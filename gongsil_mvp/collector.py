from __future__ import annotations

import time
from dataclasses import dataclass

from .client import GongsilClient
from .config import DEFAULT_PAGE_SIZE, DISTRICTS, OFFICETEL_CODE, Settings
from .geocode import Geocoder
from .parser import parse_detail, parse_listing_rows
from .storage import connect, finish_run, init_db, start_run, update_detail, update_listing_geocode, upsert_listing


@dataclass
class CollectResult:
    district: str
    complex_name: str = ""
    pages_fetched: int = 0
    listings_seen: int = 0
    new_listings: int = 0
    price_changes: int = 0
    detail_pages_fetched: int = 0


def collect_officetels(
    settings: Settings,
    districts: tuple[str, ...] = DISTRICTS,
    max_pages: int = 2,
    fetch_details: bool = True,
    complex_names: tuple[str, ...] | None = None,
) -> list[CollectResult]:
    init_db(settings.db_path)
    client = GongsilClient(settings.username, settings.password)
    geocoder = Geocoder(settings)
    client.login()
    results: list[CollectResult] = []

    with connect(settings.db_path) as conn:
        target_complexes = complex_names if complex_names is not None else settings.complex_names
        search_targets = tuple(target_complexes) or ("",)
        for district in districts:
            for complex_name in search_targets:
                run_id = start_run(conn, district=district, k_code=OFFICETEL_CODE)
                result = CollectResult(district=district, complex_name=complex_name)
                try:
                    for page_index in range(max_pages):
                        page_no = page_index * DEFAULT_PAGE_SIZE
                        filters = {"k_bname": complex_name} if complex_name else {}
                        html = client.fetch_listing_page(district=district, page_no=page_no, **filters)
                        result.pages_fetched += 1
                        rows = parse_listing_rows(html, district=district, k_code=OFFICETEL_CODE)
                        if complex_name:
                            rows = [row for row in rows if complex_name in row.building_name]
                        if not rows:
                            break
                        result.listings_seen += len(rows)
                        for row in rows:
                            upsert_result = upsert_listing(conn, row)
                            if upsert_result.status == "new":
                                result.new_listings += 1
                            elif upsert_result.status == "price_changed":
                                result.price_changes += 1
                            if fetch_details and upsert_result.needs_detail_refresh:
                                time.sleep(settings.request_delay_seconds)
                                detail_html = client.fetch_detail(row.source_listing_id)
                                detail = parse_detail(detail_html)
                                update_detail(conn, row.source_listing_id, detail)
                                point = geocoder.geocode_listing_candidate(
                                    {
                                        "district": row.district,
                                        "address": row.address,
                                        "building_name": row.building_name,
                                        "full_address": detail.get("full_address", ""),
                                    }
                                )
                                if point:
                                    update_listing_geocode(
                                        conn,
                                        source_listing_id=row.source_listing_id,
                                        latitude=point.latitude,
                                        longitude=point.longitude,
                                        status="ok",
                                        source=point.source,
                                        full_address=detail.get("full_address", "") or point.address,
                                    )
                                result.detail_pages_fetched += 1
                        conn.commit()
                        time.sleep(settings.request_delay_seconds)
                    finish_run(
                        conn,
                        run_id,
                        pages_fetched=result.pages_fetched,
                        listings_seen=result.listings_seen,
                        new_listings=result.new_listings,
                        price_changes=result.price_changes,
                        detail_pages_fetched=result.detail_pages_fetched,
                    )
                except Exception as exc:
                    finish_run(conn, run_id, error=str(exc))
                    raise
                results.append(result)
    return results
