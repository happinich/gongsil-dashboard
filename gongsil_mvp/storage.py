from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .parser import ListingSummary


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT 'gongsil',
    source_listing_id TEXT NOT NULL UNIQUE,
    k_code TEXT NOT NULL,
    district TEXT NOT NULL,
    deal_type TEXT,
    address TEXT,
    building_name TEXT,
    area_text TEXT,
    room_text TEXT,
    move_in TEXT,
    price_text TEXT,
    registered_date TEXT,
    agent_text TEXT,
    agent_phone TEXT,
    full_address TEXT,
    latitude REAL,
    longitude REAL,
    geocode_status TEXT,
    geocode_source TEXT,
    geocoded_at TEXT,
    detail_url TEXT,
    list_raw_hash TEXT,
    detail_raw_hash TEXT,
    detail_json TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_district ON listings(district);
CREATE INDEX IF NOT EXISTS idx_listings_seen ON listings(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_text);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    district TEXT,
    k_code TEXT,
    pages_fetched INTEGER DEFAULT 0,
    listings_seen INTEGER DEFAULT 0,
    new_listings INTEGER DEFAULT 0,
    price_changes INTEGER DEFAULT 0,
    detail_pages_fetched INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS search_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    district TEXT,
    deal_type TEXT,
    deposit_min INTEGER,
    deposit_max INTEGER,
    rent_min INTEGER,
    rent_max INTEGER,
    sale_min INTEGER,
    sale_max INTEGER,
    area_min REAL,
    area_max REAL,
    keyword TEXT,
    built_year_min INTEGER,
    station_name TEXT,
    radius_m INTEGER,
    station_latitude REAL,
    station_longitude REAL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_listing_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_price_text TEXT,
    new_price_text TEXT,
    event_at TEXT NOT NULL,
    UNIQUE(source_listing_id, event_type, old_price_text, new_price_text)
);

CREATE INDEX IF NOT EXISTS idx_listing_events_recent ON listing_events(event_at DESC);

CREATE TABLE IF NOT EXISTS notification_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    UNIQUE(event_id, profile_id, channel)
);

