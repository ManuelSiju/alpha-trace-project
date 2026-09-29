from __future__ import annotations
from typing import List

from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding


class PhoneAgent(BaseAgent):
    name = "PhoneAgent"
    category = "Phone Intelligence"

    async def gather(self, target: Target) -> List[Finding]:
        if not target.phone:
            return []

        try:
            import phonenumbers
            from phonenumbers import geocoder, carrier, timezone
        except ImportError:
            logger.warning("phonenumbers not installed")
            return [self._no_source("the 'phonenumbers' library is not installed")]

        # When the user types a bare local number (no +country code), assume the
        # configured region so an Indian 10-digit mobile parses correctly instead
        # of failing. E.164 numbers (leading +) ignore this default.
        from config.settings import settings
        default_region = settings.REGION_FOCUS.upper() or None
        try:
            parsed = phonenumbers.parse(target.phone, default_region)
        except phonenumbers.NumberParseException as e:
            return [Finding(
                category=self.category,
                source="phonenumbers",
                title="Phone parse failed",
                content=f"Could not parse '{target.phone}': {e}",
                confidence=20,
            )]

        valid = phonenumbers.is_valid_number(parsed)
        type_map = {
            0: "Fixed Line", 1: "Mobile", 2: "Fixed Line or Mobile",
            3: "Toll Free", 4: "Premium Rate", 5: "Shared Cost",
            6: "VoIP", 7: "Personal Number", 8: "Pager", 9: "UAN",
            10: "Voicemail", 27: "Unknown",
        }
        ntype = type_map.get(phonenumbers.number_type(parsed), "Unknown")
        country = geocoder.description_for_number(parsed, "en")
        carrier_name = carrier.name_for_number(parsed, "en")
        tzs = list(timezone.time_zones_for_number(parsed))

        return [Finding(
            category=self.category,
            source="phonenumbers",
            title=f"Phone {target.phone} parsed",
            content=f"valid={valid}; country={country}; carrier={carrier_name}; type={ntype}; tz={tzs}",
            confidence=85 if valid else 30,
            data={
                "valid": valid,
                "country": country,
                "carrier": carrier_name,
                "type": ntype,
                "timezones": tzs,
                "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                "international": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            },
        )]

    def _no_source(self, reason: str) -> Finding:
        return Finding(
            category=self.category,
            source="phone-intelligence",
            title="No phone-intelligence source configured",
            content=(
                f"Structured phone lookup unavailable: {reason}. Alpha-Tracer does not use "
                "data-broker or people-search sites for phone lookups by design."
            ),
            confidence=0,
        )
