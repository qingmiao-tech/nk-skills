#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from types import ModuleType
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


try:
    from playwright.sync_api import TimeoutError as PWTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PWTimeoutError = None
    sync_playwright = None


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from wechat_publish_config import load_config, resolve_config_path, resolve_optional_config_path, resolve_project_root


REPO_ROOT = resolve_project_root(__file__)
PUBLISH_CONFIG = load_config(REPO_ROOT)
WECHAT_MP_URL = "https://mp.weixin.qq.com"
OPENCLI_DAEMON_URL = str(PUBLISH_CONFIG.get("opencli_daemon_url") or "http://127.0.0.1:19825")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_SESSION_FILE = resolve_optional_config_path(REPO_ROOT, PUBLISH_CONFIG, "wechat_session_file") or (
    REPO_ROOT / "skills" / "wechat-draft-publisher" / "scripts" / "session.json"
)
DEFAULT_OUTPUT_JSON = resolve_config_path(REPO_ROOT, PUBLISH_CONFIG, "article_library_json")
DEFAULT_OUTPUT_MD = resolve_config_path(REPO_ROOT, PUBLISH_CONFIG, "article_library_md")
PUBLISH_DOC_ROOT = resolve_config_path(REPO_ROOT, PUBLISH_CONFIG, "publish_doc_root")
ARCHIVE_SCRIPT_PATH = (
    SCRIPT_DIR / "archive_wechat_article_to_publish.py"
    if (SCRIPT_DIR / "archive_wechat_article_to_publish.py").exists()
    else REPO_ROOT / "00.系统配置" / "wechat-cover-summary-tool" / "archive_wechat_article_to_publish.py"
)
INDEX_FILENAME = str(PUBLISH_CONFIG.get("publish_index_filename") or "发布索引.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从微信公众号后台同步已发表文章列表，并回写本地发布索引链接。")
    parser.add_argument(
        "--backend",
        choices=("opencli", "playwright"),
        default="opencli",
        help="同步后端：默认 opencli，直接读取主 Chrome 的 opencli 扩展登录态；playwright 会打开独立浏览器",
    )
    parser.add_argument("--session", type=Path, default=DEFAULT_SESSION_FILE, help="微信公众号后台登录态文件")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON, help="文章库 JSON 输出路径")
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD, help="文章库 Markdown 输出路径")
    parser.add_argument("--max-pages", type=int, default=5, help="最多拉取页数")
    parser.add_argument("--page-size", type=int, default=20, help="每页数量")
    parser.add_argument("--headless", action="store_true", help="无头模式运行浏览器")
    parser.add_argument("--relogin", action="store_true", help="强制重新扫码登录")
    parser.add_argument("--no-login", action="store_true", help="登录态失效时不弹出扫码登录，直接失败")
    parser.add_argument("--update-index", action="store_true", help="用同步到的文章链接回写本地发布记录和发布索引")
    parser.add_argument("--match-title", default="", help="只输出指定标题匹配到的文章链接")
    parser.add_argument("--json-output", action="store_true", help="用 JSON 打印匹配结果，方便其他脚本调用")
    parser.add_argument("--opencli-daemon-url", default=OPENCLI_DAEMON_URL, help="opencli daemon 地址")
    parser.add_argument("--token", default="", help="手动指定微信公众号后台 token，通常无需填写")
    return parser.parse_args()


def log(message: str) -> None:
    print(f"[wechat-sync] {message}", flush=True)


