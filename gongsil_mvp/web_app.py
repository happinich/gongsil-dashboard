from __future__ import annotations

import html
import base64
import hmac
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from .config import DISTRICTS, load_settings
from .collector import collect_officetels
from .geocode import Geocoder
from .geocode import geocode_pending_listings
from .matcher import filter_listings, match_count
from .natural_query import parse_natural_query, summarize_natural_profile
from .notify import send_pending_telegram_alerts
from .storage import (
    connect,
    create_profile,
    delete_profile,
    get_profile,
    init_db,
    list_profiles,
    list_recent,
    stats,
)


DEAL_TYPES = ("", "매매", "전세", "월세", "단기")
DONG_FILTERS = ("삼성동", "대치동", "역삼동", "서초동")

CSS = """
:root { --ink:#17212b; --muted:#667085; --line:#dde3ea; --brand:#0f766e; --brand2:#9a5b13; --bg:#f6f1e8; --card:#fffaf2; --danger:#b42318; }
* { box-sizing: border-box; }
body { margin:0; color:var(--ink); background:radial-gradient(circle at top left,#d8efe8,transparent 34rem),linear-gradient(135deg,#f6f1e8,#efe6d4); font-family: ui-serif, Georgia, 'Times New Roman', serif; }
header { padding:32px 40px 18px; }
h1 { margin:0; font-size:34px; letter-spacing:-0.04em; }
main { padding:0 40px 48px; }
.card { background:rgba(255,250,242,.92); border:1px solid var(--line); border-radius:22px; box-shadow:0 18px 45px rgba(41,33,23,.08); padding:22px; margin-bottom:18px; }
.stats { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:18px; }
.stat { min-width:150px; padding:16px 18px; border-radius:18px; background:#fff; border:1px solid var(--line); }
.stat b { display:block; font-size:26px; }
.toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:18px 0; }
a, button { color:var(--brand); }
button { cursor:pointer; }
.filter a, .pill { display:inline-block; padding:8px 12px; border-radius:999px; text-decoration:none; border:1px solid var(--line); background:#fff; margin:0 6px 6px 0; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif; font-size:13px; }
.filter a.active, .pill.active { background:var(--brand); color:#fff; border-color:var(--brand); }
.grid { display:grid; grid-template-columns: repeat(6, minmax(100px, 1fr)); gap:10px; }
.field { display:flex; flex-direction:column; gap:5px; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif; font-size:12px; color:var(--muted); }
.field.wide { grid-column: span 2; }
input, select { width:100%; border:1px solid var(--line); border-radius:12px; padding:10px 11px; background:#fff; color:var(--ink); }
.actions { display:flex; align-items:flex-end; gap:8px; }
.primary { border:0; border-radius:14px; padding:11px 16px; background:var(--brand); color:#fff; font-weight:800; }
.ghost { border:1px solid var(--line); border-radius:14px; padding:9px 12px; background:#fff; color:var(--muted); }
.profile-list { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }
.profile-card { display:flex; align-items:center; gap:10px; padding:10px 12px; border:1px solid var(--line); background:#fff; border-radius:16px; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif; }
.profile-card.active { border-color:var(--brand); box-shadow:0 0 0 3px rgba(15,118,110,.12); }
.profile-card form { margin:0; }
.delete { border:0; background:transparent; color:var(--danger); padding:2px 4px; }
table { width:100%; border-collapse:separate; border-spacing:0 8px; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif; }
th { text-align:left; color:var(--muted); font-size:12px; font-weight:700; padding:0 10px; }
td { background:#fff; border-top:1px solid var(--line); border-bottom:1px solid var(--line); padding:12px 10px; vertical-align:top; font-size:13px; }
td:first-child { border-left:1px solid var(--line); border-radius:14px 0 0 14px; }
td:last-child { border-right:1px solid var(--line); border-radius:0 14px 14px 0; }
tr[data-detail-row] td { cursor:pointer; }
tr[data-detail-row]:hover td { background:#f8fff9; }
.small { color:var(--muted); font-size:12px; }
.price { font-weight:800; color:var(--danger); }
.empty { padding:32px; text-align:center; color:var(--muted); }
.listing-detail summary { cursor:pointer; color:var(--brand); font-weight:800; }
.detail-grid { display:grid; grid-template-columns: repeat(4, minmax(130px, 1fr)); gap:8px; margin-top:10px; padding:12px; border:1px solid var(--line); border-radius:12px; background:#fffaf2; }
.detail-item { color:var(--muted); font-size:12px; }
.detail-item b { display:block; color:var(--ink); font-size:13px; margin-top:3px; overflow-wrap:anywhere; }
.detail-item.wide { grid-column: span 2; }
.detail-item.full { grid-column: 1 / -1; }
code { background:#fff; padding:2px 5px; border-radius:6px; border:1px solid var(--line); }
.notice { margin-bottom:12px; padding:12px 14px; border-radius:14px; background:#eef8f5; border:1px solid #b7ddd2; color:#0f766e; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif; font-size:13px; }
.suggestions { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
.suggestion { padding:12px 14px; border:1px solid var(--line); border-radius:16px; background:#fff; min-width:220px; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif; }
.suggestion strong { display:block; margin-bottom:4px; }
.search-block { padding:0; border-top:1px solid var(--line); }
.search-block:first-of-type { border-top:0; }
.search-block summary { display:flex; align-items:center; justify-content:space-between; gap:12px; cursor:pointer; list-style:none; padding:16px 0; font-size:18px; font-weight:800; }
.search-block summary::-webkit-details-marker { display:none; }
.search-block summary::after { content:"+"; display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; border-radius:999px; border:1px solid var(--line); background:#fff; color:var(--brand); font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif; }
.search-block[open] summary::after { content:"-"; }
.search-body { padding:0 0 18px; }
.loading-banner { display:none; margin-bottom:12px; padding:12px 14px; border-radius:14px; background:#fff7e8; border:1px solid #f0c98e; color:#9a5b13; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif; font-size:13px; }
.primary[disabled] { opacity:.65; cursor:progress; }
@media (max-width: 980px) { .grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); } .field.wide { grid-column: span 2; } }
@media (max-width: 860px) { header, main { padding-left:18px; padding-right:18px; } table { display:block; overflow:auto; } h1 { font-size:28px; } .toolbar { align-items:flex-start; flex-direction:column; } }
"""


