from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

from .config import ARTICLE_URL, BASE_URL, OFFICETEL_CODE
from .text import clean_html, first_match


ROW_RE = re.compile(r'<tr id="tr_rowspantop_[^"]+".*?</tr>', re.I | re.S)
TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.I | re.S)
ID_RE = re.compile(r'value="(\d+)"|id=(\d+)', re.I)
HREF_RE = re.compile(r'href="([^"]*view\.php[^"]*id=\d+[^"]*)"', re.I)
TITLE_RE = re.compile(r'title="([^"]+)"', re.I)
PHONE_RE = re.compile(r'(?:0\d{1,2}-\d{3,4}-\d{4}|01\d-\d{3,4}-\d{4})')


@dataclass
class ListingSummary:
    source_listing_id: str
    district: str
    k_code: str
    deal_type: str
    address: str
    building_name: str
    area_text: str
    room_text: str
    move_in: str
    price_text: str
    registered_date: str
    agent_text: str
    agent_phone: str
    detail_url: str
    raw_hash: str


def parse_listing_rows(html: str, district: str, k_code: str = OFFICETEL_CODE) -> list[ListingSummary]:
    rows: list[ListingSummary] = []
    for raw_row in ROW_RE.findall(html):
        source_id = _extract_id(raw_row)
        if not source_id:
            continue
        href_match = HREF_RE.search(raw_row)
        detail_url = urljoin(ARTICLE_URL, href_match.group(1)) if href_match else f"{ARTICLE_URL}view.php?page=&id={source_id}"
        cells = [clean_html(cell) for cell in TD_RE.findall(raw_row)]
        cells = [cell for cell in cells]
        deal_type = _cell(cells, 1)
        address = _cell(cells, 2)
        building_name = _cell(cells, 3)
        area_text = _cell(cells, 5)
        if k_code == OFFICETEL_CODE:
            # Officetel rows include usage and move-in columns before room/price/date.
            room_text = _cell(cells, 8)
            move_in = _cell(cells, 7)
            price_text = _cell(cells, 9)
            registered_date = _cell(cells, 10)
            agent_text = _cell(cells, 11)
        else:
            room_text = _cell(cells, 6)
            move_in = _cell(cells, 7)
            price_text = _cell(cells, 8)
            registered_date = _cell(cells, 9)
            agent_text = _cell(cells, 10)
        phone_match = PHONE_RE.search(agent_text)
        rows.append(
            ListingSummary(
                source_listing_id=source_id,
                district=district,
                k_code=k_code,
                deal_type=deal_type.replace("급매물", "").replace("추천매물", "").strip(),
                address=address,
                building_name=building_name,
                area_text=area_text,
                room_text=room_text,
                move_in=move_in,
                price_text=price_text,
                registered_date=registered_date,
                agent_text=agent_text,
                agent_phone=phone_match.group(0) if phone_match else "",
                detail_url=detail_url,
                raw_hash=hashlib.sha256(raw_row.encode("utf-8", errors="ignore")).hexdigest(),
            )
        )
    return rows


def parse_detail(html: str) -> dict[str, str]:
    plain = clean_html(html)
    detail: dict[str, str] = {
        "raw_hash": hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest(),
        "listing_no": first_match(r"매물번호\s*:\s*<span[^>]*>(.*?)</span>", html),
        "full_address": _between(plain, "주소", "건물명"),
        "unit_text": _between_first(plain, "동/호수", ("가격정보",)),
        "price_info": _between(plain, "가격정보", "상세정보"),
        "usage_text": _between(plain, "용도", "공급면적"),
        "supply_area": _between(plain, "공급면적", "전용면적"),
        "exclusive_area": _between(plain, "전용면적", "입주가능일"),
        "available_date": _between(plain, "입주가능일", "해당층/총층"),
        "floor_text": _between_first(plain, "해당층/총층", ("건축년월", "방향/현관구조", "시설/옵션", "등록자확인일")),
        "built_date": _between(plain, "건축년월", "방향"),
        "direction": _between_any(plain, "방향/현관구조", ("시설/옵션", "등록자확인일")),
        "parking": _between(plain, "주차", "난방방식/연료"),
        "options": _between(plain, "기타시설", "시설/옵션"),
        "description": _description_text(plain),
        "complex_built_year": _between(plain, "준공년도", "총세대수"),
        "complex_parking": _complex_parking(plain),
        "confirmed_at": _between(plain, "등록자확인일", "최초등록일"),
        "first_registered_at": _between(plain, "최초등록일", "순위갱신"),
        "agent_office": _between(plain, "회사명", "쪽지보내기") or _between(plain, "회사명", "등록번호"),
        "agent_license_no": _between(plain, "등록번호", "소재지"),
        "agent_address": _between(plain, "소재지", "이름"),
        "agent_name": _between(plain, "이름", "연락처"),
        "agent_contact": _between(plain, "연락처", "※ 매물번호"),
    }
    return {key: value for key, value in detail.items() if value}


def _extract_id(raw_row: str) -> str:
    for match in ID_RE.finditer(raw_row):
        value = match.group(1) or match.group(2)
        if value:
            return value
    return ""


def _cell(cells: list[str], index: int) -> str:
    return cells[index] if index < len(cells) else ""


def _between(text: str, start: str, end: str) -> str:
    pattern = re.escape(start) + r"\s*(.*?)\s*" + re.escape(end)
    match = re.search(pattern, text, re.I | re.S)
    return re.sub(r"\s+", " ", match.group(1)).strip(" -:/") if match else ""


def _between_any(text: str, start: str, ends: tuple[str, ...]) -> str:
    for end in ends:
        value = _between(text, start, end)
        if value:
            return value
    return ""


def _between_first(text: str, start: str, ends: tuple[str, ...]) -> str:
    start_match = re.search(re.escape(start), text, re.I)
    if not start_match:
        return ""
    candidates: list[tuple[int, str]] = []
    for end in ends:
        end_match = re.search(re.escape(end), text[start_match.end():], re.I)
        if end_match:
            candidates.append((start_match.end() + end_match.start(), end))
    if not candidates:
        return ""
    end_pos, _ = min(candidates, key=lambda item: item[0])
    value = text[start_match.end():end_pos]
    return re.sub(r"\s+", " ", value).strip(" -:/")


def _complex_parking(text: str) -> str:
    match = re.search(r"총동수\s+\S+\s+주차\s*(.*?)\s*난방", text, re.I | re.S)
    if not match:
        return _between(text, "주차", "난방")
    return re.sub(r"\s+", " ", match.group(1)).strip(" -:/")


def _description_text(text: str) -> str:
    value = _between_first(text, "중개업소용 안내사항", ("매물댓글", "위치정보", "매물사진", "단지정보"))
    if not value:
        value = _between_first(text, "안내사항", ("매물댓글", "위치정보", "매물사진", "단지정보"))
    return value
