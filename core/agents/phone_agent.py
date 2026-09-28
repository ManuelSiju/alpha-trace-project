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
            return []

        try:
            parsed = phonenumbers.parse(target.phone, None)
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
