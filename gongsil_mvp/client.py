from __future__ import annotations

import http.cookiejar
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .config import ARTICLE_URL, BASE_URL, DEFAULT_PAGE_SIZE, LOGIN_URL, OFFICETEL_CODE, SEOUL_CODE
from .text import decode_euc_kr


@dataclass
class GongsilClient:
    username: str
    password: str

    def __post_init__(self) -> None:
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X) GongsilInternalMVP/0.1"),
            ("Referer", BASE_URL + "/"),
        ]

    def get(self, url: str) -> str:
        with self.opener.open(url, timeout=30) as response:
            return decode_euc_kr(response.read())

    def post_form(self, url: str, fields: dict[str, str]) -> str:
        body = urllib.parse.urlencode(fields, encoding="euc-kr").encode("ascii")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with self.opener.open(request, timeout=30) as response:
            return decode_euc_kr(response.read())

    def login(self) -> None:
        self.get(BASE_URL + "/")
        self.post_form(
            LOGIN_URL,
            {
                "url": BASE_URL,
                "mb_id": self.username,
                "mb_password": self.password,
                "save_id": "1",
            },
        )
        html = self.get(ARTICLE_URL)
        if self.username not in html and "로그아웃" not in html:
            raise RuntimeError("Gongsil login did not appear to succeed.")

    def listing_url(
        self,
        district: str,
        page_no: int = 0,
        page_size: int = DEFAULT_PAGE_SIZE,
        **filters: str,
    ) -> str:
        params: dict[str, str | int] = {
            "k_code": OFFICETEL_CODE,
            "k_ad1": SEOUL_CODE,
            "k_ad2": district,
            "page_size": page_size,
            "page_no": page_no,
        }
        for key, value in filters.items():
            if value not in (None, ""):
                params[key] = value
        return ARTICLE_URL + "?" + urllib.parse.urlencode(params, encoding="euc-kr")

    def fetch_listing_page(self, district: str, page_no: int = 0, **filters: str) -> str:
        return self.get(self.listing_url(district=district, page_no=page_no, **filters))

    def fetch_detail(self, source_listing_id: str) -> str:
        url = urllib.parse.urljoin(ARTICLE_URL, f"view.php?page=&id={source_listing_id}")
        return self.get(url)
