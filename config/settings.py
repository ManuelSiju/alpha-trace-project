from __future__ import annotations
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    BASE_DIR: Path = Path(__file__).parent.parent
    OUTPUT_DIR: Path = BASE_DIR / "outputs"
    ASSETS_DIR: Path = BASE_DIR / "assets"
    LOG_FILE: Path = BASE_DIR / "alpha_tracer.log"

    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b-instruct"
    OLLAMA_FALLBACK_MODEL: str = "qwen2.5:3b-instruct"
    OLLAMA_NUM_CTX: int = 8192
    LLM_TEMPERATURE: float = 0.6
    LLM_MAX_TOKENS: int = 2000
    LLM_TIMEOUT: int = 120

    MAX_FINDINGS_PER_CATEGORY: int = 10
    CHAT_TOP_K_EVIDENCE: int = 8

    USER_AGENTS: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]

    USE_PROXIES: bool = False
    PROXY_LIST: Optional[List[str]] = None

    MAX_REQUESTS_PER_MINUTE: int = 30
    MAX_CONCURRENT_REQUESTS: int = 5
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 5
    AGENT_TIMEOUT: int = 260

    ENABLE_USERNAME_AGENT: bool = True
    ENABLE_EMAIL_AGENT: bool = True
    ENABLE_PHONE_AGENT: bool = True
    ENABLE_SOCIAL_MEDIA_AGENT: bool = True
    ENABLE_DOMAIN_AGENT: bool = True
    ENABLE_IMAGE_AGENT: bool = False
    ENABLE_BREACH_AGENT: bool = True
    ENABLE_PEOPLE_SEARCH_AGENT: bool = True
    ENABLE_GITHUB_AGENT: bool = True
    ENABLE_WEB_AGENT: bool = True
    ENABLE_ARCHIVE_AGENT: bool = True

    HEADLESS_BROWSER: bool = True
    ENABLE_PLAYWRIGHT: bool = False
    BROWSER_TIMEOUT_MS: int = 30000

    MAX_TWEETS_PER_USER: int = 100
    MAX_INSTAGRAM_POSTS: int = 30
    SHERLOCK_TIMEOUT: int = 240
    SHERLOCK_PER_SITE_TIMEOUT: int = 8

    CACHE_TTL: int = 3600

    GENERATE_PDF_REPORTS: bool = True
    GENERATE_JSON_EXPORTS: bool = True
    SAVE_RAW_DATA: bool = True

    LOG_LEVEL: str = "INFO"

    SHODAN_API_KEY: Optional[str] = None
    HAVEIBEENPWNED_API_KEY: Optional[str] = None
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    REDDIT_USER_AGENT: str = "alpha-tracer/0.1"


settings = Settings()

for d in (
    settings.OUTPUT_DIR,
    settings.ASSETS_DIR,
    settings.OUTPUT_DIR / "reports",
):
    d.mkdir(parents=True, exist_ok=True)