class DashboardHandler(BaseHTTPRequestHandler):
    db_path: Path
    settings: object

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send_json({"ok": True})
            return
        if not self._is_authorized():
            self._request_auth()
            return
        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        query = parse_qs(parsed.query)
        district = query.get("district", [""])[0]
        if district not in DISTRICTS:
            district = ""
        dong = query.get("dong", [""])[0]
        if dong not in DONG_FILTERS:
            dong = ""
        profile_id = _as_int(query.get("profile_id", [""])[0])
        flash = query.get("flash", [""])[0]
        settings = load_settings(require_credentials=False)
        complex_name = query.get("complex", [""])[0]
        if complex_name not in settings.complex_names:
            complex_name = ""
        deal_filter = query.get("deal", [""])[0]
        if deal_filter not in DEAL_TYPES:
            deal_filter = ""

        init_db(self.db_path)
        with connect(self.db_path) as conn:
            page_stats = stats(conn)
            profiles = list_profiles(conn)
            selected_profile = get_profile(conn, profile_id) if profile_id else None
            source_district = selected_profile["district"] if selected_profile and selected_profile["district"] else district
            source_rows = list_recent(conn, limit=1000, district=source_district or "")
            source_rows = filter_dong_rows(source_rows, dong)
            rows = filter_listings(selected_profile, source_rows)
            complex_counts = count_complexes(source_rows, settings.complex_names)
            rows = filter_complex_rows(rows, complex_name)
            deal_counts = count_deals(rows)
            rows = filter_deal_rows(rows, deal_filter)
            all_rows = list_recent(conn, limit=1000)
            all_rows = filter_dong_rows(all_rows, "")
            page_stats = with_target_stats(page_stats, all_rows)
            counts = {profile["id"]: match_count(profile, all_rows) for profile in profiles}
        self._send_html(
            render_dashboard(
                page_stats,
                rows,
                district,
                dong,
                complex_name,
                deal_filter,
                profiles,
                selected_profile,
                counts,
                flash,
                settings.complex_names,
                complex_counts,
                deal_counts,
            )
        )

    def do_POST(self) -> None:
        if not self._is_authorized():
            self._request_auth()
            return
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        fields = {key: values[0] for key, values in parse_qs(body).items()}
        init_db(self.db_path)

        if parsed.path == "/profiles":
            values = normalize_profile_fields(fields)
            values = enrich_profile_with_station(values)
            with connect(self.db_path) as conn:
                profile_id = create_profile(conn, values)
            self._redirect(f"/?profile_id={profile_id}")
            return
        if parsed.path == "/profiles/natural":
            query_text = fields.get("natural_query", "").strip()
            if not query_text:
                self._redirect("/?" + urlencode({"flash": "검색 문장을 입력해 주세요."}))
                return
            values = parse_natural_query(query_text)
            values = enrich_profile_with_station(values)
            with connect(self.db_path) as conn:
                profile_id = create_profile(conn, values)
            flash = "말로 찾기 조건 저장: " + summarize_natural_profile(values)
            self._redirect("/?" + urlencode({"profile_id": profile_id, "flash": flash}))
            return
        if parsed.path == "/profiles/delete":
            profile_id = _as_int(fields.get("profile_id", ""))
            if profile_id:
                with connect(self.db_path) as conn:
                    delete_profile(conn, profile_id)
            self._redirect("/")
            return
        if parsed.path == "/refresh":
            settings = load_settings(require_credentials=False)
            profile_id = _as_int(fields.get("profile_id", ""))
            max_pages = _as_int(fields.get("max_pages", "")) or settings.default_max_pages
            do_notify = fields.get("notify", "") == "1"
            flash = run_refresh(settings, max_pages=max_pages, notify=do_notify)
            target = "/?" + urlencode({"profile_id": profile_id, "flash": flash}) if profile_id else "/?" + urlencode({"flash": flash})
            self._redirect(target)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _is_authorized(self) -> bool:
        password = getattr(self.settings, "dashboard_password", "")
        if not password:
            return True
        header = self.headers.get("Authorization", "")
        prefix = "Basic "
        if not header.startswith(prefix):
            return False
        try:
            decoded = base64.b64decode(header[len(prefix):]).decode("utf-8")
            username, supplied_password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        expected_user = getattr(self.settings, "dashboard_user", "admin")
        return hmac.compare_digest(username, expected_user) and hmac.compare_digest(supplied_password, password)

    def _request_auth(self) -> None:
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="Gongsil Dashboard"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Authentication required.".encode("utf-8"))

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, body: dict[str, object]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def normalize_profile_fields(fields: dict[str, str]) -> dict[str, object]:
    name = fields.get("name", "").strip() or "새 조건"
    district = fields.get("district", "").strip()
    deal_type = fields.get("deal_type", "").strip()
    if district not in ("", *DISTRICTS):
        district = ""
    if deal_type not in DEAL_TYPES:
        deal_type = ""
    return {
        "name": name[:60],
        "district": district,
        "deal_type": deal_type,
        "deposit_min": _optional_int(fields.get("deposit_min", "")),
        "deposit_max": _optional_int(fields.get("deposit_max", "")),
        "rent_min": _optional_int(fields.get("rent_min", "")),
        "rent_max": _optional_int(fields.get("rent_max", "")),
        "sale_min": _optional_int(fields.get("sale_min", "")),
        "sale_max": _optional_int(fields.get("sale_max", "")),
        "area_min": _optional_float(fields.get("area_min", "")),
        "area_max": _optional_float(fields.get("area_max", "")),
        "keyword": fields.get("keyword", "").strip()[:80],
        "built_year_min": _optional_int(fields.get("built_year_min", "")),
        "station_name": fields.get("station_name", "").strip()[:40],
        "radius_m": _optional_int(fields.get("radius_m", "")),
        "station_latitude": None,
        "station_longitude": None,
    }