CREATE INDEX IF NOT EXISTS idx_notification_logs_recent ON notification_logs(sent_at DESC);
"""


@dataclass(frozen=True)
class UpsertResult:
    status: str
    needs_detail_refresh: bool = False


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate_schema(conn)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _migrate_schema(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "collection_runs", "price_changes", "INTEGER DEFAULT 0")
    _ensure_column(conn, "listings", "full_address", "TEXT")
    _ensure_column(conn, "listings", "latitude", "REAL")
    _ensure_column(conn, "listings", "longitude", "REAL")
    _ensure_column(conn, "listings", "geocode_status", "TEXT")
    _ensure_column(conn, "listings", "geocode_source", "TEXT")
    _ensure_column(conn, "listings", "geocoded_at", "TEXT")
    _ensure_column(conn, "search_profiles", "station_name", "TEXT")
    _ensure_column(conn, "search_profiles", "radius_m", "INTEGER")
    _ensure_column(conn, "search_profiles", "station_latitude", "REAL")
    _ensure_column(conn, "search_profiles", "station_longitude", "REAL")
    _ensure_column(conn, "search_profiles", "built_year_min", "INTEGER")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def start_run(conn: sqlite3.Connection, district: str, k_code: str) -> int:
    cur = conn.execute(
        "INSERT INTO collection_runs(started_at, district, k_code) VALUES (?, ?, ?)",
        (now_iso(), district, k_code),
    )
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, **values: object) -> None:
    allowed = {"pages_fetched", "listings_seen", "new_listings", "price_changes", "detail_pages_fetched", "error"}
    set_values = {key: value for key, value in values.items() if key in allowed}
    set_values["finished_at"] = now_iso()
    assignments = ", ".join(f"{key} = ?" for key in set_values)
    conn.execute(
        f"UPDATE collection_runs SET {assignments} WHERE id = ?",
        (*set_values.values(), run_id),
    )


def upsert_listing(conn: sqlite3.Connection, listing: ListingSummary) -> UpsertResult:
    existing = conn.execute(
        "SELECT id, price_text, registered_date, deal_type, detail_raw_hash, detail_json FROM listings WHERE source_listing_id = ?",
        (listing.source_listing_id,),
    ).fetchone()
    timestamp = now_iso()
    params = {
        "source_listing_id": listing.source_listing_id,
        "k_code": listing.k_code,
        "district": listing.district,
        "deal_type": listing.deal_type,
        "address": listing.address,
        "building_name": listing.building_name,
        "area_text": listing.area_text,
        "room_text": listing.room_text,
        "move_in": listing.move_in,
        "price_text": listing.price_text,
        "registered_date": listing.registered_date,
        "agent_text": listing.agent_text,
        "agent_phone": listing.agent_phone,
        "full_address": "",
        "detail_url": listing.detail_url,
        "list_raw_hash": listing.raw_hash,
        "last_seen_at": timestamp,
        "updated_at": timestamp,
    }
    if existing:
        price_changed = (existing["price_text"] or "") != listing.price_text
        conn.execute(
            """
            UPDATE listings SET
                k_code=:k_code, district=:district, deal_type=:deal_type, address=:address,
                building_name=:building_name, area_text=:area_text, room_text=:room_text,
                move_in=:move_in, price_text=:price_text, registered_date=:registered_date,
                agent_text=:agent_text, agent_phone=:agent_phone, full_address=COALESCE(NULLIF(full_address, ''), :full_address), detail_url=:detail_url,
                list_raw_hash=:list_raw_hash, last_seen_at=:last_seen_at, updated_at=:updated_at
            WHERE source_listing_id=:source_listing_id
            """,
            params,
        )
        if price_changed:
            record_listing_event(
                conn,
                source_listing_id=listing.source_listing_id,
                event_type="price_changed",
                old_price_text=existing["price_text"] or "",
                new_price_text=listing.price_text,
            )
            return UpsertResult(status="price_changed", needs_detail_refresh=True)
        needs_detail_refresh = not existing["detail_raw_hash"] or not _has_current_detail_fields(existing["detail_json"])
        return UpsertResult(status="updated", needs_detail_refresh=needs_detail_refresh)
    conn.execute(
        """
        INSERT INTO listings (
            source_listing_id, k_code, district, deal_type, address, building_name,
            area_text, room_text, move_in, price_text, registered_date, agent_text,
            agent_phone, full_address, detail_url, list_raw_hash, first_seen_at, last_seen_at, updated_at
        ) VALUES (
            :source_listing_id, :k_code, :district, :deal_type, :address, :building_name,
            :area_text, :room_text, :move_in, :price_text, :registered_date, :agent_text,
            :agent_phone, :full_address, :detail_url, :list_raw_hash, :first_seen_at, :last_seen_at, :updated_at
        )
        """,
        {**params, "first_seen_at": timestamp},
    )
    record_listing_event(
        conn,
        source_listing_id=listing.source_listing_id,
        event_type="new_listing",
        old_price_text="",
        new_price_text=listing.price_text,
    )
    return UpsertResult(status="new", needs_detail_refresh=True)


def update_detail(conn: sqlite3.Connection, source_listing_id: str, detail: dict[str, str]) -> None:
    conn.execute(
        """
        UPDATE listings
        SET detail_json = ?, detail_raw_hash = ?, full_address = COALESCE(NULLIF(?, ''), full_address), updated_at = ?
        WHERE source_listing_id = ?
        """,
        (
            json.dumps(detail, ensure_ascii=False),
            detail.get("raw_hash", ""),
            detail.get("full_address", ""),
            now_iso(),
            source_listing_id,
        ),
    )


def _has_current_detail_fields(detail_json: str | None) -> bool:
    if not detail_json:
        return False
    try:
        detail = json.loads(detail_json)
    except (TypeError, ValueError):
        return False
    return "description" in detail and ("unit_text" in detail or "floor_text" in detail or "direction" in detail)


def update_listing_geocode(
    conn: sqlite3.Connection,
    source_listing_id: str,
    latitude: float | None,
    longitude: float | None,
    status: str,
    source: str,
    full_address: str = "",
) -> None:
    conn.execute(
        """
        UPDATE listings
        SET latitude = ?, longitude = ?, geocode_status = ?, geocode_source = ?,
            geocoded_at = ?, full_address = COALESCE(NULLIF(?, ''), full_address), updated_at = ?
        WHERE source_listing_id = ?
        """,
        (
            latitude,
            longitude,
            status,
            source,
            now_iso(),
            full_address,
            now_iso(),
            source_listing_id,
        ),
    )


def record_listing_event(
    conn: sqlite3.Connection,
    source_listing_id: str,
    event_type: str,
    old_price_text: str,
    new_price_text: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO listing_events (
            source_listing_id, event_type, old_price_text, new_price_text, event_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (source_listing_id, event_type, old_price_text, new_price_text, now_iso()),
    )


def list_recent(conn: sqlite3.Connection, limit: int = 200, district: str = "") -> list[sqlite3.Row]:
    params: list[object] = []
    where = ""
    if district:
        where = "WHERE district = ?"
        params.append(district)
    params.append(limit)
    return list(
        conn.execute(
            f"""
            SELECT * FROM listings
            {where}
            ORDER BY last_seen_at DESC, id DESC
            LIMIT ?
            """,
            params,
        )
    )


def list_ungeocoded_listings(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT source_listing_id, district, address, building_name, full_address, detail_json
            FROM listings
            WHERE (latitude IS NULL OR longitude IS NULL)
              AND COALESCE(geocode_status, '') != 'failed'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def create_profile(conn: sqlite3.Connection, values: dict[str, object]) -> int:
    timestamp = now_iso()
    cur = conn.execute(
        """
        INSERT INTO search_profiles (
            name, district, deal_type, deposit_min, deposit_max, rent_min, rent_max,
            sale_min, sale_max, area_min, area_max, keyword, built_year_min, station_name, radius_m,
            station_latitude, station_longitude, enabled, created_at, updated_at
        ) VALUES (
            :name, :district, :deal_type, :deposit_min, :deposit_max, :rent_min, :rent_max,
            :sale_min, :sale_max, :area_min, :area_max, :keyword, :built_year_min, :station_name, :radius_m,
            :station_latitude, :station_longitude, 1, :created_at, :updated_at
        )
        """,
        {**values, "created_at": timestamp, "updated_at": timestamp},
    )
    return int(cur.lastrowid)


def delete_profile(conn: sqlite3.Connection, profile_id: int) -> None:
    conn.execute("DELETE FROM search_profiles WHERE id = ?", (profile_id,))


def list_profiles(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT *
            FROM search_profiles
            WHERE enabled = 1
            ORDER BY id DESC
            """
        )
    )


