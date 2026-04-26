from __future__ import annotations

import json
import re
from math import asin, cos, radians, sin, sqrt
from sqlite3 import Row
from typing import Any


NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
AREA_RE = re.compile(r"\((\d+(?:\.\d+)?)\)")


def parse_price(price_text: str) -> dict[str, int | None]:
    text = price_text.replace(" ", "")
    numbers = [int(float(value.replace(",", ""))) for value in NUMBER_RE.findall(text)]
    result: dict[str, int | None] = {"deposit": None, "rent": None, "sale": None}
    if text.startswith("월"):
        if len(numbers) >= 1:
            result["deposit"] = numbers[0]
        if len(numbers) >= 2:
            result["rent"] = numbers[1]
    elif text.startswith("매"):
        if numbers:
            result["sale"] = numbers[0]
    elif text.startswith("전"):
        if numbers:
            result["deposit"] = numbers[0]
    return result


def parse_area_pyeong(area_text: str) -> float | None:
    match = AREA_RE.search(area_text or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def profile_matches_listing(profile: Row, listing: Row) -> bool:
    if profile["district"] and profile["district"] != listing["district"]:
        return False
    if profile["deal_type"] and profile["deal_type"] != listing["deal_type"]:
        return False

    keyword = (profile["keyword"] or "").strip().lower()
    if keyword:
        keywords = [item.strip() for item in keyword.split(",") if item.strip()]
        haystack = " ".join(
            str(listing[key] or "")
            for key in ("address", "building_name", "room_text", "move_in", "price_text", "agent_text", "full_address", "detail_json")
        ).lower()
        if not keywords:
            keywords = [keyword]
        if any(item not in haystack for item in keywords):
            return False

    price = parse_price(listing["price_text"] or "")
    if not _in_range(price["deposit"], profile["deposit_min"], profile["deposit_max"]):
        return False
    if not _in_range(price["rent"], profile["rent_min"], profile["rent_max"]):
        return False
    if not _in_range(price["sale"], profile["sale_min"], profile["sale_max"]):
        return False

    area = parse_area_pyeong(listing["area_text"] or "")
    if not _in_range(area, profile["area_min"], profile["area_max"]):
        return False

    built_year_min = _as_int(_value(profile, "built_year_min"))
    if built_year_min is not None:
        built_year = extract_built_year(listing)
        if built_year is not None and built_year < built_year_min:
            return False

    station_lat = _as_float(_value(profile, "station_latitude"))
    station_lng = _as_float(_value(profile, "station_longitude"))
    radius_m = _as_float(_value(profile, "radius_m"))
    if station_lat is not None and station_lng is not None and radius_m is not None:
        listing_lat = _as_float(_value(listing, "latitude"))
        listing_lng = _as_float(_value(listing, "longitude"))
        if listing_lat is None or listing_lng is None:
            return False
        if haversine_meters(station_lat, station_lng, listing_lat, listing_lng) > radius_m:
            return False
    return True


def filter_listings(profile: Row | None, listings: list[Row]) -> list[Row]:
    if profile is None:
        return listings
    return [listing for listing in listings if profile_matches_listing(profile, listing)]


def match_count(profile: Row, listings: list[Row]) -> int:
    return sum(1 for listing in listings if profile_matches_listing(profile, listing))


def event_matches_profile(event_row: Row) -> bool:
    profile = {
        "district": event_row["profile_district"],
        "deal_type": event_row["profile_deal_type"],
        "keyword": event_row["keyword"],
        "deposit_min": event_row["deposit_min"],
        "deposit_max": event_row["deposit_max"],
        "rent_min": event_row["rent_min"],
        "rent_max": event_row["rent_max"],
        "sale_min": event_row["sale_min"],
        "sale_max": event_row["sale_max"],
        "area_min": event_row["area_min"],
        "area_max": event_row["area_max"],
        "built_year_min": event_row["built_year_min"],
        "station_latitude": event_row["station_latitude"],
        "station_longitude": event_row["station_longitude"],
        "radius_m": event_row["radius_m"],
    }
    listing = {
        "district": event_row["district"],
        "deal_type": event_row["deal_type"],
        "address": event_row["address"],
        "building_name": event_row["building_name"],
        "room_text": event_row["room_text"],
        "move_in": event_row["move_in"],
        "price_text": event_row["price_text"],
        "agent_text": event_row["agent_text"],
        "area_text": event_row["area_text"],
        "full_address": event_row["full_address"],
        "latitude": event_row["latitude"],
        "longitude": event_row["longitude"],
        "detail_json": event_row["detail_json"],
    }
    return profile_matches_listing(profile, listing)


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    return radius * c


def _in_range(value: int | float | None, min_value: Any, max_value: Any) -> bool:
    min_number = _as_float(min_value)
    max_number = _as_float(max_value)
    if min_number is None and max_number is None:
        return True
    if value is None:
        return False
    number = float(value)
    if min_number is not None and number < min_number:
        return False
    if max_number is not None and number > max_number:
        return False
    return True


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def extract_built_year(listing: Any) -> int | None:
    detail_json = _value(listing, "detail_json")
    if not detail_json:
        return None
    try:
        detail = json.loads(detail_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    for key in ("built_date", "built_at", "built_year", "completion_date"):
        year = _extract_year_from_text(detail.get(key))
        if year is not None:
            return year
    for value in detail.values():
        year = _extract_year_from_text(value)
        if year is not None:
            return year
    return None


def _extract_year_from_text(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value)
    match = re.search(r"(19\d{2}|20\d{2})", text)
    if not match:
        return None
    year = int(match.group(1))
    if 1900 <= year <= 2100:
        return year
    return None


def _value(item: Any, key: str) -> Any:
    if isinstance(item, Row):
        return item[key]
    return item.get(key)
