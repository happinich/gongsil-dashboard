from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from sqlite3 import Row

from .config import Settings
from .matcher import event_matches_profile
from .storage import connect, list_unnotified_events_for_profiles, record_notification


@dataclass
class NotifyResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0


def send_pending_telegram_alerts(settings: Settings) -> NotifyResult:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")

    result = NotifyResult()
    with connect(settings.db_path) as conn:
        rows = list_unnotified_events_for_profiles(conn, channel="telegram")
        for row in rows:
            if not event_matches_profile(row):
                result.skipped += 1
                continue
            try:
                send_telegram_message(settings, build_message(row))
                record_notification(conn, row["event_id"], row["profile_id"], "telegram", "sent")
                result.sent += 1
            except Exception as exc:  # noqa: BLE001
                record_notification(conn, row["event_id"], row["profile_id"], "telegram", "failed", str(exc))
                result.failed += 1
    return result


def send_telegram_message(settings: Settings, text: str) -> None:
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if settings.telegram_topic_id:
        payload["message_thread_id"] = settings.telegram_topic_id

    data = urllib.parse.urlencode(payload).encode("utf-8")
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(f"Telegram API error: {body}")


def build_message(row: Row) -> str:
    label = "신규 매물" if row["event_type"] == "new_listing" else "가격 변경"
    price_line = row["new_price_text"] or row["price_text"] or ""
    if row["event_type"] == "price_changed":
        price_line = f"{row['old_price_text']} -> {row['new_price_text']}"
    parts = [
        f"<b>{label}</b>",
        f"조건: <b>{_escape(row['profile_name'])}</b>",
        f"지역/거래: {_escape(row['district'])} / {_escape(row['deal_type'])}",
        f"건물명: {_escape(row['building_name'] or '-')}",
        f"주소: {_escape(row['address'] or '-')}",
        f"면적: {_escape(row['area_text'] or '-')}",
        f"구조/입주: {_escape(row['room_text'] or '-')} / {_escape(row['move_in'] or '-')}",
        f"금액: <b>{_escape(price_line)}</b>",
        f"등록자: {_escape(row['agent_text'] or '-')}",
        f"링크: {_escape(row['detail_url'] or '-')}",
        f"시각: {_escape(row['event_at'])}",
    ]
    return "\n".join(parts)


def _escape(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
