from __future__ import annotations

from core.agents.image_agent import reverse_image_search_urls


def test_reverse_image_urls_cover_major_engines():
    urls = reverse_image_search_urls("https://example.com/a photo.jpg")
    assert set(urls) == {"google_lens", "yandex", "bing", "tineye"}
    # the image URL is percent-encoded into each query (space -> %20)
    assert "example.com%2Fa%20photo.jpg" in urls["yandex"]
    assert all(v.startswith("https://") for v in urls.values())
