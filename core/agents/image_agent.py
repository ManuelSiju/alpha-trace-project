from __future__ import annotations
from pathlib import Path
from typing import List

from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding


class ImageAgent(BaseAgent):
    name = "ImageAgent"
    category = "Image Metadata"

    async def gather(self, target: Target) -> List[Finding]:
        if not target.image_path:
            return []
        p = Path(target.image_path)
        if not p.exists():
            return [Finding(
                category=self.category,
                source="local",
                title="Image path missing",
                content=f"File not found: {p}",
                confidence=0,
            )]
        try:
            from PIL import Image, ExifTags
        except ImportError:
            logger.warning("Pillow not installed")
            return []

        try:
            img = Image.open(p)
            exif_raw = img._getexif() or {}
            exif = {ExifTags.TAGS.get(k, str(k)): str(v) for k, v in exif_raw.items()}
        except Exception as e:
            return [Finding(
                category=self.category,
                source="exif",
                title="EXIF read failed",
                content=str(e),
                confidence=10,
            )]
        if not exif:
            return [Finding(
                category=self.category,
                source="exif",
                title="No EXIF data",
                content=f"{p.name} contains no EXIF metadata.",
                confidence=50,
            )]
        return [Finding(
            category=self.category,
            source="exif",
            title=f"EXIF metadata: {p.name}",
            content="; ".join(f"{k}={v[:60]}" for k, v in list(exif.items())[:10]),
            confidence=85,
            data=exif,
        )]
