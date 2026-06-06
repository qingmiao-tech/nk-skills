#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from wechat_publish_config import load_config, resolve_project_root


REPO_ROOT = resolve_project_root(__file__)
PUBLISH_CONFIG = load_config(REPO_ROOT)
PUBLISH_SCRIPT_PATH = (
    SCRIPT_DIR / "build_wechat_publish_package.py"
    if (SCRIPT_DIR / "build_wechat_publish_package.py").exists()
    else REPO_ROOT / "00.系统配置" / "wechat-cover-summary-tool" / "build_wechat_publish_package.py"
)
SYNC_SCRIPT_PATH = (
    SCRIPT_DIR / "sync_wechat_published_articles.py"
    if (SCRIPT_DIR / "sync_wechat_published_articles.py").exists()
    else REPO_ROOT / "00.系统配置" / "wechat-cover-summary-tool" / "sync_wechat_published_articles.py"
)
IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
PUBLISH_RECORD_HEADING = "## 发布记录"
PUBLISH_INDEX_FILENAME = str(PUBLISH_CONFIG.get("publish_index_filename") or "发布索引.md")
DATE_PREFIX_RE = re.compile(r"^(\d{4}年\d{1,2}月\d{1,2}日)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy a draft WeChat article into the 发布 directory and generate publish assets there."
    )
    parser.add_argument("--article", required=True, help="草稿 Markdown 文章路径")
    parser.add_argument("--summary", default="", help="公众号列表摘要")
    parser.add_argument("--cover-title", default="", help="封面主标题")
    parser.add_argument("--cover-subtitle", default="", help="封面副标题")
    parser.add_argument("--brand", default="", help="品牌角标")
    parser.add_argument("--accent", default="", help="强调词")
    parser.add_argument("--theme", default="blue", help="HTML 主题，默认 blue")
    parser.add_argument("--published-url", default="", help="已发布文章链接，可选")
    parser.add_argument(
        "--auto-fetch-published-url",
        action="store_true",
        help="从公众号后台文章列表自动匹配当前文章正式链接，并回写发布记录",
    )
    parser.add_argument("--wechat-session", type=Path, default=None, help="微信公众号后台 session.json 路径")
    parser.add_argument("--wechat-sync-pages", type=int, default=5, help="自动同步公众号后台文章列表的页数")
    parser.add_argument("--wechat-sync-headless", action="store_true", help="同步公众号后台时使用无头浏览器")
    parser.add_argument(
        "--wechat-sync-backend",
        choices=("opencli", "playwright"),
        default="opencli",
        help="自动同步公众号后台的后端，默认 opencli，复用主 Chrome 登录态",
    )
    parser.add_argument(
        "--update-link-only",
        action="store_true",
        help="只补写公众号链接和归档信息，不重新复制文章或生成发布素材",
    )
    parser.add_argument(
        "--copy-html",
        action="store_true",
        help="生成后复制 HTML 片段到剪贴板",
    )
    return parser.parse_args()


