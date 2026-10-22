import ipaddress
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


def llm_url_is_private(url: str) -> bool:
    """True for localhost, private/LAN addresses and bare service names (docker compose).

    The product runs in a closed contour: the LLM must be Ollama on this machine or the LAN,
    never a public API."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith((".local", ".lan", ".internal"))
    return ip.is_private or ip.is_loopback


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://maxi:maxi@localhost:5432/maxicalc"  # reserved (not used yet)
    redis_url: str | None = None          # e.g. redis://localhost:6379/0 ; None = in-memory cache
    # Local LLM through Ollama's OpenAI-compatible API (closed contour, RTX 3090 24 GB server).
    # Model = whatever `ollama list` shows; compare candidates with scripts/llm_bench.py.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3:14b"
    llm_api_key: str = ""
    llm_timeout_s: float = 60.0
    llm_enabled: bool = True              # False = never call the LLM (deterministic fallbacks)
    llm_allow_remote: bool = False        # a public LLM URL is refused unless this is set
    cors_origins: str = "*"               # comma-separated origins of the shop site(s)
    hardware_tier: str = "gpu24"          # gpu24 | gpu8 | cpu

    # The organisers' catalog stand (Bagisto API). One variable switches mock <-> real:
    # STAND_BASE_URL=http://127.0.0.1:9000 (mock, `make mock-stand`) or the real stand URL.
    stand_base_url: str | None = None
    stand_token: str | None = None
    stand_region_id: str | None = None    # region context for stock; None = the stand's default
    stand_cache_dir: str = "data/stand_cache"
    stand_min_interval_s: float = 0.0     # politeness: minimum gap between stand requests
    margin_weight: float = 0.0            # ranking weight of a margin field; 0 = inactive
    rating_weight: float = 0.0            # ranking weight of rating / recsys_rating; 0 = inactive
    completeness_weight: float = 0.2      # ranking weight of card completeness (no ratings needed)
    catalog_path: str | None = None       # CSV / XLSX / JSON / YML catalog loaded at startup
    overrides_path: str | None = None     # JSONL of human bindings; they always beat ML
    model_path: str | None = None         # joblib MatchModel; None = rules only
    worktype_model_path: str | None = "data/models/worktypes.joblib"   # absent file = rules only
    worktype_overrides_path: str | None = None   # JSON of human work-type fixes (they win)
    cache_max_items: int = 5000
    cache_ttl_s: int = 86400
    rate_limit_per_min: int = 600         # per client IP; 0 disables
    rate_limit_burst: int = 100
    pdf_font_path: str | None = None      # TTF with Cyrillic for PDF export
    log_json: bool = True
    sync_match_limit: int = 500           # larger /catalog/match batches become background jobs


settings = Settings()
