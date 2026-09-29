from __future__ import annotations
from pathlib import Path
from typing import List
from urllib.parse import quote

from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding


def reverse_image_search_urls(image_url: str) -> dict[str, str]:
    """Build ready-to-open reverse-image-search links for a *hosted* image URL.
    These are the real query URLs each engine accepts for by-URL search -- no
    API key, no scraping; the analyst clicks through. (A local file can't be
    auto-submitted this way; it must be uploaded to the engine manually.)"""
    enc = quote(image_url, safe="")
    return {
        "google_lens": f"https://lens.google.com/uploadbyurl?url={enc}",
        "yandex": f"https://yandex.com/images/search?rpt=imageview&url={enc}",
        "bing": f"https://www.bing.com/images/search?q=imgurl:{enc}&view=detailv2&iss=sbi",
        "tineye": f"https://tineye.com/search?url={enc}",
    }


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