def load_module(module_name: str, module_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def split_before_draft(article_path: Path) -> tuple[Path, Path]:
    parts = article_path.parts
    if "草稿" not in parts:
        raise ValueError(f"文章路径中缺少“草稿”目录：{article_path}")
    draft_index = parts.index("草稿")
    base_path = Path(*parts[:draft_index])
    relative_path = Path(*parts[draft_index + 1 :])
    return base_path, relative_path


def derive_publish_root(article_path: Path) -> Path:
    parts = article_path.parts
    if "草稿" not in parts:
        raise ValueError(f"文章路径中缺少“草稿”目录：{article_path}")

    draft_index = parts.index("草稿")
    if draft_index == 0:
        raise ValueError(f"无法从路径识别年份目录：{article_path}")

    year_dir = parts[draft_index - 1]
    if not re.match(r"^\d{4}年$", year_dir):
        raise ValueError(f"草稿目录前一级不是年份目录：{article_path}")

    return Path(*parts[:draft_index - 1]) / year_dir / "发布"


def derive_draft_root(published_article_path: Path) -> Path:
    parts = published_article_path.parts
    if "发布" not in parts:
        raise ValueError(f"发布文章路径中缺少“发布”目录：{published_article_path}")

    publish_index = parts.index("发布")
    if publish_index == 0:
        raise ValueError(f"无法从路径识别年份目录：{published_article_path}")

    year_dir = parts[publish_index - 1]
    if not re.match(r"^\d{4}年$", year_dir):
        raise ValueError(f"发布目录前一级不是年份目录：{published_article_path}")

    return Path(*parts[:publish_index - 1]) / year_dir / "草稿"


def split_after_publish(published_article_path: Path) -> Path:
    parts = published_article_path.parts
    if "发布" not in parts:
        raise ValueError(f"发布文章路径中缺少“发布”目录：{published_article_path}")
    publish_index = parts.index("发布")
    return Path(*parts[publish_index + 1 :])


def derive_published_article_path_from_draft(article_path: Path) -> Path:
    publish_root = derive_publish_root(article_path.resolve())
    _, relative_path = split_before_draft(article_path.resolve())
    return (publish_root.resolve() / relative_path).resolve()


def derive_draft_article_path_from_published(published_article_path: Path) -> Path:
    draft_root = derive_draft_root(published_article_path.resolve())
    relative_path = split_after_publish(published_article_path.resolve())
    return (draft_root.resolve() / relative_path).resolve()


def normalize_relative_asset_path(raw_path: str) -> str:
    return raw_path.split('"')[0].strip()


def collect_local_image_references(markdown: str) -> list[str]:
    refs: list[str] = []
    for raw_path in IMAGE_REF_RE.findall(markdown):
        normalized = normalize_relative_asset_path(raw_path)
        if normalized.startswith(("http://", "https://", "data:")):
            continue
        refs.append(normalized)
    return refs


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def date_prefix_from_stem(stem: str) -> str:
    match = DATE_PREFIX_RE.match(stem)
    if not match:
        raise ValueError(f"文章文件名缺少日期前缀：{stem}")
    return match.group(1)


def title_from_markdown(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def fetch_published_url_from_backend(title: str, args: argparse.Namespace) -> str:
    command = [
        sys.executable,
        str(SYNC_SCRIPT_PATH),
        "--match-title",
        title,
        "--json-output",
        "--update-index",
        "--max-pages",
        str(args.wechat_sync_pages),
        "--backend",
        args.wechat_sync_backend,
    ]
    if args.wechat_session:
        command.extend(["--session", str(args.wechat_session)])
    if args.wechat_sync_headless:
        command.append("--headless")

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode not in (0, 2):
        sys.stderr.write(result.stderr)
        raise RuntimeError("自动获取公众号正式链接失败")
    if result.returncode == 2:
        return ""

    payload_line = ""
    for line in reversed(result.stdout.splitlines()):
        if line.strip().startswith("{"):
            payload_line = line.strip()
            break
    if not payload_line:
        return ""
    payload = json.loads(payload_line)
    matched = payload.get("matched") or {}
    return str(matched.get("url") or "").strip()


def to_vault_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def derive_publish_artifact_paths(published_article_path: Path, theme: str) -> tuple[Path, Path, Path]:
    date_prefix = date_prefix_from_stem(published_article_path.stem)
    cover_path = published_article_path.parent / date_prefix / f"{published_article_path.stem}-公众号封面.png"
    summary_path = published_article_path.parent / date_prefix / f"{published_article_path.stem}-公众号列表摘要.txt"
    preview_path = published_article_path.with_name(f"{published_article_path.stem}.{theme}.preview.html")
    return cover_path, summary_path, preview_path


def load_summary_text(published_article_path: Path, theme: str) -> str:
    _, summary_path, _ = derive_publish_artifact_paths(published_article_path, theme)
    if summary_path.exists():
        return summary_path.read_text(encoding="utf-8").strip()
    return ""


def has_yaml_frontmatter(markdown: str) -> bool:
    lines = markdown.splitlines()
    return len(lines) >= 2 and lines[0].strip() == "---" and "---" in {line.strip() for line in lines[1:]}


def update_yaml_publish_metadata(markdown: str, target_article_path: Path, published_url: str = "") -> str:
    lines = markdown.splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return markdown

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        return markdown

    frontmatter = lines[1:closing_index]
    body = lines[closing_index + 1 :]
    target_path_value = to_vault_relative(target_article_path)
    published_at_value = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def upsert_field(items: list[str], key: str, value: str) -> list[str]:
        prefix = f"{key}:"
        for idx, line in enumerate(items):
            if line.startswith(prefix):
                items[idx] = f'{key}: "{value}"'
                return items
        items.append(f'{key}: "{value}"')
        return items

    frontmatter = upsert_field(frontmatter, "published_path", target_path_value)
    frontmatter = upsert_field(frontmatter, "published_at", published_at_value)
    frontmatter = upsert_field(frontmatter, "status", "已发布")
    if published_url.strip():
        frontmatter = upsert_field(frontmatter, "published_url", published_url.strip())

    rebuilt = ["---", *frontmatter, "---", *body]
    return "\n".join(rebuilt).rstrip() + "\n"


def update_body_publish_record(markdown: str, target_article_path: Path, published_url: str = "") -> str:
    target_path_value = to_vault_relative(target_article_path)
    published_at_value = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    published_url_line = f"- 发布链接：{published_url.strip()}\n" if published_url.strip() else ""
    record_block = (
        f"{PUBLISH_RECORD_HEADING}\n\n"
        f"- 发布时间：{published_at_value}\n"
        f"- 发布路径：`{target_path_value}`\n"
        f"{published_url_line}"
        f"- 发布状态：已发布\n"
    )

    pattern = re.compile(
        rf"(?:\n|^){re.escape(PUBLISH_RECORD_HEADING)}\n(?:.*\n?)*\Z",
        re.MULTILINE,
    )
    if pattern.search(markdown):
        updated = pattern.sub(f"\n\n{record_block}", markdown.rstrip())
        return updated.rstrip() + "\n"
    return markdown.rstrip() + "\n\n" + record_block


def write_back_publish_record(article_path: Path, target_article_path: Path, published_url: str = "") -> None:
    markdown = article_path.read_text(encoding="utf-8")
    if has_yaml_frontmatter(markdown):
        updated = update_yaml_publish_metadata(markdown, target_article_path, published_url)
    else:
        updated = update_body_publish_record(markdown, target_article_path, published_url)
    article_path.write_text(updated, encoding="utf-8")


def update_published_article_record(
    target_article_path: Path,
    *,
    source_article_path: Path,
    summary: str,
    cover_path: Path,
    preview_path: Path,
    published_url: str = "",
) -> None:
    markdown = target_article_path.read_text(encoding="utf-8")
    source_path_value = to_vault_relative(source_article_path.resolve())
    cover_path_value = to_vault_relative(cover_path.resolve())
    preview_path_value = to_vault_relative(preview_path.resolve())
    published_url_line = f"- 公众号链接：{published_url.strip()}\n" if published_url.strip() else ""
    record_block = (
        f"{PUBLISH_RECORD_HEADING}\n\n"
        f"- 发布状态：已发布\n"
        f"- 草稿来源：`{source_path_value}`\n"
        f"- 发布时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- 封面文件：`{cover_path_value}`\n"
        f"- 预览文件：`{preview_path_value}`\n"
        f"{published_url_line}"
        f"- 列表摘要：{summary.strip()}\n"
    )

    pattern = re.compile(
        rf"(?:\n|^){re.escape(PUBLISH_RECORD_HEADING)}\n(?:.*\n?)*\Z",
        re.MULTILINE,
    )
    if pattern.search(markdown):
        updated = pattern.sub(f"\n\n{record_block}", markdown.rstrip())
    else:
        updated = markdown.rstrip() + "\n\n" + record_block
    target_article_path.write_text(updated.rstrip() + "\n", encoding="utf-8")


def update_publish_index(
    publish_root: Path,
    *,
    source_article_path: Path,
    target_article_path: Path,
    title: str,
    summary: str,
    published_url: str = "",
) -> Path:
    index_path = publish_root / PUBLISH_INDEX_FILENAME
    published_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_path_value = to_vault_relative(source_article_path.resolve())
    target_path_value = to_vault_relative(target_article_path.resolve())
    published_url_text = published_url.strip() or "待补充"
    entry = (
        f"## {title}\n\n"
        f"- 发布时间：{published_at}\n"
        f"- 草稿路径：`{source_path_value}`\n"
        f"- 发布路径：`{target_path_value}`\n"
        f"- 发布链接：{published_url_text}\n"
        f"- 列表摘要：{summary.strip()}\n"
    )

    if index_path.exists():
        current = index_path.read_text(encoding="utf-8")
    else:
        current = "# 发布索引\n\n"

    matches = list(re.finditer(r"^##\s+(.+)$", current, re.MULTILINE))
    replacement_done = False

    if matches:
        segments: list[str] = []
        last_end = 0
        for idx, match in enumerate(matches):
            block_start = match.start()
            block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(current)
            block = current[block_start:block_end]
            block_title = match.group(1).strip()
            should_replace = (
                block_title == title
                or f"- 草稿路径：`{source_path_value}`" in block
                or f"- 发布路径：`{target_path_value}`" in block
            )

            if should_replace and not replacement_done:
                segments.append(current[last_end:block_start])
                segments.append(f"\n\n{entry}\n")
                replacement_done = True
            else:
                segments.append(current[last_end:block_end])
            last_end = block_end

        updated = "".join(segments).rstrip() + "\n"
    else:
        updated = current.rstrip() + "\n"

    if not replacement_done:
        updated = updated.rstrip() + "\n\n" + entry + "\n"

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(updated.rstrip() + "\n", encoding="utf-8")
    return index_path


def archive_article(
    *,
    article_path: Path,
    publish_root: Path,
) -> tuple[Path, list[Path]]:
    article_path = article_path.resolve()
    if not article_path.exists():
        raise FileNotFoundError(f"文章不存在：{article_path}")

    _, relative_path = split_before_draft(article_path)
    target_article_path = (publish_root.resolve() / relative_path).resolve()
    copy_file(article_path, target_article_path)

    markdown = article_path.read_text(encoding="utf-8")
    copied_assets: list[Path] = []
    for ref in collect_local_image_references(markdown):
        source_asset = (article_path.parent / ref).resolve()
        if not source_asset.exists() or not source_asset.is_file():
            continue
        target_asset = (target_article_path.parent / ref).resolve()
        copy_file(source_asset, target_asset)
        copied_assets.append(target_asset)

    return target_article_path, copied_assets


def resolve_article_pair(article_path: Path) -> tuple[Path, Path, Path]:
    resolved = article_path.resolve()
    parts = resolved.parts
    if "草稿" in parts:
        draft_article_path = resolved
        publish_root = derive_publish_root(resolved)
        published_article_path = derive_published_article_path_from_draft(resolved)
        return draft_article_path, published_article_path, publish_root
    if "发布" in parts:
        published_article_path = resolved
        publish_root = derive_publish_root(derive_draft_article_path_from_published(resolved))
        draft_article_path = derive_draft_article_path_from_published(resolved)
        return draft_article_path, published_article_path, publish_root
    raise ValueError(f"文章路径既不在草稿目录也不在发布目录：{article_path}")


def main() -> int:
    args = parse_args()
    article_path = Path(args.article)
    draft_article_path, published_article_path, publish_root = resolve_article_pair(article_path)

    if args.update_link_only:
        if not published_article_path.exists():
            raise FileNotFoundError(f"发布文章不存在：{published_article_path}")

        published_markdown = published_article_path.read_text(encoding="utf-8")
        published_title = title_from_markdown(published_markdown, published_article_path.stem)
        published_url = args.published_url
        if args.auto_fetch_published_url and not published_url.strip():
            fetched_url = fetch_published_url_from_backend(published_title, args)
            if fetched_url:
                published_url = fetched_url
        if not published_url.strip():
            raise ValueError("补链模式必须提供 --published-url，或使用 --auto-fetch-published-url 自动获取")

        summary_text = load_summary_text(published_article_path, args.theme)
        cover_path, _, preview_path = derive_publish_artifact_paths(published_article_path, args.theme)
        write_back_publish_record(draft_article_path, published_article_path, published_url)
        write_back_publish_record(published_article_path, published_article_path, published_url)
        update_published_article_record(
            published_article_path,
            source_article_path=draft_article_path,
            summary=summary_text,
            cover_path=cover_path,
            preview_path=preview_path,
            published_url=published_url,
        )
        index_path = update_publish_index(
            publish_root,
            source_article_path=draft_article_path,
            target_article_path=published_article_path,
            title=published_title,
            summary=summary_text,
            published_url=published_url,
        )
        print(draft_article_path)
        print(published_article_path)
        print(index_path)
        return 0

    if not args.summary.strip():
        raise ValueError("发布模式必须提供 --summary")

    publish_module = load_module("build_wechat_publish_package", PUBLISH_SCRIPT_PATH)
    target_article_path, copied_assets = archive_article(
        article_path=draft_article_path,
        publish_root=publish_root,
    )

    published_markdown = target_article_path.read_text(encoding="utf-8")
    published_title = title_from_markdown(published_markdown, target_article_path.stem)
    published_url = args.published_url
    if args.auto_fetch_published_url and not published_url.strip():
        fetched_url = fetch_published_url_from_backend(published_title, args)
        if fetched_url:
            published_url = fetched_url

    cover_path, summary_path, fragment_path, preview_path = publish_module.build_publish_package(
        article_path=target_article_path,
        summary=args.summary,
        cover_title=args.cover_title,
        cover_subtitle=args.cover_subtitle,
        brand=args.brand,
        accent=args.accent,
        theme=args.theme,
        published_url=published_url,
        promote_h2_to_h1=args.theme == "blue",
        copy_html=args.copy_html,
    )

    write_back_publish_record(draft_article_path, target_article_path, published_url)
    write_back_publish_record(target_article_path, target_article_path, published_url)
    update_published_article_record(
        target_article_path,
        source_article_path=draft_article_path,
        summary=args.summary,
        cover_path=cover_path,
        preview_path=preview_path,
        published_url=published_url,
    )
    index_path = update_publish_index(
        publish_root,
        source_article_path=draft_article_path,
        target_article_path=target_article_path,
        title=published_title,
        summary=args.summary,
        published_url=published_url,
    )

    print(target_article_path)
    for asset_path in copied_assets:
        print(asset_path)
    print(cover_path)
    print(summary_path)
    print(fragment_path)
    print(preview_path)
    print(index_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
