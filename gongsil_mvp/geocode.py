from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from sqlite3 import Row

from .config import Settings
from .storage import connect, list_ungeocoded_listings, update_listing_geocode


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float
    source: str
    address: str


class Geocoder:
    def __init__(self, settings: Settings):
        self.settings = settings

    def geocode(self, query: str) -> GeoPoint | None:
        query = query.strip()
        if not query:
            return None
        if self.settings.kakao_rest_api_key:
            point = self._geocode_kakao(query)
            if point:
                return point
        return self._geocode_nominatim(query)

    def geocode_station(self, station_name: str) -> GeoPoint | None:
        query = station_name.strip()
        if not query:
            return None
        if not query.endswith("역"):
            query = query + "역"
        return self.geocode(f"서울 {query}")

    def geocode_listing_candidate(self, listing: Row | dict[str, object]) -> GeoPoint | None:
        candidates = build_listing_queries(listing)
        for query in candidates:
            point = self.geocode(query)
            if point:
                return point
            time.sleep(self.settings.geocode_delay_seconds)
        return None

    def _geocode_kakao(self, query: str) -> GeoPoint | None:
        encoded = urllib.parse.urlencode({"query": query})
        url = f"https://dapi.kakao.com/v2/local/search/address.json?{encoded}"
        request = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {self.settings.kakao_rest_api_key}"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        documents = body.get("documents") or []
        if not documents:
            return None
        item = documents[0]
        return GeoPoint(
            latitude=float(item["y"]),
            longitude=float(item["x"]),
            source="kakao",
            address=item.get("address_name") or query,
        )

    def _geocode_nominatim(self, query: str) -> GeoPoint | None:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "kr",
            }
        )
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "GongsilInternalMVP/0.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not body:
            return None
        item = body[0]
        return GeoPoint(
            latitude=float(item["lat"]),
            longitude=float(item["lon"]),
            source="nominatim",
            address=item.get("display_name") or query,
        )


def build_listing_queries(listing: Row | dict[str, object]) -> list[str]:
    def value(key: str) -> str:
        raw = listing[key] if isinstance(listing, Row) else listing.get(key, "")
        return str(raw or "").strip()

    district = value("district")
    address = value("address")
    building_name = value("building_name")
    full_address = value("full_address")

    prefix = f"서울특별시 {district}" if district else "서울특별시"
    queries = []
    if full_address:
        queries.append(full_address)
    if address and building_name:
        queries.append(f"{prefix} {address} {building_name}")
    if address:
        queries.append(f"{prefix} {address}")
    if building_name:
        queries.append(f"{prefix} {building_name}")
    deduped = []
    seen = set()
    for item in queries:
        cleaned = " ".join(item.split())
        if cleaned and cleaned not in seen:
            deduped.append(cleaned)
            seen.add(cleaned)
    return deduped


def geocode_pending_listings(settings: Settings, limit: int = 100) -> tuple[int, int]:
    geocoder = Geocoder(settings)
    success = 0
    failed = 0
    with connect(settings.db_path) as conn:
        rows = list_ungeocoded_listings(conn, limit=limit)
        for row in rows:
            point = geocoder.geocode_listing_candidate(row)
            if point:
                update_listing_geocode(
                    conn,
                    source_listing_id=row["source_listing_id"],
                    latitude=point.latitude,
                    longitude=point.longitude,
                    status="ok",
                    source=point.source,
                    full_address=row["full_address"] or point.address,
                )
                success += 1
            else:
                update_listing_geocode(
                    conn,
                    source_listing_id=row["source_listing_id"],
                    latitude=None,
                    longitude=None,
                    status="failed",
                    source="",
                    full_address=row["full_address"],
                )
                failed += 1
            time.sleep(settings.geocode_delay_seconds)
    return success, failed
