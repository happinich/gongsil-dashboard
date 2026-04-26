#!/usr/bin/env python3
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib import request
from urllib.parse import urljoin

from playwright.sync_api import BrowserContext, Page, Route, TimeoutError, sync_playwright


BASE_URL = "https://www.gongsil.com"
LOGIN_URL = f"{BASE_URL}/h/member/login.php"
RECRUIT_URL = f"{BASE_URL}/bbs/recruit"
OUTPUT_DIR = Path(__file__).resolve().parent / "artifacts"


def getenv_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def getenv_optional(name: str) -> str:
    return os.getenv(name, "").strip()


def install_submit_guard(context: BrowserContext, allow_insert: bool = False) -> None:
    blocked_patterns = ("insert.php", "delete.php")

    def guard(route: Route) -> None:
        url = route.request.url.lower()
        is_insert = "insert.php" in url
        should_block = any(pat in url for pat in blocked_patterns)
        if allow_insert and is_insert:
            should_block = False
        if route.request.method.upper() == "POST" and should_block:
            print(f"[guard] blocked dangerous request: {route.request.method} {route.request.url}")
            route.abort()
            return
        route.continue_()

    context.route("**/*", guard)


def install_client_side_guard(page: Page, allow_insert: bool = False) -> None:
    dangerous_action = "(?:delete)\\.php" if allow_insert else "(?:insert|delete)\\.php"
    page.add_init_script(
        """
        (dangerousPattern => {
          const dangerousAction = new RegExp(dangerousPattern, "i");
          const block = (reason) => {
            window.__dry_run_blocked = reason;
            console.warn("[dry-run] blocked action:", reason);
            return false;
          };

          document.addEventListener("submit", (event) => {
            const form = event.target;
            const action = form && form.action ? form.action : "";
            if (dangerousAction.test(action)) {
              event.preventDefault();
              event.stopPropagation();
              block(`form submit blocked: ${action}`);
            }
          }, true);

          const originalSubmit = HTMLFormElement.prototype.submit;
          HTMLFormElement.prototype.submit = function () {
            const action = this && this.action ? this.action : "";
            if (dangerousAction.test(action)) {
              return block(`programmatic submit blocked: ${action}`);
            }
            return originalSubmit.call(this);
          };
        })("%s");
        """
        % dangerous_action
    )


def settle(page: Page, delay_ms: int = 1200) -> None:
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(delay_ms)


def login(page: Page, username: str, password: str) -> None:
    print("[step] open login page")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    login_form = page.locator('form[action*="login_check.php"]').first
    login_form.locator('input[name="mb_id"]').fill(username)
    login_form.locator('input[name="mb_password"]').fill(password)
    login_form.evaluate("(form) => form.submit()")
    settle(page)
    page.wait_for_function(
        "(user) => !!document.body && (document.body.innerText.includes(user) || document.body.innerText.includes('로그아웃'))",
        arg=username,
    )
    print("[step] login complete")


def find_my_posts_link(page: Page) -> str:
    print("[step] open recruit board")
    page.goto(RECRUIT_URL, wait_until="domcontentloaded")
    settle(page)
    link = page.locator('text="내가등록한글보기"').first
    href = link.get_attribute("onclick") or link.get_attribute("href") or ""
    if "document.location.href" in href:
        match = re.search(r"href='([^']+)'", href)
        if not match:
            match = re.search(r'href="([^"]+)"', href)
        if match:
            return urljoin(RECRUIT_URL, match.group(1))
    if href:
        return urljoin(RECRUIT_URL, href)
    raise RuntimeError("Could not locate the '내가등록한글보기' link")


def extract_top_post(page: Page, my_posts_url: str) -> Dict[str, str]:
    print("[step] open my posts")
    page.goto(my_posts_url, wait_until="domcontentloaded")
    settle(page)

    anchors = page.locator("a[href*='?id=']")
    count = anchors.count()
    for index in range(count):
        anchor = anchors.nth(index)
        href = anchor.get_attribute("href") or ""
        title = " ".join((anchor.inner_text() or "").split())
        if not href or not title:
            continue
        parsed_href = urljoin(RECRUIT_URL, href)
        if "un=" in parsed_href:
            match = re.search(r"[?&]id=(\d+)", parsed_href)
            return {
                "title": title,
                "view_url": parsed_href,
                "id": match.group(1) if match else "",
            }
    raise RuntimeError("Could not find the top post in the filtered my-posts list")