def enrich_profile_with_station(values: dict[str, object]) -> dict[str, object]:
    station_name = values.get("station_name") or ""
    if not station_name:
        return values
    geocoder = Geocoder(load_settings(require_credentials=False))
    point = geocoder.geocode_station(str(station_name))
    if point:
        values["station_latitude"] = point.latitude
        values["station_longitude"] = point.longitude
    return values


def render_dashboard(
    page_stats: dict[str, object],
    rows: list[object],
    district: str,
    dong: str,
    complex_name: str,
    deal_filter: str,
    profiles: list[object],
    selected_profile: object | None,
    counts: dict[int, int],
    flash: str,
    complex_names: tuple[str, ...],
    complex_counts: dict[str, int],
    deal_counts: dict[str, int],
) -> str:
    by_district = {item["district"]: item["c"] for item in page_stats.get("by_district", [])}
    by_dong = {item["dong"]: item["c"] for item in page_stats.get("by_dong", [])}
    by_event = {item["event_type"]: item["c"] for item in page_stats.get("event_counts", [])}
    last_run = page_stats.get("last_run") or {}
    profile_id = selected_profile["id"] if selected_profile else 0
    dong_links = ['<a class="{}" href="/" data-listing-filter>전체</a>'.format("active" if not dong and not profile_id else "")]
    for item in DONG_FILTERS:
        dong_links.append(
            '<a class="{}" href="{}" data-listing-filter>{} <span class="small">({})</span></a>'.format(
                "active" if dong == item and not profile_id else "",
                html.escape(listing_filter_url(dong=item)),
                html.escape(item),
                by_dong.get(item, 0),
            )
        )
    complex_links = render_complex_filter_links(dong, complex_name, complex_names, complex_counts)
    deal_links = render_deal_filter_links(dong, complex_name, deal_filter, deal_counts)
    subtitle = render_listing_subtitle(selected_profile, dong, complex_name, deal_filter)
    suggestions = build_profile_suggestions(selected_profile, len(rows))
    table_rows = "".join(render_row(row) for row in rows) or '<tr><td class="empty" colspan="10">조건에 맞는 매물이 없습니다. 조건을 넓히거나 수집 범위를 늘려보세요.</td></tr>'
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>공실 오피스텔 매물 MVP</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="small">Gangnam / Seocho Officetel Finder</div>
  <h1>공실닷컴 오피스텔 매물 대시보드</h1>