def get_profile(conn: sqlite3.Connection, profile_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM search_profiles
        WHERE id = ? AND enabled = 1
        """,
        (profile_id,),
    ).fetchone()


def list_recent_events(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT e.*, l.district, l.deal_type, l.address, l.building_name, l.detail_url
            FROM listing_events e
            JOIN listings l ON l.source_listing_id = e.source_listing_id
            ORDER BY e.event_at DESC, e.id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def list_unnotified_events_for_profiles(conn: sqlite3.Connection, channel: str = "telegram") -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                e.id AS event_id,
                e.source_listing_id,
                e.event_type,
                e.old_price_text,
                e.new_price_text,
                e.event_at,
                l.district,
                l.deal_type,
                l.address,
                l.building_name,
                l.area_text,
                l.room_text,
                l.move_in,
                l.price_text,
                l.agent_text,
                l.full_address,
                l.latitude,
                l.longitude,
                l.detail_url,
                p.id AS profile_id,
                p.name AS profile_name,
                p.district AS profile_district,
                p.deal_type AS profile_deal_type,
                p.deposit_min,
                p.deposit_max,
                p.rent_min,
                p.rent_max,
                p.sale_min,
                p.sale_max,
                p.area_min,
                p.area_max,
                p.keyword,
                p.built_year_min,
                p.station_name,
                p.radius_m,
                p.station_latitude,
                p.station_longitude,
                l.detail_json
            FROM listing_events e
            JOIN listings l ON l.source_listing_id = e.source_listing_id
            JOIN search_profiles p ON p.enabled = 1
            LEFT JOIN notification_logs n
                ON n.event_id = e.id
               AND n.profile_id = p.id
               AND n.channel = ?
            WHERE n.id IS NULL
            ORDER BY e.event_at ASC, e.id ASC, p.id ASC
            """,
            (channel,),
        )
    )


def record_notification(
    conn: sqlite3.Connection,
    event_id: int,
    profile_id: int,
    channel: str,
    status: str,
    error: str = "",
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO notification_logs (
            event_id, profile_id, channel, sent_at, status, error
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, profile_id, channel, now_iso(), status, error),
    )


def stats(conn: sqlite3.Connection) -> dict[str, object]:
    total = conn.execute("SELECT COUNT(*) AS c FROM listings").fetchone()["c"]
    by_district = conn.execute(
        "SELECT district, COUNT(*) AS c FROM listings GROUP BY district ORDER BY district"
    ).fetchall()
    last_run = conn.execute(
        "SELECT * FROM collection_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    event_counts = conn.execute(
        """
        SELECT event_type, COUNT(*) AS c
        FROM listing_events
        GROUP BY event_type
        ORDER BY event_type
        """
    ).fetchall()
    return {
        "total": total,
        "by_district": [dict(row) for row in by_district],
        "last_run": dict(last_run) if last_run else None,
        "event_counts": [dict(row) for row in event_counts],
    }