def find_edit_url(page: Page, view_url: str) -> str:
    print("[step] open top post detail")
    page.goto(view_url, wait_until="domcontentloaded")
    settle(page)

    button = page.locator('text="수정"').first
    onclick = button.get_attribute("onclick") or ""
    match = re.search(r"href='([^']+)'", onclick)
    if not match:
        match = re.search(r'href="([^"]+)"', onclick)
    if match:
        return urljoin(view_url, match.group(1))
    href = button.get_attribute("href")
    if href:
        return urljoin(view_url, href)
    raise RuntimeError("Could not locate edit URL from post view page")


def selected_value(page: Page, selector: str) -> str:
    value = page.locator(selector).input_value()
    return value.strip()


def checked_value(page: Page, name: str) -> str:
    locator = page.locator(f'input[name="{name}"]:checked').first
    if locator.count() == 0:
        return ""
    return locator.get_attribute("value", timeout=2000) or ""


def set_optional_field(page: Page, name: str, value: str) -> None:
    if not value:
        return
    locator = page.locator(f'[name="{name}"]')
    if locator.count() == 0:
        return
    locator.first.evaluate(
        """
        (el, value) => {
          el.value = value;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
        }
        """,
        value,
    )


def select_optional(page: Page, name: str, value: str, delay_ms: int = 800) -> None:
    if not value or value == "0":
        return
    locator = page.locator(f'select[name="{name}"]')
    if locator.count() == 0:
        set_optional_field(page, name, value)
        return
    values = locator.first.evaluate("(el) => Array.from(el.options || []).map(o => o.value)")
    if value not in values:
        return
    page.select_option(f'select[name="{name}"]', value)
    page.wait_for_timeout(delay_ms)


def summarize_content(html: str) -> Dict[str, Any]:
    normalized = re.sub(r"\s+", " ", html).strip()
    return {
        "content_length": len(html),
        "content_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "content_preview": normalized[:160],
    }


def extract_form_data(page: Page, edit_url: str) -> Dict[str, Any]:
    print("[step] open edit form")
    page.goto(edit_url, wait_until="domcontentloaded")
    settle(page)

    data = {
        "source_edit_url": edit_url,
        "id": page.locator('input[name="id"]').input_value().strip(),
        "list_url": page.locator('input[name="list_url"]').input_value().strip(),
        "title": page.locator('input[name="title"]').input_value().strip(),
        "company": page.locator('input[name="company"]').input_value().strip(),
        "tel": page.locator('input[name="tel"]').input_value().strip(),
        "job": page.locator('input[name="job"]').input_value().strip(),
        "person": page.locator('input[name="person"]').input_value().strip(),
        "carr": selected_value(page, 'select[name="carr"]'),
        "pay": page.locator('input[name="pay"]').input_value().strip(),
        "sex": checked_value(page, "sex"),
        "school": checked_value(page, "school"),
        "age1": page.locator('input[name="age1"]').input_value().strip(),
        "age2": page.locator('input[name="age2"]').input_value().strip(),
        "age3": checked_value(page, "age3"),
        "wr_link1_name": page.locator('input[name="wr_link1_name"]').input_value().strip(),
        "wr_link1": page.locator('input[name="wr_link1"]').input_value().strip(),
        "wr_link2_name": page.locator('input[name="wr_link2_name"]').input_value().strip(),
        "wr_link2": page.locator('input[name="wr_link2"]').input_value().strip(),
        "content_html": page.locator('textarea[name="content"]').input_value(),
    }

    for field in ("sido", "gugun", "dong", "ri", "bname"):
        locator = page.locator(f'[name="{field}"]')
        if locator.count():
            try:
                data[field] = locator.input_value().strip()
            except Exception:
                value = locator.evaluate(
                    "(el) => el.value || (el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex].value : '')"
                )
                data[field] = str(value).strip()
        else:
            data[field] = ""

    content_summary = summarize_content(data["content_html"])
    data.update(content_summary)
    print(
        "[check] fetched latest source content "
        f"(len={content_summary['content_length']}, sha256={content_summary['content_sha256'][:12]}...)"
    )

    return data