</header>
<main>
  <section id="stats-section" class="stats">
    <div class="stat"><span class="small">전체 저장</span><b>{page_stats.get('total', 0)}</b></div>
    <div class="stat"><span class="small">삼성동</span><b>{by_dong.get('삼성동', 0)}</b></div>
    <div class="stat"><span class="small">대치동</span><b>{by_dong.get('대치동', 0)}</b></div>
    <div class="stat"><span class="small">역삼동</span><b>{by_dong.get('역삼동', 0)}</b></div>
    <div class="stat"><span class="small">서초동</span><b>{by_dong.get('서초동', 0)}</b></div>
    <div class="stat"><span class="small">현재 표시</span><b>{len(rows)}</b></div>
    <div class="stat"><span class="small">신규 이벤트</span><b>{by_event.get('new_listing', 0)}</b></div>
    <div class="stat"><span class="small">가격 변경</span><b>{by_event.get('price_changed', 0)}</b></div>
    <div class="stat"><span class="small">마지막 수집</span><b style="font-size:14px">{html.escape(str(last_run.get('finished_at') or '없음'))}</b></div>
  </section>
  <section class="card">
    <h2 style="margin:0 0 12px">검색</h2>
    {render_search_panel(selected_profile, profiles, counts, flash, complex_names)}
  </section>
  {suggestions}
  <section id="listings-section" class="card">
    <div class="toolbar">
      <div>
        <div class="filter">{''.join(dong_links)}</div>
        {complex_links}
        {deal_links}
        <div class="small">{subtitle}</div>
      </div>
      <div class="small">수집: <code>python3 scripts/collect_officetels.py --max-pages 2</code></div>
    </div>
    <table>
      <thead><tr><th>구</th><th>거래</th><th>주소</th><th>건물명</th><th>면적</th><th>방/입주</th><th>금액</th><th>등록일</th><th>등록자</th><th>상세</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </section>
</main>
<script>
document.addEventListener("DOMContentLoaded", function () {{
  const refreshForm = document.querySelector('form[action="/refresh"]');
  if (refreshForm) {{
    refreshForm.addEventListener("submit", function () {{
      const button = refreshForm.querySelector('button[type="submit"]');
      const banner = document.getElementById("refresh-loading");
      if (button) {{
        button.disabled = true;
        button.textContent = "검색 진행 중...";
      }}
      if (banner) {{
        banner.style.display = "block";
      }}
    }});
  }}

  function bindListingFilters() {{
    document.querySelectorAll("[data-listing-filter]").forEach(function (link) {{
      link.addEventListener("click", function (event) {{
        event.preventDefault();
        const href = link.getAttribute("href");
        if (!href) return;
        const scrollTop = window.scrollY;
        fetch(href, {{ headers: {{ "X-Requested-With": "fetch" }} }})
          .then(function (response) {{ return response.text(); }})
          .then(function (htmlText) {{
            const doc = new DOMParser().parseFromString(htmlText, "text/html");
            const nextStats = doc.getElementById("stats-section");
            const nextListings = doc.getElementById("listings-section");
            const stats = document.getElementById("stats-section");
            const listings = document.getElementById("listings-section");
            if (nextStats && stats) stats.innerHTML = nextStats.innerHTML;
            if (nextListings && listings) listings.innerHTML = nextListings.innerHTML;
            window.history.pushState({{}}, "", href);
            bindListingFilters();
            bindListingDetailRows();
            window.scrollTo({{ top: scrollTop }});
          }})
          .catch(function () {{
            window.location.href = href;
          }});
      }});
    }});
  }}
  bindListingFilters();
  function bindListingDetailRows() {{
    document.querySelectorAll("tr[data-detail-row]").forEach(function (row) {{
      row.addEventListener("click", function (event) {{
        if (event.target.closest("summary") || event.target.closest(".detail-grid")) return;
        const detail = row.querySelector("details.listing-detail");
        if (detail) detail.open = !detail.open;
      }});
    }});
  }}
  bindListingDetailRows();
  window.addEventListener("popstate", function () {{
    window.location.reload();
  }});
}});
</script>
</body>
</html>"""


def render_search_panel(
    selected_profile: object | None,
    profiles: list[object],
    counts: dict[int, int],
    flash: str,
    complex_names: tuple[str, ...],
) -> str:
    return f"""
