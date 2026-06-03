#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]
COVER_SCRIPT_PATH = REPO_ROOT / "00.系统配置" / "wechat-cover-summary-tool" / "build_wechat_cover_package.py"
HTML_SCRIPT_CANDIDATES = [
    REPO_ROOT / ".claude" / "skills" / "nk-wechat-mdnice-blue-html" / "scripts" / "convert_markdown.py",
    REPO_ROOT / ".agents" / "skills" / "nk-wechat-mdnice-blue-html" / "scripts" / "convert_markdown.py",
    REPO_ROOT / "skills" / "nk-wechat-mdnice-blue-html" / "scripts" / "convert_markdown.py",
    REPO_ROOT / ".claude" / "skills" / "wechat-mdnice-blue-html" / "scripts" / "convert_markdown.py",
]
HTML_SCRIPT_PATH = next((path for path in HTML_SCRIPT_CANDIDATES if path.exists()), HTML_SCRIPT_CANDIDATES[0])
PUBLISH_RECORD_HEADING = "## 发布记录"
WECHAT_TEMPLATE_DIR = REPO_ROOT / "07.发布文案" / "模板" / "公众号"
WECHAT_HEADER_TEMPLATE_PATH = WECHAT_TEMPLATE_DIR / "AI南柯-header-card.md"
WECHAT_FOOTER_TEMPLATE_PATH = WECHAT_TEMPLATE_DIR / "AI南柯-footer.md"
WECHAT_ARTICLE_LIBRARY_PATH = REPO_ROOT / "08.数据反馈" / "公众号文章库" / "AI南柯-文章列表.json"
PUBLISH_INDEX_FILENAME = "发布索引.md"
MAX_RELATED_ARTICLES = 5
RELATED_KEYWORD_WEIGHTS = {
    "obsidian": 18,
    "知识库": 18,
    "长期记忆": 16,
    "记忆系统": 16,
    "本地": 10,
    "归档": 14,
    "复盘": 10,
    "工作流": 14,
    "skill": 14,
    "脚本": 12,
    "agent": 10,
    "智能体": 10,
    "hermes": 12,
    "飞书": 8,
    "公众号": 8,
    "发布": 8,
}
PUBLISH_ENV_CANDIDATES = [
    REPO_ROOT / "skills" / "nk-wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.ps1",
    REPO_ROOT / ".claude" / "skills" / "nk-wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.ps1",
    REPO_ROOT / ".agents" / "skills" / "nk-wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.ps1",
    REPO_ROOT / "skills" / "wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.ps1",
    REPO_ROOT / ".claude" / "skills" / "wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.ps1",
    REPO_ROOT / ".agents" / "skills" / "wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.ps1",
]
PUBLISH_ENV_FALLBACK_CANDIDATES = [
    REPO_ROOT / "skills" / "nk-wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.ps1.example",
    REPO_ROOT / "skills" / "nk-wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.template.ps1",
    REPO_ROOT / "skills" / "wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.ps1.example",
    REPO_ROOT / "skills" / "wechat-mdnice-blue-html" / "scripts" / "publish_wechat.env.template.ps1",
]
PLACEHOLDER_ENV_VALUES = {
    "REPLACE_WITH_GITHUB_TOKEN",
    "REPLACE_WITH_YOUR_NEW_TOKEN",
    "YOUR_TOKEN",
    "owner/repo",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a WeChat publish package with cover, summary, and HTML.")
    parser.add_argument("--article", required=True, help="Absolute or relative path to the markdown article.")
    parser.add_argument("--summary", required=True, help="WeChat list summary text.")
    parser.add_argument("--cover-title", default="", help="Short cover headline.")
    parser.add_argument("--cover-subtitle", default="", help="Cover subtitle.")
    parser.add_argument("--brand", default="", help="Brand badge text.")
    parser.add_argument("--accent", default="", help="Optional accent badge text.")
    parser.add_argument("--theme", default="blue", help="WeChat HTML theme name, default blue.")
    parser.add_argument("--published-url", default="", help="Current article published URL, used to exclude itself from related articles.")
    parser.add_argument(
        "--promote-h2-to-h1",
        action="store_true",
        help="Force render Markdown ## headings with h1 styling.",
    )
    parser.add_argument("--copy-html", action="store_true", help="Copy generated HTML fragment to clipboard.")
    return parser.parse_args()


def load_module(module_name: str, module_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def strip_yaml_frontmatter(markdown: str) -> str:
    lines = markdown.splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return markdown

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            remaining = "\n".join(lines[index + 1 :]).lstrip("\n")
            return remaining
    return markdown


def strip_publish_record_block(markdown: str) -> str:
    pattern = re.compile(
        rf"\n*{re.escape(PUBLISH_RECORD_HEADING)}\n(?:.*\n?)*\Z",
        re.MULTILINE,
    )
    return pattern.sub("", markdown).rstrip() + "\n"


def prepare_markdown_for_wechat(markdown: str) -> str:
    cleaned = strip_yaml_frontmatter(markdown)
    cleaned = strip_publish_record_block(cleaned)
    return cleaned.strip() + "\n"


def is_placeholder_env_value(value: str) -> bool:
    normalized = value.strip()
    return not normalized or normalized in PLACEHOLDER_ENV_VALUES or normalized.startswith("REPLACE_WITH_")


def discover_publish_env_candidates() -> list[Path]:
    candidates = list(PUBLISH_ENV_CANDIDATES)
    candidates.extend(
        sorted(
            REPO_ROOT.glob(".claude/worktrees/*/skills/nk-wechat-mdnice-blue-html/scripts/publish_wechat.env.ps1")
        )
    )
    candidates.extend(
        sorted(
            REPO_ROOT.glob(".claude/worktrees/*/skills/wechat-mdnice-blue-html/scripts/publish_wechat.env.ps1")
        )
    )

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)
    return unique_candidates


def load_publish_env_from_paths(paths: list[Path]) -> dict[str, str]:
    loaded: dict[str, str] = {}
    pattern = re.compile(r'^\s*\$env:([A-Z0-9_]+)\s*=\s*"([^"]*)"\s*$')

    for candidate in paths:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line)
            if not match:
                continue
            key, value = match.groups()
            if not is_placeholder_env_value(value):
                loaded[key] = value
        if loaded:
            break

    return loaded