def fill_create_form(page: Page, data: Dict[str, Any]) -> None:
    print("[step] open create form")
    page.goto(f"{RECRUIT_URL}?mode=write", wait_until="domcontentloaded")
    settle(page)

    page.fill('input[name="title"]', data["title"])
    page.fill('input[name="company"]', data["company"])
    page.fill('input[name="tel"]', data["tel"])
    page.fill('input[name="job"]', data["job"])
    page.fill('input[name="person"]', data["person"])
    page.select_option('select[name="carr"]', data["carr"] or "")
    page.fill('input[name="pay"]', data["pay"])
    page.check(f'input[name="sex"][value="{data["sex"]}"]')
    if data["school"]:
        page.check(f'input[name="school"][value="{data["school"]}"]')
    page.fill('input[name="age1"]', data["age1"])
    page.fill('input[name="age2"]', data["age2"])
    if data["age3"]:
        page.check(f'input[name="age3"][value="{data["age3"]}"]')
    page.fill('input[name="wr_link1_name"]', data["wr_link1_name"])
    page.fill('input[name="wr_link1"]', data["wr_link1"])
    page.fill('input[name="wr_link2_name"]', data["wr_link2_name"])
    page.fill('input[name="wr_link2"]', data["wr_link2"])
    select_optional(page, "sido", data.get("sido", ""))
    select_optional(page, "gugun", data.get("gugun", ""))
    select_optional(page, "dong", data.get("dong", ""))
    select_optional(page, "ri", data.get("ri", ""))
    select_optional(page, "bname", data.get("bname", ""))

    page.locator('textarea[name="content"]').evaluate(
        "(el, value) => { el.value = value; }", data["content_html"]
    )
    page.evaluate(
        """
        (html) => {
          const frame = document.getElementById("gsEditor");
          if (frame && frame.contentWindow && frame.contentWindow.document) {
            frame.contentWindow.document.open();
            frame.contentWindow.document.write(html);
            frame.contentWindow.document.close();
          }
        }
        """,
        data["content_html"],
    )
    print("[step] create form populated")


def submit_create_form(page: Page, my_posts_url: str, source_post_id: str) -> Dict[str, Any]:
    print("[publish] submitting create form")
    page.on("dialog", lambda dialog: dialog.accept())
    with page.expect_response(
        lambda response: "insert.php" in response.url and response.request.method.upper() == "POST",
        timeout=30000,
    ) as response_info:
        page.click("#submit_btn")
    response = response_info.value
    settle(page, delay_ms=2000)

    latest_post = extract_top_post(page, my_posts_url)
    is_new_post = bool(latest_post.get("id")) and latest_post["id"] != source_post_id
    return {
        "submitted": True,
        "insert_status": response.status,
        "after_submit_url": page.url,
        "latest_post_after_submit": latest_post,
        "is_new_post_detected": is_new_post,
    }


def collect_create_form_snapshot(page: Page) -> Dict[str, Any]:
    return {
        "title": page.locator('input[name="title"]').input_value().strip(),
        "company": page.locator('input[name="company"]').input_value().strip(),
        "tel": page.locator('input[name="tel"]').input_value().strip(),
        "job": page.locator('input[name="job"]').input_value().strip(),
        "person": page.locator('input[name="person"]').input_value().strip(),
        "carr": selected_value(page, 'select[name="carr"]'),
        "pay": page.locator('input[name="pay"]').input_value().strip(),
        "sex": checked_value(page, "sex"),
        "school": checked_value(page, "school"),
        "age1": page.locator('input[name="age1"]').input_value().strip(),
        "age2": page.locator('input[name="age2"]').input_value().strip(),
        "age3": checked_value(page, "age3"),
        "wr_link1_name": page.locator('input[name="wr_link1_name"]').input_value().strip(),
        "wr_link1": page.locator('input[name="wr_link1"]').input_value().strip(),
        "wr_link2_name": page.locator('input[name="wr_link2_name"]').input_value().strip(),
        "wr_link2": page.locator('input[name="wr_link2"]').input_value().strip(),
        "content_length": len(page.locator('textarea[name="content"]').input_value()),
        "create_url": page.url,
        "sido": page.locator('[name="sido"]').evaluate("(el) => el.value").strip()
        if page.locator('[name="sido"]').count()
        else "",
        "gugun": page.locator('[name="gugun"]').evaluate("(el) => el.value").strip()
        if page.locator('[name="gugun"]').count()
        else "",
        "dong": page.locator('[name="dong"]').evaluate("(el) => el.value").strip()
        if page.locator('[name="dong"]').count()
        else "",
    }