<details class="search-block">
  <summary>지금 다시 검색</summary>
  <div class="search-body">{render_refresh_form(selected_profile, flash, complex_names)}</div>
</details>
<details class="search-block" open>
  <summary>말로 검색</summary>
  <div class="search-body">
    <div class="small" style="margin-bottom:12px">예: 강남역 6~8평 오피스텔 10년 이내 신축급 100만원 이하 월세 매물 찾아줘</div>
    {render_natural_query_form()}
  </div>
</details>
<details class="search-block">
  <summary>상세 조건</summary>
  <div class="search-body">
    {render_profile_form()}
    {render_profile_list(profiles, selected_profile, counts)}
  </div>
</details>"""


def render_complex_filter_links(
    dong: str,
    selected_complex: str,
    complex_names: tuple[str, ...],
    complex_counts: dict[str, int],
) -> str:
    links = [
        '<a class="{}" href="{}" data-listing-filter>단지 전체</a>'.format(
            "active" if not selected_complex else "",
            html.escape(listing_filter_url(dong=dong)),
        )
    ]
    for name in complex_names:
        count = complex_counts.get(name, 0)
        if count <= 0:
            continue
        links.append(
            '<a class="{}" href="{}" data-listing-filter>{} <span class="small">({})</span></a>'.format(
                "active" if selected_complex == name else "",
                html.escape(listing_filter_url(dong=dong, complex_name=name)),
                html.escape(name),
                count,
            )
        )
    if len(links) == 1:
        return ""
    return '<div class="filter" style="margin-top:8px">' + "".join(links) + "</div>"


def render_deal_filter_links(
    dong: str,
    selected_complex: str,
    selected_deal: str,
    deal_counts: dict[str, int],
) -> str:
    links = [
        '<a class="{}" href="{}" data-listing-filter>거래 전체</a>'.format(
            "active" if not selected_deal else "",
            html.escape(listing_filter_url(dong=dong, complex_name=selected_complex)),
        )
    ]
    for deal_type in DEAL_TYPES:
        if not deal_type:
            continue
        count = deal_counts.get(deal_type, 0)
        if count <= 0:
            continue
        links.append(
            '<a class="{}" href="{}" data-listing-filter>{} <span class="small">({})</span></a>'.format(
                "active" if selected_deal == deal_type else "",
                html.escape(listing_filter_url(dong=dong, complex_name=selected_complex, deal_filter=deal_type)),
                html.escape(deal_type),
                count,
            )
        )
    return '<div class="filter" style="margin-top:8px">' + "".join(links) + "</div>"


def render_listing_subtitle(
    selected_profile: object | None,
    dong: str,
    complex_name: str,
    deal_filter: str,
) -> str:
    if selected_profile:
        return render_selected_summary(selected_profile)
    parts = []
    if dong:
        parts.append(f"{dong} 매물")
    else:
        parts.append("관심 동 전체 매물")
    if complex_name:
        parts.append(complex_name)
    if deal_filter:
        parts.append(deal_filter)
    return " · ".join(parts)


def render_refresh_form(selected_profile: object | None, flash: str, complex_names: tuple[str, ...]) -> str:
    profile_id = selected_profile["id"] if selected_profile else 0
    flash_html = f'<div class="notice">{html.escape(flash)}</div>' if flash else ""
    complex_list = ", ".join(complex_names)
    return f"""
{flash_html}
<div id="refresh-loading" class="loading-banner">공실닷컴에서 최신 매물을 다시 수집하고 있습니다. 페이지를 유지한 채 잠시 기다려 주세요.</div>
<form method="post" action="/refresh">
  <input type="hidden" name="profile_id" value="{profile_id}">
  <div class="grid">
    <label class="field">페이지 수<input name="max_pages" inputmode="numeric" placeholder="예: 1" value="1"></label>
    <label class="field wide">관심 단지<div class="small" style="padding-top:10px">{html.escape(complex_list)}</div></label>
    <label class="field">텔레그램 알림<select name="notify"><option value="0" selected>끄기</option><option value="1">켜기</option></select></label>
    <div class="actions"><button class="primary" type="submit">지금 다시 검색</button></div>
  </div>