def load_module(module_name: str, module_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_session(context, session_file: Path) -> bool:
    if not session_file.exists():
        return False
    storage = json.loads(session_file.read_text(encoding="utf-8"))
    context.add_cookies(storage.get("cookies", []))
    return True


def save_session(context, session_file: Path) -> None:
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps({"cookies": context.cookies()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def token_from_url(url: str) -> str:
    return parse_qs(urlparse(url).query).get("token", [""])[0]


def token_from_page(page) -> str:
    token = token_from_url(page.url)
    if token:
        return token

    try:
        token = page.evaluate(
            """() => {
                const direct = window.cgiData?.token || window.wx?.cgiData?.token || "";
                if (direct) return String(direct);
                for (const item of Array.from(document.querySelectorAll("a[href*='token=']"))) {
                    const value = new URL(item.href, location.href).searchParams.get("token");
                    if (value) return value;
                }
                return "";
            }"""
        )
    except Exception:
        token = ""
    return token or ""


def check_login_valid(page) -> bool:
    page.goto(f"{WECHAT_MP_URL}/cgi-bin/home?t=home/index&lang=zh_CN", wait_until="domcontentloaded")
    time.sleep(2)
    return bool(token_from_page(page))


def wait_for_login(page, timeout_sec: int = 120) -> bool:
    log("请在打开的浏览器窗口中扫码登录微信公众号后台...")
    page.goto(WECHAT_MP_URL, wait_until="domcontentloaded")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if token_from_page(page):
            return True
        if "login" not in page.url and "passport" not in page.url:
            page.goto(f"{WECHAT_MP_URL}/cgi-bin/home?t=home/index&lang=zh_CN", wait_until="domcontentloaded")
        time.sleep(2)
    return False


def ensure_token(page) -> str:
    token = token_from_page(page)
    if token:
        return token

    page.goto(f"{WECHAT_MP_URL}/cgi-bin/home?t=home/index&lang=zh_CN", wait_until="domcontentloaded")
    time.sleep(2)
    token = token_from_page(page)
    if not token:
        raise RuntimeError("未能从公众号后台页面识别 token")
    return token


def request_publish_page(context, token: str, begin: int, count: int) -> dict:
    query = urlencode(
        {
            "sub": "list",
            "begin": str(begin),
            "count": str(count),
            "token": token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
        }
    )
    url = f"{WECHAT_MP_URL}/cgi-bin/appmsgpublish?{query}"
    response = context.request.get(
        url,
        headers={
            "Referer": f"{WECHAT_MP_URL}/cgi-bin/appmsgpublish?sub=list&token={token}&lang=zh_CN",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    if not response.ok:
        raise RuntimeError(f"获取已发表文章列表失败：HTTP {response.status}")
    payload = response.json()
    ensure_backend_payload_ok(payload)
    return payload


def ensure_backend_payload_ok(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    base_resp = payload.get("base_resp")
    if not isinstance(base_resp, dict):
        return
    ret = base_resp.get("ret")
    if ret in (None, 0, "0"):
        return
    message = str(base_resp.get("err_msg") or "unknown")
    raise RuntimeError(f"获取已发表文章列表失败：ret={ret}, err_msg={message}")


def opencli_request_json(
    daemon_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: int = 30,
) -> dict:
    data = None
    headers = {"X-OpenCLI": "1"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{daemon_url.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"opencli daemon 请求失败：HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError("无法连接 opencli daemon，请确认 opencli daemon 已启动且 Chrome 扩展已连接") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("opencli daemon 返回了无法解析的 JSON") from exc


def opencli_command(daemon_url: str, action: str, params: dict | None = None, timeout: int = 30):
    payload = {
        "id": f"wechat_sync_{int(time.time() * 1000)}",
        "action": action,
        **(params or {}),
    }
    result = opencli_request_json(daemon_url, "POST", "/command", payload, timeout=timeout + 5)
    if not result.get("ok"):
        raise RuntimeError(f"opencli 执行 {action} 失败：{result.get('error') or 'unknown'}")
    return result.get("data")


def get_opencli_cookies(daemon_url: str) -> list[dict]:
    status = opencli_request_json(daemon_url, "GET", "/status", timeout=5)
    if not status.get("extensionConnected"):
        raise RuntimeError("opencli daemon 已启动，但 Chrome 扩展未连接")

    cookies = opencli_command(daemon_url, "cookies", {"domain": "mp.weixin.qq.com"}, timeout=20)
    if not isinstance(cookies, list) or not cookies:
        raise RuntimeError("未从主 Chrome 读取到 mp.weixin.qq.com 的登录 Cookie")
    return [cookie for cookie in cookies if isinstance(cookie, dict)]


def cookie_header_from_opencli(cookies: list[dict]) -> str:
    pairs = []
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def token_from_opencli_logs(daemon_url: str) -> str:
    logs_payload = opencli_request_json(daemon_url, "GET", "/logs", timeout=5)
    logs = logs_payload.get("logs") if isinstance(logs_payload, dict) else []
    if not isinstance(logs, list):
        return ""

    for entry in reversed(logs):
        message = str(entry.get("msg") or "") if isinstance(entry, dict) else ""
        for match in re.finditer(r"https://mp\.weixin\.qq\.com/[^\s,]+", html.unescape(message)):
            token = token_from_url(match.group(0))
            if token:
                return token
        match = re.search(r"token=(\d+)", message)
        if match:
            return match.group(1)
    return ""


def request_publish_page_with_cookie(cookie_header: str, token: str, begin: int, count: int) -> dict:
    query = urlencode(
        {
            "sub": "list",
            "begin": str(begin),
            "count": str(count),
            "token": token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
        }
    )
    url = f"{WECHAT_MP_URL}/cgi-bin/appmsgpublish?{query}"
    request = Request(
        url,
        headers={
            "Cookie": cookie_header,
            "Referer": f"{WECHAT_MP_URL}/cgi-bin/appmsgpublish?sub=list&token={token}&lang=zh_CN",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8-sig")
    except HTTPError as exc:
        raise RuntimeError(f"获取已发表文章列表失败：HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("请求微信公众号后台失败，请确认主 Chrome 登录态仍有效") from exc

    payload = json.loads(raw)
    ensure_backend_payload_ok(payload)
    return payload


def parse_json_string(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def timestamp_to_text(value) -> str:
    if value in (None, ""):
        return ""
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return str(value)
    if timestamp <= 0:
        return ""
    return dt.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def normalize_article(raw: dict) -> dict | None:
    title = str(raw.get("title") or raw.get("title_short") or "").strip()
    url = str(raw.get("link") or raw.get("content_url") or raw.get("url") or "").strip()
    if not title or not url:
        return None

    url = html.unescape(url)
    digest = str(raw.get("digest") or raw.get("summary") or "").strip()
    cover = str(raw.get("cover") or raw.get("thumb_url") or raw.get("pic_cdn_url") or "").strip()
    article_id = str(raw.get("appmsgid") or raw.get("msgid") or raw.get("id") or "").strip()
    published_at = timestamp_to_text(
        raw.get("publish_time")
        or raw.get("sent_time")
        or raw.get("time")
        or raw.get("update_time")
        or raw.get("create_time")
    )
    return {
        "title": html.unescape(title),
        "url": url,
        "digest": html.unescape(digest),
        "cover": html.unescape(cover),
        "published_at": published_at,
        "article_id": article_id,
        "source": "wechat_mp_backend",
    }


def extract_articles(payload) -> list[dict]:
    payload = parse_json_string(payload)
    articles: list[dict] = []

    if isinstance(payload, list):
        for item in payload:
            articles.extend(extract_articles(item))
        return articles

    if not isinstance(payload, dict):
        return articles

    normalized = normalize_article(payload)
    if normalized:
        articles.append(normalized)

    sent_info = payload.get("sent_info")
    sent_time = sent_info.get("time") if isinstance(sent_info, dict) else None
    for key in ("publish_page", "publish_list", "publish_info", "appmsg_info", "appmsgex", "item", "list"):
        if key in payload:
            nested = parse_json_string(payload[key])
            if key == "appmsg_info" and sent_time and isinstance(nested, list):
                nested = [
                    {**item, "publish_time": item.get("publish_time") or sent_time}
                    if isinstance(item, dict)
                    else item
                    for item in nested
                ]
            articles.extend(extract_articles(nested))

    return articles


def extract_total_count(payload) -> int | None:
    payload = parse_json_string(payload)
    if isinstance(payload, dict):
        for key in ("total_count", "total", "count"):
            value = payload.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        for key in ("publish_page", "data"):
            nested = extract_total_count(payload.get(key))
            if nested is not None:
                return nested
    return None


def normalize_title(title: str) -> str:
    title = re.sub(r"^\d{4}年\d{1,2}月\d{1,2}日[-—]?", "", title.strip())
    title = re.sub(r"[（(](改写版|修改版|修订版|优化版|排版版)[)）]", "", title)
    return re.sub(r"\s+", "", title).lower()


def merge_articles(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for article in existing + incoming:
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        if not title or not url:
            continue
        key = normalize_title(title) or str(article.get("article_id") or "").strip() or url
        current = merged.get(key, {})
        incoming_values = {k: v for k, v in article.items() if v}
        chosen = {**current, **incoming_values}
        if current.get("url") and incoming_values.get("url"):
            chosen["url"] = choose_preferred_url(str(current["url"]), str(incoming_values["url"]))
        merged[key] = chosen

    return sorted(
        merged.values(),
        key=lambda item: item.get("published_at") or "",
        reverse=True,
    )


def choose_preferred_url(current_url: str, incoming_url: str) -> str:
    def score(url: str) -> int:
        if re.match(r"^https://mp\.weixin\.qq\.com/s/[^?]+$", url):
            return 3
        if "mp.weixin.qq.com/s/" in url:
            return 2
        if "tempkey=" in url:
            return 0
        return 1

    return incoming_url if score(incoming_url) > score(current_url) else current_url


def load_article_library(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("articles", [])
    if isinstance(data, list):
        return data
    return []


def save_article_library(json_path: Path, md_path: Path, articles: list[dict]) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "wechat_mp_backend",
        "articles": articles,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 公众号文章库", "", f"- 更新时间：{payload['updated_at']}", f"- 文章数：{len(articles)}", ""]
    for article in articles:
        lines.append(f"## {article['title']}")
        if article.get("published_at"):
            lines.append(f"- 发布时间：{article['published_at']}")
        lines.append(f"- 链接：{article['url']}")
        if article.get("digest"):
            lines.append(f"- 摘要：{article['digest']}")
        lines.append("")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def collect_backend_articles_with_opencli(args: argparse.Namespace) -> list[dict]:
    cookies = get_opencli_cookies(args.opencli_daemon_url)
    cookie_header = cookie_header_from_opencli(cookies)
    token = args.token.strip() or token_from_opencli_logs(args.opencli_daemon_url)
    if not token:
        raise RuntimeError(
            "未能从 opencli 日志识别微信公众号后台 token。请先在主 Chrome 打开公众号后台“内容与互动/发表记录”列表页，或用 --token 手动指定。"
        )

    articles: list[dict] = []
    total_count: int | None = None
    for page_index in range(max(args.max_pages, 1)):
        begin = page_index * args.page_size
        payload = request_publish_page_with_cookie(cookie_header, token, begin, args.page_size)
        if total_count is None:
            total_count = extract_total_count(payload)
        batch = extract_articles(payload)
        articles.extend(batch)
        if not batch:
            break
        if total_count is not None and begin + args.page_size >= total_count:
            break

    return articles


def collect_backend_articles_with_playwright(args: argparse.Namespace) -> list[dict]:
    if sync_playwright is None:
        raise RuntimeError("playwright 未安装，请运行：pip install playwright && playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        if args.relogin and args.session.exists():
            args.session.unlink()

        session_loaded = load_session(context, args.session)
        session_valid = session_loaded and check_login_valid(page)
        if not session_valid:
            if args.no_login:
                browser.close()
                raise RuntimeError("公众号后台登录态无效，请先用非 --no-login 模式扫码登录")
            if not wait_for_login(page):
                browser.close()
                raise RuntimeError("公众号后台登录失败")
            save_session(context, args.session)

        token = ensure_token(page)
        page.goto(
            f"{WECHAT_MP_URL}/cgi-bin/appmsgpublish?action=list&token={token}&lang=zh_CN",
            wait_until="domcontentloaded",
        )
        time.sleep(1)
        articles: list[dict] = []
        total_count: int | None = None

        for page_index in range(max(args.max_pages, 1)):
            begin = page_index * args.page_size
            payload = request_publish_page(context, token, begin, args.page_size)
            if total_count is None:
                total_count = extract_total_count(payload)
            batch = extract_articles(payload)
            articles.extend(batch)
            if not batch:
                break
            if total_count is not None and begin + args.page_size >= total_count:
                break

        save_session(context, args.session)
        browser.close()
        return articles


def collect_backend_articles(args: argparse.Namespace) -> list[dict]:
    if args.backend == "opencli":
        return collect_backend_articles_with_opencli(args)
    return collect_backend_articles_with_playwright(args)


def find_article_by_title(articles: list[dict], title: str) -> dict | None:
    target = normalize_title(title)
    if not target:
        return None
    exact = [item for item in articles if normalize_title(str(item.get("title") or "")) == target]
    if exact:
        return exact[0]

    for item in articles:
        item_key = normalize_title(str(item.get("title") or ""))
        if item_key and (item_key in target or target in item_key):
            return item
    return None


def parse_publish_index(index_path: Path) -> list[dict]:
    if not index_path.exists():
        return []
    text = index_path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^##\s+(.+)$", text, re.MULTILINE))
    entries: list[dict] = []
    for idx, match in enumerate(matches):
        block = text[match.end() : matches[idx + 1].start() if idx + 1 < len(matches) else len(text)]
        entry = {"title": match.group(1).strip(), "index_path": index_path}
        for line in block.splitlines():
            field_match = re.match(r"^-\s*([^：]+)：(.+)$", line.strip())
            if not field_match:
                continue
            key = field_match.group(1).strip()
            value = field_match.group(2).strip().strip("`")
            entry[key] = value
        entries.append(entry)
    return entries


def update_local_publish_links(articles: list[dict]) -> int:
    archive_module = load_module("archive_wechat_article_to_publish", ARCHIVE_SCRIPT_PATH)
    updated_count = 0
    for index_path in PUBLISH_DOC_ROOT.glob(f"*/发布/{INDEX_FILENAME}"):
        for entry in parse_publish_index(index_path):
            current_url = str(entry.get("发布链接") or "").strip()
            if current_url and current_url != "待补充":
                continue

            matched = find_article_by_title(articles, str(entry.get("title") or ""))
            if not matched:
                continue
            published_url = str(matched.get("url") or "").strip()
            if not published_url:
                continue

            published_path_text = str(entry.get("发布路径") or "").strip()
            if not published_path_text:
                continue
            published_path = REPO_ROOT / published_path_text
            if not published_path.exists():
                continue

            draft_path, target_path, publish_root = archive_module.resolve_article_pair(published_path)
            summary = str(entry.get("列表摘要") or "")
            cover_path, _, preview_path = archive_module.derive_publish_artifact_paths(target_path, "blue")
            archive_module.write_back_publish_record(draft_path, target_path, published_url)
            archive_module.update_published_article_record(
                target_path,
                source_article_path=draft_path,
                summary=summary,
                cover_path=cover_path,
                preview_path=preview_path,
                published_url=published_url,
            )
            archive_module.update_publish_index(
                publish_root,
                source_article_path=draft_path,
                target_article_path=target_path,
                title=str(entry.get("title") or ""),
                summary=summary,
                published_url=published_url,
            )
            updated_count += 1
    return updated_count


def main() -> int:
    args = parse_args()
    fetched = collect_backend_articles(args)
    existing = load_article_library(args.output_json)
    articles = merge_articles(existing, fetched)
    save_article_library(args.output_json, args.output_md, articles)

    matched = find_article_by_title(articles, args.match_title) if args.match_title else None
    if args.update_index:
        updated_count = update_local_publish_links(articles)
        log(f"已回写本地发布链接：{updated_count} 条")

    if args.match_title:
        payload = {"title": args.match_title, "matched": matched or {}}
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False))
        elif matched:
            print(matched.get("url", ""))
        return 0 if matched else 2

    log(f"已同步文章：{len(fetched)} 条，本地文章库：{args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