def encode_multipart(fields: Dict[str, str], files: Dict[str, Path]) -> tuple[bytes, str]:
    boundary = f"codex-boundary-{hashlib.md5(os.urandom(16)).hexdigest()}"
    chunks = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    for name, path in files.items():
        filename = path.name
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode(),
                b"Content-Type: image/png\r\n\r\n",
                path.read_bytes(),
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def send_telegram_photo(result: Dict[str, Any], screenshot_path: Path) -> None:
    bot_token = getenv_optional("TELEGRAM_BOT_TOKEN")
    chat_id = getenv_optional("TELEGRAM_CHAT_ID")
    thread_id = getenv_optional("TELEGRAM_TOPIC_ID")
    if not bot_token or not chat_id:
        print("[step] telegram not configured, skipping send")
        return

    top_post = result["top_post"]
    source_data = result["source_data"]
    caption_lines = [
        f"[{result['mode']}] 공실닷컴 구인글 캡처",
        f"제목: {top_post['title']}",
        f"글 ID: {top_post['id']}",
        f"본문 길이: {source_data['content_length']}",
        f"본문 해시: {source_data['content_sha256'][:12]}...",
        f"확인 시각(UTC): {result['fetched_at_utc']}",
    ]
    fields = {
        "chat_id": chat_id,
        "caption": "\n".join(caption_lines),
    }
    if thread_id:
        fields["message_thread_id"] = thread_id

    body, boundary = encode_multipart(fields, {"photo": screenshot_path})
    api_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    req = request.Request(
        api_url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram send failed: {payload}")
    print("[done] telegram screenshot sent")


def save_outputs(result: Dict[str, Any], page: Page) -> None:
    output_dir = ensure_output_dir()
    (output_dir / "last_run.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    page.screenshot(path=str(output_dir / "create_form_dry_run.png"), full_page=True)


def main() -> int:
    username = getenv_required("GONGSIL_ID")
    password = getenv_required("GONGSIL_PASSWORD")
    headless = os.getenv("HEADLESS", "true").lower() not in {"0", "false", "no"}
    publish = os.getenv("PUBLISH", "false").lower() in {"1", "true", "yes"}
    publish_confirmed = os.getenv("PUBLISH_CONFIRM", "") == "REGISTER"

    if publish and not publish_confirmed:
        raise SystemExit("PUBLISH=true requires PUBLISH_CONFIRM=REGISTER")

    if publish:
        print("[start] publish mode. insert.php is allowed once; delete.php remains blocked.")
    else:
        print("[start] dry-run only. submit/delete requests are blocked.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(locale="ko-KR")
        install_submit_guard(context, allow_insert=publish)

        page = context.new_page()
        install_client_side_guard(page, allow_insert=publish)

        try:
            login(page, username, password)
            my_posts_url = find_my_posts_link(page)
            top_post = extract_top_post(page, my_posts_url)
            edit_url = find_edit_url(page, top_post["view_url"])
            source_data = extract_form_data(page, edit_url)
            fill_create_form(page, source_data)
            create_snapshot = collect_create_form_snapshot(page)

            result = {
                "mode": "publish" if publish else "dry-run",
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_content_checked_each_run": True,
                "my_posts_url": my_posts_url,
                "top_post": top_post,
                "source_data": source_data,
                "create_snapshot": create_snapshot,
                "guard_blocked": page.evaluate("window.__dry_run_blocked || null"),
            }
            save_outputs(result, page)
            send_telegram_photo(result, OUTPUT_DIR / "create_form_dry_run.png")

            if publish:
                publish_result = submit_create_form(page, my_posts_url, top_post["id"])
                result["publish_result"] = publish_result
                save_outputs(result, page)
                print(f"[done] published. insert status: {publish_result['insert_status']}")
                print(
                    "[done] latest post after submit: "
                    f"{publish_result['latest_post_after_submit']}"
                )
            else:
                print("[done] create form was populated without submitting.")
            print(f"[done] top post id: {top_post['id']}")
            print(f"[done] top post title: {top_post['title']}")
            print(f"[done] artifacts: {OUTPUT_DIR}")
            return 0
        except TimeoutError as exc:
            print(f"[error] timeout: {exc}", file=sys.stderr)
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