</form>"""


def build_profile_suggestions(profile: object | None, match_count_value: int) -> str:
    if profile is None:
        return ""
    suggestions: list[tuple[str, str]] = []
    if match_count_value == 0:
        if profile["radius_m"] is not None:
            suggestions.append(("반경 넓히기", f"현재 {profile['radius_m']}m입니다. 1000m 또는 1500m까지 넓혀보세요."))
        if profile["rent_max"] is not None:
            suggestions.append(("월세 조건 완화", f"현재 월세 최대 {profile['rent_max']}입니다. 150 또는 200까지 열어보면 결과가 늘 수 있습니다."))
        if profile["built_year_min"] is not None:
            suggestions.append(("준공연도 완화", f"현재 {profile['built_year_min']}년 이후입니다. 준공연도 조건을 비우거나 3~5년 넓혀보세요."))
        if profile["station_name"]:
            suggestions.append(("역 조건 잠시 제외", f"{profile['station_name']} 반경 조건을 빼고 먼저 주변 동네 매물을 확인해보세요."))
        if profile["keyword"]:
            suggestions.append(("키워드 단순화", "건물명/옵션 키워드가 너무 좁으면 비우고 먼저 범위를 넓혀보세요."))
    elif match_count_value < 5:
        suggestions.append(("페이지 수 늘리기", "지금 다시 검색에서 페이지 수를 5~10으로 올리면 최신 매물을 더 넓게 가져올 수 있습니다."))
        if profile["radius_m"] is not None:
            suggestions.append(("반경 소폭 완화", f"현재 {profile['radius_m']}m입니다. 200~300m만 넓혀도 결과가 늘 수 있습니다."))
    if not suggestions:
        return ""
    cards = "".join(
        f'<div class="suggestion"><strong>{html.escape(title)}</strong><div class="small">{html.escape(body)}</div></div>'
        for title, body in suggestions
    )
    return '<div class="card"><h2 style="margin:0 0 12px">조건 추천</h2><div class="small">현재 조건 기준으로 더 잘 찾기 위한 추천입니다.</div><div class="suggestions">' + cards + "</div></div>"


def render_natural_query_form() -> str:
    return """
<form method="post" action="/profiles/natural">
  <div class="grid">
    <label class="field wide" style="grid-column: span 5">찾고 싶은 조건<input name="natural_query" placeholder="예: 강남역 6~8평 오피스텔 10년 이내 신축급 100만원 이하 월세 매물 찾아줘" required></label>
    <div class="actions"><button class="primary" type="submit">조건 만들기</button></div>
  </div>
</form>"""


def render_profile_form() -> str:
    district_options = _options(["", *DISTRICTS], "", empty_label="전체")
    deal_options = _options(DEAL_TYPES, "", empty_label="전체")
    return f"""
<form method="post" action="/profiles">
  <div class="grid">
    <label class="field wide">조건 이름<input name="name" placeholder="예: 강남 월세 500 이하" required></label>
    <label class="field">지역<select name="district">{district_options}</select></label>
    <label class="field">거래<select name="deal_type">{deal_options}</select></label>
    <label class="field">키워드<input name="keyword" placeholder="건물명/동/옵션"></label>
    <label class="field">역명<input name="station_name" placeholder="예: 선릉역"></label>
    <label class="field">반경(m)<input name="radius_m" inputmode="numeric" placeholder="예: 700"></label>
    <label class="field">보증금 최소<input name="deposit_min" inputmode="numeric" placeholder="만원"></label>
    <label class="field">보증금 최대<input name="deposit_max" inputmode="numeric" placeholder="만원"></label>
    <label class="field">월세 최소<input name="rent_min" inputmode="numeric" placeholder="만원"></label>
    <label class="field">월세 최대<input name="rent_max" inputmode="numeric" placeholder="만원"></label>
    <label class="field">매매가 최소<input name="sale_min" inputmode="numeric" placeholder="만원"></label>
    <label class="field">매매가 최대<input name="sale_max" inputmode="numeric" placeholder="만원"></label>
    <label class="field">평수 최소<input name="area_min" inputmode="decimal" placeholder="평"></label>
    <label class="field">평수 최대<input name="area_max" inputmode="decimal" placeholder="평"></label>
    <label class="field">준공연도 최소<input name="built_year_min" inputmode="numeric" placeholder="예: 2017"></label>
    <div class="actions"><button class="primary" type="submit">조건 저장</button></div>
  </div>