def load_publish_env_from_file() -> dict[str, str]:
    return load_publish_env_from_paths(discover_publish_env_candidates())


def load_publish_env_defaults() -> dict[str, str]:
    return load_publish_env_from_paths(PUBLISH_ENV_FALLBACK_CANDIDATES)


def resolve_gh_command() -> str:
    for candidate in ("gh.exe", "gh"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return ""


def load_github_token_from_gh() -> str:
    gh_command = resolve_gh_command()
    if not gh_command:
        return ""
    completed = subprocess.run(
        [gh_command, "auth", "token"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


def format_env_candidate_status() -> str:
    lines: list[str] = []
    for candidate in discover_publish_env_candidates():
        if candidate.exists():
            lines.append(f"- {candidate}: exists")
        else:
            lines.append(f"- {candidate}: missing")
    return "\n".join(lines)


def build_github_image_uploader(html_module: ModuleType):
    env_values = load_publish_env_from_file()
    fallback_values = load_publish_env_defaults()
    token = os.environ.get("GITHUB_TOKEN") or env_values.get("GITHUB_TOKEN", "") or load_github_token_from_gh()
    repo = os.environ.get("GITHUB_REPO") or env_values.get("GITHUB_REPO", "") or fallback_values.get("GITHUB_REPO", "")
    branch = (
        os.environ.get("GITHUB_BRANCH")
        or env_values.get("GITHUB_BRANCH", "")
        or fallback_values.get("GITHUB_BRANCH", "main")
        or "main"
    )
    directory = (
        os.environ.get("GITHUB_IMAGE_PATH")
        or env_values.get("GITHUB_IMAGE_PATH", "")
        or fallback_values.get("GITHUB_IMAGE_PATH", "images")
        or "images"
    )
    cdn = (
        os.environ.get("GITHUB_CDN")
        or env_values.get("GITHUB_CDN", "")
        or fallback_values.get("GITHUB_CDN", "jsdelivr")
        or "jsdelivr"
    )

    if not token or not repo:
        raise RuntimeError(
            "生成公众号发布 HTML 需要 GitHub 图床配置，但当前未找到 GITHUB_TOKEN / GITHUB_REPO。"
            "请先配置环境变量，或在以下任一正式配置文件中填写发布图床配置：\n"
            f"{format_env_candidate_status()}\n"
            "注意：publish_wechat.env.ps1.example 和 publish_wechat.env.template.ps1 只作为模板，不会当作正式密钥配置。"
        )

    return html_module.GitHubImageUploader(
        token=token,
        repo=repo,
        branch=branch,
        directory=directory,
        cdn=cdn,
    )


def load_brand_header_html() -> str:
    if not WECHAT_HEADER_TEMPLATE_PATH.exists():
        return ""
    return WECHAT_HEADER_TEMPLATE_PATH.read_text(encoding="utf-8").strip()


def render_brand_footer_html(
    html_module: ModuleType,
    *,
    theme: str,
    article_title: str,
    article_path: Path,
    article_markdown: str,
    current_published_url: str = "",
    promote_h2_to_h1: bool,
) -> str:
    footer_markdown = build_related_articles_footer_markdown(
        article_title=article_title,
        article_path=article_path,
        article_markdown=article_markdown,
        current_published_url=current_published_url,
    )
    if not footer_markdown:
        return ""

    temp_fragment_path = WECHAT_FOOTER_TEMPLATE_PATH.with_suffix(f".{theme}.temp.wechat.html")
    temp_preview_path = WECHAT_FOOTER_TEMPLATE_PATH.with_suffix(f".{theme}.temp.preview.html")
    result = html_module.convert_markdown_to_files(
        footer_markdown + "\n",
        title=f"{article_title}-footer",
        theme_name=theme,
        fragment_path=temp_fragment_path,
        preview_path=temp_preview_path,
        image_base_dir=WECHAT_FOOTER_TEMPLATE_PATH.parent,
        promote_h2_to_h1=promote_h2_to_h1,
    )

    for temp_path in (temp_fragment_path, temp_preview_path):
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass

    return extract_nice_inner_html(result.fragment_html).strip()


def normalize_title_for_match(title: str) -> str:
    cleaned = re.sub(r"^\d{4}年\d{1,2}月\d{1,2}日[-—]?", "", title.strip())
    cleaned = re.sub(r"[（(](改写版|修改版|修订版|优化版|排版版)[)）]", "", cleaned)
    return re.sub(r"\s+", "", cleaned).lower()


def tokenize_text(text: str) -> set[str]:
    tokens = set(re.findall(r"[A-Za-z0-9+#.]{2,}|[\u4e00-\u9fff]{2,}", text.lower()))
    stopwords = {
        "一个",
        "这件",
        "这篇",
        "但是",
        "为什么",
        "真正",
        "自己",
        "不是",
        "怎么",
        "什么",
        "起来",
        "工具",
        "系统",
        "文章",
        "改写版",
        "修改版",
        "修订版",
        "优化版",
        "排版版",
    }
    return {token for token in tokens if token not in stopwords}


def parse_datetime_text(value: str) -> dt.datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return dt.datetime.min


def parse_date_from_text(value: str) -> dt.datetime:
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return dt.datetime(year, month, day)
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return dt.datetime(year, month, day)
    return dt.datetime.min


def score_recency(published_at: dt.datetime, reference_date: dt.datetime) -> int:
    if published_at == dt.datetime.min or reference_date == dt.datetime.min:
        return 0
    days = abs((reference_date.date() - published_at.date()).days)
    if days <= 7:
        return 30
    if days <= 14:
        return 24
    if days <= 30:
        return 16
    if days <= 90:
        return 3
    return 0


def load_articles_from_library(path: Path = WECHAT_ARTICLE_LIBRARY_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    raw_articles = data.get("articles", []) if isinstance(data, dict) else data
    articles: list[dict[str, str]] = []
    if not isinstance(raw_articles, list):
        return articles
    for item in raw_articles:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or item.get("published_url") or "").strip()
        if title and url and url != "待补充":
            articles.append(
                {
                    "title": title,
                    "url": url,
                    "summary": str(item.get("digest") or item.get("summary") or "").strip(),
                    "published_at": str(item.get("published_at") or "").strip(),
                    "source": str(item.get("source") or "article_library").strip(),
                }
            )
    return articles


def parse_publish_index(index_path: Path) -> list[dict[str, str]]:
    if not index_path.exists():
        return []
    text = index_path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^##\s+(.+)$", text, re.MULTILINE))
    entries: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end() : block_end]
        entry: dict[str, str] = {"title": match.group(1).strip()}
        for line in block.splitlines():
            field_match = re.match(r"^-\s*([^：]+)：(.+)$", line.strip())
            if not field_match:
                continue
            key = field_match.group(1).strip()
            value = field_match.group(2).strip().strip("`")
            entry[key] = value
        if entry.get("发布链接") and entry["发布链接"] != "待补充":
            entries.append(
                {
                    "title": entry["title"],
                    "url": entry["发布链接"],
                    "summary": entry.get("列表摘要", ""),
                    "published_at": entry.get("发布时间", ""),
                    "source": "publish_index",
                }
            )
    return entries


def load_articles_from_publish_indexes() -> list[dict[str, str]]:
    articles: list[dict[str, str]] = []
    for index_path in REPO_ROOT.glob(f"07.发布文案/*/发布/{PUBLISH_INDEX_FILENAME}"):
        articles.extend(parse_publish_index(index_path))
    return articles


def load_related_article_candidates() -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for article in load_articles_from_publish_indexes() + load_articles_from_library():
        title = article.get("title", "").strip()
        url = article.get("url", "").strip()
        if not title or not url:
            continue
        key = url or normalize_title_for_match(title)
        current = merged.get(key, {})
        merged[key] = {**current, **{k: v for k, v in article.items() if v}}
    return list(merged.values())


def score_related_article(
    candidate: dict[str, str],
    *,
    article_title: str,
    article_markdown: str,
    reference_date: dt.datetime = dt.datetime.min,
) -> tuple[int, dt.datetime]:
    target_title = normalize_title_for_match(article_title)
    candidate_title = normalize_title_for_match(candidate.get("title", ""))
    if not candidate_title or candidate_title == target_title:
        return (-1, dt.datetime.min)

    source_text = f"{article_title}\n{article_markdown[:5000]}"
    target_tokens = tokenize_text(source_text)
    candidate_tokens = tokenize_text(f"{candidate.get('title', '')}\n{candidate.get('summary', '')}")
    overlap = target_tokens & candidate_tokens
    score = len(overlap) * 10

    candidate_text = f"{candidate.get('title', '')}\n{candidate.get('summary', '')}".lower()
    source_text_lower = source_text.lower()
    for keyword, weight in RELATED_KEYWORD_WEIGHTS.items():
        if keyword in source_text_lower and keyword in candidate_text:
            score += weight

    for keyword in ("ai", "编程", "工具", "教学", "中医", "coze", "openclaw"):
        if keyword in source_text_lower and keyword in candidate_text:
            score += 6

    published_at = parse_datetime_text(candidate.get("published_at", ""))
    score += score_recency(published_at, reference_date)
    if score == 0 and published_at > dt.datetime.min:
        score = 1
    return (score, published_at)


def select_related_articles(
    *,
    article_title: str,
    article_path: Path,
    article_markdown: str,
    current_published_url: str = "",
    limit: int = MAX_RELATED_ARTICLES,
) -> list[dict[str, str]]:
    candidates = load_related_article_candidates()
    current_path_text = article_path.stem
    current_url = current_published_url.strip()
    reference_date = parse_date_from_text(article_path.name)
    scored: list[tuple[tuple[int, dt.datetime], dict[str, str]]] = []
    for candidate in candidates:
        if current_url and candidate.get("url", "").strip() == current_url:
            continue
        if normalize_title_for_match(candidate.get("title", "")) == normalize_title_for_match(current_path_text):
            continue
        score = score_related_article(
            candidate,
            article_title=article_title,
            article_markdown=article_markdown,
            reference_date=reference_date,
        )
        if score[0] <= 0:
            continue
        scored.append((score, candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in scored[:limit]]


def build_related_articles_footer_markdown(
    *,
    article_title: str,
    article_path: Path,
    article_markdown: str,
    current_published_url: str = "",
) -> str:
    related_articles = select_related_articles(
        article_title=article_title,
        article_path=article_path,
        article_markdown=article_markdown,
        current_published_url=current_published_url,
    )
    if not related_articles:
        return ""

    lines = ["# 相关文章", ""]
    for article in related_articles:
        lines.append(f"[{article['title']}]({article['url']})")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def extract_nice_inner_html(fragment_html: str) -> str:
    match = re.search(
        r'<section id="nice"[^>]*>\s*(.*)\s*</section>\s*\Z',
        fragment_html,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return fragment_html.strip()


def inject_brand_segments(fragment_html: str, *, header_html: str, footer_html: str) -> str:
    if not header_html and not footer_html:
        return fragment_html

    match = re.search(r'(<section id="nice"[^>]*>)(.*?)(</section>)', fragment_html, re.DOTALL)
    if not match:
        return fragment_html

    open_tag, body_html, close_tag = match.groups()
    segments: list[str] = []
    if header_html:
        segments.append(header_html.strip())
    if body_html.strip():
        segments.append(body_html.strip())
    if footer_html:
        segments.append(footer_html.strip())

    combined_body = "\n\n".join(segment for segment in segments if segment)
    return f"{open_tag}\n{combined_body}\n{close_tag}"


def build_publish_package(
    *,
    article_path: Path,
    summary: str,
    cover_title: str = "",
    cover_subtitle: str = "",
    brand: str = "",
    accent: str = "",
    theme: str = "blue",
    published_url: str = "",
    promote_h2_to_h1: bool = False,
    copy_html: bool = False,
) -> tuple[Path, Path, Path, Path]:
    article_path = article_path.resolve()
    if not article_path.exists():
        raise FileNotFoundError(f"文章不存在：{article_path}")

    cover_module = load_module("build_wechat_cover_package", COVER_SCRIPT_PATH)
    html_module = load_module("convert_markdown", HTML_SCRIPT_PATH)
    image_uploader = build_github_image_uploader(html_module)

    markdown = article_path.read_text(encoding="utf-8")
    wechat_markdown = prepare_markdown_for_wechat(markdown)
    stem = article_path.stem
    date_prefix = cover_module.date_prefix_from_stem(stem)
    article_title = cover_module.title_from_markdown(
        wechat_markdown,
        cover_module.clean_article_name(stem),
    )

    cover_title = cover_title.strip() or cover_module.derive_cover_title(article_title)
    cover_subtitle = cover_subtitle.strip() or cover_module.derive_cover_subtitle(article_title, summary)
    brand = brand.strip() or cover_module.derive_brand(article_title, markdown)
    accent = accent.strip() or cover_module.derive_accent(article_title, summary)
    keywords = cover_module.derive_keywords(article_title, markdown)

    output_dir = article_path.parent / date_prefix
    cover_path = output_dir / f"{stem}-公众号封面.png"
    summary_path = output_dir / f"{stem}-公众号列表摘要.txt"
    hero_image = cover_module.choose_hero_image(
        cover_module.resolve_image_candidates(article_path, markdown)
    )

    cover_module.build_cover(
        output_path=cover_path,
        brand=brand,
        cover_title=cover_title,
        cover_subtitle=cover_subtitle,
        accent=accent,
        keywords=keywords,
        hero_image=hero_image,
    )
    cover_module.write_summary(summary_path, summary)

    fragment_path = html_module.derive_output_path(article_path, None, f".{theme}.wechat.html")
    preview_path = html_module.derive_output_path(article_path, None, f".{theme}.preview.html")
    html_result = html_module.convert_markdown_to_files(
        wechat_markdown,
        title=article_title,
        theme_name=theme,
        fragment_path=fragment_path,
        preview_path=preview_path,
        image_uploader=image_uploader,
        image_base_dir=article_path.parent,
        promote_h2_to_h1=promote_h2_to_h1 or theme == "blue",
    )

    header_html = load_brand_header_html()
    footer_html = render_brand_footer_html(
        html_module,
        theme=theme,
        article_title=article_title,
        article_path=article_path,
        article_markdown=wechat_markdown,
        current_published_url=published_url,
        promote_h2_to_h1=promote_h2_to_h1 or theme == "blue",
    )
    final_fragment_html = inject_brand_segments(
        html_result.fragment_html,
        header_html=header_html,
        footer_html=footer_html,
    )
    fragment_path.write_text(final_fragment_html, encoding="utf-8")
    preview_path.write_text(
        html_module.MarkdownToWechatHtml(
            theme_name=theme,
            promote_h2_to_h1=promote_h2_to_h1 or theme == "blue",
        ).wrap_full_html(final_fragment_html, article_title),
        encoding="utf-8",
    )

    if copy_html:
        html_module.copy_to_clipboard(final_fragment_html)

    return cover_path, summary_path, html_result.fragment_path, html_result.preview_path


def main() -> int:
    args = parse_args()
    cover_path, summary_path, fragment_path, preview_path = build_publish_package(
        article_path=Path(args.article),
        summary=args.summary,
        cover_title=args.cover_title,
        cover_subtitle=args.cover_subtitle,
        brand=args.brand,
        accent=args.accent,
        theme=args.theme,
        published_url=args.published_url,
        promote_h2_to_h1=args.promote_h2_to_h1,
        copy_html=args.copy_html,
    )

    print(cover_path)
    print(summary_path)
    print(fragment_path)
    print(preview_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
