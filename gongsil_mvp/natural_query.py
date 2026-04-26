from __future__ import annotations

import re
from datetime import datetime

DISTRICT_MAP = {
    "강남": "강남구",
    "강남구": "강남구",
    "서초": "서초구",
    "서초구": "서초구",
}

AREA_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:~|\-|부터)\s*(\d+(?:\.\d+)?)\s*평")
AREA_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*평")
YEARS_RE = re.compile(r"(\d+)\s*년\s*이내")
RADIUS_RE = re.compile(r"(\d{3,4})\s*m\s*(?:이내|근처)?|(\d{3,4})\s*미터")
STATION_RE = re.compile(r"([가-힣A-Za-z0-9]+역)")
MONEY_BELOW_RE = re.compile(r"(\d[\d,]*)\s*만원\s*이하")
MONEY_RANGE_RE = re.compile(r"(\d[\d,]*)\s*만원\s*(?:~|\-)\s*(\d[\d,]*)\s*만원")


def parse_natural_query(query: str) -> dict[str, object]:
    text = " ".join((query or "").split())
    current_year = datetime.now().year
    values: dict[str, object] = {
        "name": text[:60] or "자연어 조건",
        "district": _extract_district(text),
        "deal_type": _extract_deal_type(text),
        "deposit_min": None,
        "deposit_max": None,
        "rent_min": None,
        "rent_max": None,
        "sale_min": None,
        "sale_max": None,
        "area_min": None,
        "area_max": None,
        "keyword": "",
        "built_year_min": None,
        "station_name": _extract_station(text),
        "radius_m": _extract_radius(text),
        "station_latitude": None,
        "station_longitude": None,
    }

    area_match = AREA_RANGE_RE.search(text)
    if area_match:
        values["area_min"] = float(area_match.group(1))
        values["area_max"] = float(area_match.group(2))
    else:
        single_area = AREA_SINGLE_RE.search(text)
        if single_area:
            area = float(single_area.group(1))
            values["area_min"] = area
            values["area_max"] = area

    year_match = YEARS_RE.search(text)
    if year_match:
        years = int(year_match.group(1))
        values["built_year_min"] = current_year - years + 1
    elif "신축급" in text or "신축" in text:
        values["built_year_min"] = current_year - 10 + 1

    lower_money = _extract_money_below(text)
    if values["deal_type"] == "월세":
        values["rent_max"] = lower_money
    elif values["deal_type"] == "전세":
        values["deposit_max"] = lower_money
    elif values["deal_type"] == "매매":
        values["sale_max"] = lower_money

    min_money, max_money = _extract_money_range(text)
    if values["deal_type"] == "월세":
        values["rent_min"] = min_money
        values["rent_max"] = max_money or values["rent_max"]

    keywords = []
    if "원룸" in text:
        keywords.append("원룸")
    if "복층" in text:
        keywords.append("복층")
    values["keyword"] = ", ".join(dict.fromkeys(keywords))

    if values["station_name"] and values["radius_m"] is None:
        values["radius_m"] = 700

    return values


def summarize_natural_profile(values: dict[str, object]) -> str:
    parts = []
    for key, label in (("district", "지역"), ("deal_type", "거래"), ("station_name", "역")):
        if values.get(key):
            parts.append(f"{label}:{values[key]}")
    if values.get("radius_m"):
        parts.append(f"반경:{values['radius_m']}m")
    if values.get("area_min") or values.get("area_max"):
        parts.append(f"평수:{values.get('area_min') or ''}~{values.get('area_max') or ''}")
    if values.get("rent_max") is not None:
        parts.append(f"월세:~{values['rent_max']}")
    if values.get("deposit_max") is not None:
        parts.append(f"보증금:~{values['deposit_max']}")
    if values.get("sale_max") is not None:
        parts.append(f"매매가:~{values['sale_max']}")
    if values.get("built_year_min"):
        parts.append(f"준공:{values['built_year_min']}년 이후")
    if values.get("keyword"):
        parts.append(f"키워드:{values['keyword']}")
    return " / ".join(parts)


def _extract_district(text: str) -> str:
    for token, district in DISTRICT_MAP.items():
        if token in text:
            return district
    return ""


def _extract_deal_type(text: str) -> str:
    if "월세" in text:
        return "월세"
    if "전세" in text:
        return "전세"
    if "매매" in text:
        return "매매"
    if "단기" in text:
        return "단기"
    return ""


def _extract_station(text: str) -> str:
    match = STATION_RE.search(text)
    return match.group(1) if match else ""


def _extract_radius(text: str) -> int | None:
    match = RADIUS_RE.search(text)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    return int(raw) if raw else None


def _extract_money_below(text: str) -> int | None:
    match = MONEY_BELOW_RE.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _extract_money_range(text: str) -> tuple[int | None, int | None]:
    match = MONEY_RANGE_RE.search(text)
    if not match:
        return None, None
    return int(match.group(1).replace(",", "")), int(match.group(2).replace(",", ""))