</form>"""


def render_profile_list(profiles: list[object], selected_profile: object | None, counts: dict[int, int]) -> str:
    if not profiles:
        return '<div class="small" style="margin-top:14px">아직 저장된 조건이 없습니다. 자주 찾는 조건을 저장해두면 다음 단계 알림 기능에 그대로 사용할 수 있습니다.</div>'
    selected_id = selected_profile["id"] if selected_profile else 0
    cards = []
    for profile in profiles:
        profile_id = profile["id"]
        href = "/?" + urlencode({"profile_id": profile_id})
        summary = compact_profile_summary(profile)
        cards.append(
            f"""
<div class="profile-card {'active' if selected_id == profile_id else ''}">
  <a href="{href}" style="text-decoration:none;color:inherit"><strong>{html.escape(profile['name'])}</strong> <span class="small">({counts.get(profile_id, 0)}건)</span><div class="small">{html.escape(summary)}</div></a>
  <form method="post" action="/profiles/delete"><input type="hidden" name="profile_id" value="{profile_id}"><button class="delete" title="삭제">삭제</button></form>
</div>"""
        )
    return '<div class="profile-list">' + "".join(cards) + "</div>"


def compact_profile_summary(profile: object) -> str:
    parts = []
    for key, label in (("district", "지역"), ("deal_type", "거래"), ("keyword", "키워드"), ("station_name", "역")):
        if profile[key]:
            parts.append(f"{label}:{profile[key]}")
    ranges = [
        ("deposit_min", "deposit_max", "보증금"),
        ("rent_min", "rent_max", "월세"),
        ("sale_min", "sale_max", "매매가"),
        ("area_min", "area_max", "평수"),
    ]
    if profile['radius_m'] is not None:
        parts.append(f"반경:{profile['radius_m']}m")
    if profile["built_year_min"] is not None:
        parts.append(f"준공:{profile['built_year_min']}년 이후")
    for min_key, max_key, label in ranges:
        if profile[min_key] is not None or profile[max_key] is not None:
            parts.append(f"{label}:{profile[min_key] or ''}~{profile[max_key] or ''}")
    return " / ".join(parts) or "전체 조건"


def render_selected_summary(profile: object | None) -> str:
    if profile is None:
        return ""
    return f"선택 조건: {html.escape(profile['name'])} · {html.escape(compact_profile_summary(profile))}"


def render_row(row: object) -> str:
    get = row.__getitem__
    detail_html = render_detail_panel(get("detail_json") or "")
    return f"""
<tr data-detail-row>
  <td>{html.escape(get('district') or '')}</td>
  <td>{html.escape(get('deal_type') or '')}</td>
  <td>{html.escape(get('address') or '')}</td>
  <td>{html.escape(get('building_name') or '')}<div class="small">ID {html.escape(get('source_listing_id') or '')}</div></td>
  <td>{html.escape(get('area_text') or '')}</td>
  <td>{html.escape(get('room_text') or '')}<div class="small">{html.escape(get('move_in') or '')}</div></td>
  <td class="price">{html.escape(get('price_text') or '')}</td>
  <td>{html.escape(get('registered_date') or '')}</td>
  <td>{html.escape(get('agent_text') or '')}</td>
  <td>{detail_html}</td>
