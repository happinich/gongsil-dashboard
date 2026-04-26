from __future__ import annotations

import html
import re


TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
BR_RE = re.compile(r"<br\s*/?>", re.I)


def decode_euc_kr(data: bytes) -> str:
    return data.decode("euc-kr", errors="ignore")


def clean_html(value: str) -> str:
    value = SCRIPT_STYLE_RE.sub(" ", value)
    value = BR_RE.sub(" ", value)
    value = TAG_RE.sub(" ", value)
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def first_match(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, re.I | re.S)
    return clean_html(match.group(1)) if match else default
