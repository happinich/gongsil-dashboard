from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_URL = "https://www.gongsil.com"
LOGIN_URL = f"{BASE_URL}/h/member/login_check.php"
ARTICLE_URL = f"{BASE_URL}/article/ad/"

DISTRICTS = ("강남구", "서초구")
OFFICETEL_CODE = "21"
SEOUL_CODE = "1"
DEFAULT_PAGE_SIZE = 30
DEFAULT_COMPLEX_NAMES = (
    "삼성롯데캐슬클라쎄",
    "현대위버포레",
    "선릉LG에클라트",
    "현대썬앤빌삼성역",
    "삼성파크엘나인",
    "대치3차아이파크",
    "대치2차아이파크",
    "대치트레비스타",
    "코업레지던스",
    "역삼역센트럴아이파크시티",
    "리에바움",
    "강남헤븐리치더써밋761",
    "역삼노블루체언주",
)
DEFAULT_COLLECTION_DISTRICTS = ("강남구",)


@dataclass(frozen=True)
class Settings:
    username: str
    password: str
    db_path: Path
    dashboard_user: str = "admin"
    dashboard_password: str = ""
    request_delay_seconds: float = 0.8
    geocode_delay_seconds: float = 1.0
    default_max_pages: int = 2
    collection_districts: tuple[str, ...] = DEFAULT_COLLECTION_DISTRICTS
    complex_names: tuple[str, ...] = DEFAULT_COMPLEX_NAMES
    kakao_rest_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_topic_id: str = ""


def load_settings(require_credentials: bool = True) -> Settings:
    username = os.getenv("GONGSIL_ID", "").strip()
    password = os.getenv("GONGSIL_PASSWORD", "").strip()
    if require_credentials and (not username or not password):
        raise SystemExit(
            "Missing GONGSIL_ID or GONGSIL_PASSWORD. "
            "Create a local .env or export them before collecting."
        )

    db_path = Path(os.getenv("GONGSIL_DB", "data/gongsil.sqlite3")).resolve()
    delay_raw = os.getenv("GONGSIL_REQUEST_DELAY_SECONDS", "0.8").strip()
    try:
        delay = max(0.0, float(delay_raw))
    except ValueError:
        delay = 0.8
    geocode_delay_raw = os.getenv("GONGSIL_GEOCODE_DELAY_SECONDS", "1.0").strip()
    try:
        geocode_delay = max(0.0, float(geocode_delay_raw))
    except ValueError:
        geocode_delay = 1.0
    default_max_pages_raw = os.getenv("GONGSIL_DEFAULT_MAX_PAGES", "2").strip()
    try:
        default_max_pages = max(1, int(default_max_pages_raw))
    except ValueError:
        default_max_pages = 2
    complex_names = tuple(
        item.strip()
        for item in os.getenv("GONGSIL_COMPLEX_NAMES", "").split(",")
        if item.strip()
    ) or DEFAULT_COMPLEX_NAMES
    collection_districts = tuple(
        item.strip()
        for item in os.getenv("GONGSIL_COLLECTION_DISTRICTS", "").split(",")
        if item.strip() in DISTRICTS
    ) or DEFAULT_COLLECTION_DISTRICTS

    return Settings(
        username=username,
        password=password,
        db_path=db_path,
        dashboard_user=os.getenv("DASHBOARD_USER", "admin").strip() or "admin",
        dashboard_password=os.getenv("DASHBOARD_PASSWORD", "").strip(),
        request_delay_seconds=delay,
        geocode_delay_seconds=geocode_delay,
        default_max_pages=default_max_pages,
        collection_districts=collection_districts,
        complex_names=complex_names,
        kakao_rest_api_key=os.getenv("KAKAO_REST_API_KEY", "").strip(),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        telegram_topic_id=os.getenv("TELEGRAM_TOPIC_ID", "").strip(),
    )