</tr>"""


def render_detail_panel(detail_json: str) -> str:
    if not detail_json:
        return '<span class="small">상세 미수집</span>'
    try:
        detail = json.loads(detail_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return '<span class="small">상세 오류</span>'
    items = [
        ("매물번호", detail.get("listing_no")),
        ("동/호수", _display_detail_value(detail.get("unit_text"))),
        ("해당층/총층", _display_detail_value(detail.get("floor_text"))),
        ("방향", _display_detail_value(detail.get("direction"))),
        ("가격정보", detail.get("price_info")),
        ("용도", detail.get("usage_text")),
        ("공급면적", detail.get("supply_area")),
        ("전용/입주", detail.get("available_date")),
        ("상세설명", detail.get("description")),
        ("준공년도", detail.get("complex_built_year") or detail.get("built_date")),
        ("주차", detail.get("complex_parking") or detail.get("parking")),
        ("확인일", detail.get("confirmed_at")),
        ("최초등록", detail.get("first_registered_at")),
        ("중개사", detail.get("agent_office")),
        ("담당자", detail.get("agent_name")),
        ("연락처", detail.get("agent_contact")),
        ("소재지", detail.get("agent_address")),
    ]
    cells = "".join(
        '<div class="detail-item {}">{}<b>{}</b></div>'.format(
            "full" if label == "상세설명" else ("wide" if label in {"가격정보", "전용/입주", "소재지"} else ""),
            html.escape(label),
            html.escape(str(value or "-")),
        )
        for label, value in items
    )
    return f'<details class="listing-detail"><summary>상세 보기</summary><div class="detail-grid">{cells}</div></details>'


def _display_detail_value(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "미공개"


def _options(values: tuple[str, ...] | list[str], selected: str, empty_label: str = "") -> str:
    rendered = []
    for value in values:
        label = empty_label if value == "" else value
        rendered.append(
            '<option value="{}"{}>{}</option>'.format(
                html.escape(value), " selected" if value == selected else "", html.escape(label)
            )
        )
    return "".join(rendered)


def _optional_int(value: str) -> int | None:
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _optional_float(value: str) -> float | None:
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _as_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def run_refresh(settings: object, max_pages: int, notify: bool) -> str:
    if not getattr(settings, "username", "") or not getattr(settings, "password", ""):
        return "GONGSIL_ID 또는 GONGSIL_PASSWORD가 설정되지 않아 재수집을 실행하지 못했습니다."
    results = collect_officetels(
        settings=settings,
        districts=settings.collection_districts,
        max_pages=max(1, max_pages),
        fetch_details=True,
        complex_names=settings.complex_names,
    )
    success, failed = geocode_pending_listings(settings, limit=200)
    flash = (
        "재수집 완료: "
        + ", ".join(
            f"{result.district} seen={result.listings_seen} new={result.new_listings} price_changes={result.price_changes}"
            if not result.complex_name
            else f"{result.district}/{result.complex_name} seen={result.listings_seen} new={result.new_listings} price_changes={result.price_changes}"
            for result in results
        )
        + f" / geocode success={success} failed={failed}"
    )
    if notify:
        notify_result = send_pending_telegram_alerts(settings)
        flash += (
            f" / telegram sent={notify_result.sent}"
            f" skipped={notify_result.skipped} failed={notify_result.failed}"
        )
    return flash


def listing_filter_url(dong: str = "", complex_name: str = "", deal_filter: str = "") -> str:
    params = {}
    if dong:
        params["dong"] = dong
    if complex_name:
        params["complex"] = complex_name
    if deal_filter:
        params["deal"] = deal_filter
    return "/?" + urlencode(params) if params else "/"


def filter_dong_rows(rows: list[object], dong: str) -> list[object]:
    allowed = {dong} if dong else set(DONG_FILTERS)
    return [row for row in rows if (row["address"] or "") in allowed]


def filter_complex_rows(rows: list[object], complex_name: str) -> list[object]:
    if not complex_name:
        return rows
    return [row for row in rows if complex_name in (row["building_name"] or "")]


def filter_deal_rows(rows: list[object], deal_filter: str) -> list[object]:
    if not deal_filter:
        return rows
    return [row for row in rows if (row["deal_type"] or "") == deal_filter]


def count_complexes(rows: list[object], complex_names: tuple[str, ...]) -> dict[str, int]:
    counts = {name: 0 for name in complex_names}
    for row in rows:
        building_name = row["building_name"] or ""
        for name in complex_names:
            if name in building_name:
                counts[name] += 1
                break
    return counts


def count_deals(rows: list[object]) -> dict[str, int]:
    counts = {deal_type: 0 for deal_type in DEAL_TYPES if deal_type}
    for row in rows:
        deal_type = row["deal_type"] or ""
        if deal_type in counts:
            counts[deal_type] += 1
    return counts


def with_target_stats(page_stats: dict[str, object], rows: list[object]) -> dict[str, object]:
    by_district: dict[str, int] = {}
    by_dong: dict[str, int] = {}
    for row in rows:
        district = row["district"] or ""
        by_district[district] = by_district.get(district, 0) + 1
        dong = row["address"] or ""
        by_dong[dong] = by_dong.get(dong, 0) + 1
    return {
        **page_stats,
        "total": len(rows),
        "by_district": [
            {"district": district, "c": count}
            for district, count in sorted(by_district.items())
        ],
        "by_dong": [
            {"dong": dong, "c": by_dong.get(dong, 0)}
            for dong in DONG_FILTERS
        ],
    }


def main() -> None:
    settings = load_settings(require_credentials=False)
    init_db(settings.db_path)
    DashboardHandler.db_path = settings.db_path
    DashboardHandler.settings = settings
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard: http://{host}:{port}")
    print(f"Database: {settings.db_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()
