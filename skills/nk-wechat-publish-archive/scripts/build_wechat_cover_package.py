#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


DATE_PREFIX_RE = re.compile(r"^(\d{4}年\d{1,2}月\d{1,2}日)")
IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
PREFERRED_IMAGE_KEYWORDS = (
    "teacher",
    "cockpit",
    "dashboard",
    "student",
    "grade",
    "detail",
    "login",
    "zhishulinghang",
    "qihuangzhishu",
)
KEYWORD_CANDIDATES = (
    "SQL规范",
    "安全意识",
    "性能优化",
    "表设计",
    "能力画像",
    "知识图谱",
    "教学反馈",
    "数据库课",
    "资源推荐",
    "精准干预",
    "学生画像",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a WeChat cover image and list summary beside an article.")
    parser.add_argument("--article", required=True, help="Absolute or relative path to the markdown article.")
    parser.add_argument("--summary", required=True, help="WeChat list summary text.")
    parser.add_argument("--cover-title", default="", help="Short cover headline.")
    parser.add_argument("--cover-subtitle", default="", help="Cover subtitle.")
    parser.add_argument("--brand", default="", help="Brand badge text.")
    parser.add_argument("--accent", default="", help="Optional accent badge text.")
    return parser.parse_args()


def clean_article_name(stem: str) -> str:
    return re.sub(r"（[^）]*版）$", "", stem).strip()


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


def derive_cover_title(title: str) -> str:
    title = re.sub(r"（[^）]*）", "", title).strip()
    parts = [part.strip() for part in re.split(r"[——:：]", title) if part.strip()]
    if parts:
        primary = parts[0]
    else:
        primary = title
    primary = primary.replace("别再用", "别再只看").replace("评价学生了", "那个分数")
    if len(primary) <= 12:
        return primary
    return primary[:12]


def derive_cover_subtitle(title: str, summary: str) -> str:
    title = re.sub(r"（[^）]*）", "", title).strip()
    parts = [part.strip() for part in re.split(r"[——:：]", title) if part.strip()]
    if len(parts) >= 2:
        return parts[1][:24]
    sentence = re.split(r"[。！？!?\n]", summary.strip())[0].strip()
    return sentence[:24] if sentence else title[:24]


def derive_brand(title: str, markdown: str) -> str:
    title_lower = title.lower()
    markdown_lower = markdown.lower()
    if "智数领航" in title or "zhishulinghang" in markdown_lower:
        return "智数领航 · 数据库教学"
    if "岐黄智枢" in title or "qihuangzhishu" in markdown_lower:
        return "岐黄智枢 · 中医教学"
    if "公众号" in title or "文章" in title:
        return "公众号内容封面"
    return "内容策划 · 公众号封面"


def derive_accent(title: str, summary: str) -> str:
    if "分数" in title or "总分" in summary:
        return "能力画像"
    if "教学" in title:
        return "精准干预"
    if "AI" in title:
        return "真实案例"
    return "核心观点"


def resolve_image_candidates(article_path: Path, markdown: str) -> list[Path]:
    candidates: list[Path] = []
    parent_assets = article_path.parent / "assets"
    if parent_assets.exists():
        for file_path in parent_assets.iterdir():
            if file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                candidates.append(file_path)

    for match in IMAGE_REF_RE.findall(markdown):
        if match.startswith("http://") or match.startswith("https://"):
            continue
        image_path = (article_path.parent / match).resolve()
        if image_path.exists() and image_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            candidates.append(image_path)

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def choose_hero_image(candidates: Iterable[Path]) -> Path | None:
    ranked: list[tuple[int, Path]] = []
    for path in candidates:
        score = 0
        lowered = path.name.lower()
        for index, keyword in enumerate(PREFERRED_IMAGE_KEYWORDS):
            if keyword in lowered:
                score += 100 - index * 5
        ranked.append((score, path))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked else None


def derive_keywords(title: str, markdown: str) -> list[str]:
    source = f"{title}\n{markdown}"
    picked = [word for word in KEYWORD_CANDIDATES if word in source]
    if len(picked) >= 4:
        return picked[:4]
    fallback = ["能力画像", "精准干预", "课堂反馈", "教学改进"]
    for word in fallback:
        if word not in picked:
            picked.append(word)
        if len(picked) == 4:
            break
    return picked[:4]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:/Windows/Fonts/msyhbd.ttc" if bold else r"C:/Windows/Fonts/msyh.ttc",
        r"C:/Windows/Fonts/simhei.ttf" if bold else r"C:/Windows/Fonts/simhei.ttf",
        r"C:/Windows/Fonts/arialbd.ttf" if bold else r"C:/Windows/Fonts/arial.ttf",
    ]
    for item in candidates:
        path = Path(item)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def wrap_two_lines(text: str, first_limit: int = 6) -> tuple[str, str]:
    compact = text.strip()
    if len(compact) <= first_limit:
        return compact, ""
    return compact[:first_limit], compact[first_limit:first_limit * 2 + 4]


def build_cover(
    output_path: Path,
    brand: str,
    cover_title: str,
    cover_subtitle: str,
    accent: str,
    keywords: list[str],
    hero_image: Path | None,
) -> None:
    width, height = 900, 383
    canvas = Image.new("RGB", (width, height), "#f7fbff")
    draw = ImageDraw.Draw(canvas)

    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(246 * (1 - t) + 232 * t)
        g = int(251 * (1 - t) + 244 * t)
        b = int(255 * (1 - t) + 249 * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    for x in range(-60, width + 80, 48):
        draw.line([(x, 0), (x + 160, height)], fill=(218, 229, 242), width=1)
    for y in range(36, height, 52):
        draw.line([(0, y), (width, y)], fill=(229, 237, 246), width=1)

    screenshot = None
    if hero_image is not None:
        screenshot = Image.open(hero_image).convert("RGB")
        screenshot = ImageOps.fit(
            screenshot,
            (430, 250),
            method=Image.Resampling.LANCZOS,
            centering=(0.52, 0.50),
        )

    card = Image.new("RGBA", (470, 292), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card)
    shadow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((18, 20, 454, 278), radius=18, fill=(32, 76, 120, 38))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    card.alpha_composite(shadow)
    card_draw.rounded_rectangle((14, 12, 456, 270), radius=18, fill=(255, 255, 255, 235), outline=(201, 220, 238, 255), width=1)
    card_draw.rounded_rectangle((14, 12, 456, 44), radius=18, fill=(238, 246, 253, 255))
    card_draw.rectangle((14, 30, 456, 44), fill=(238, 246, 253, 255))
    for index, color in enumerate(["#ff6b6b", "#ffd166", "#06d6a0"]):
        card_draw.ellipse((32 + index * 18, 24, 42 + index * 18, 34), fill=color)

    if screenshot is not None:
        card.alpha_composite(screenshot.convert("RGBA"), (34, 52))
    else:
        placeholder = Image.new("RGBA", (430, 250), (243, 248, 253, 255))
        placeholder_draw = ImageDraw.Draw(placeholder)
        placeholder_draw.rounded_rectangle((0, 0, 429, 249), radius=16, fill=(243, 248, 253, 255), outline=(212, 226, 239, 255))
        placeholder_draw.text((28, 30), "公众号封面模板", font=font(24, True), fill=(39, 92, 146))
        placeholder_draw.text((28, 78), "这里将优先使用文章内截图", font=font(18, False), fill=(98, 118, 139))
        placeholder_draw.text((28, 112), "没有截图时自动使用通用版式", font=font(18, False), fill=(98, 118, 139))
        placeholder_draw.rounded_rectangle((28, 158, 192, 196), radius=18, fill=(58, 122, 255), outline=None)
        placeholder_draw.rounded_rectangle((204, 158, 338, 196), radius=18, fill=(18, 184, 134), outline=None)
        placeholder_draw.rounded_rectangle((126, 206, 274, 242), radius=18, fill=(139, 92, 246), outline=None)
        card.alpha_composite(placeholder, (34, 52))

    canvas.paste(card.convert("RGB"), (405, 56), card)
    draw = ImageDraw.Draw(canvas)

    left_overlay = Image.new("RGBA", (520, height), (247, 251, 255, 0))
    overlay_draw = ImageDraw.Draw(left_overlay)
    overlay_draw.rectangle((0, 0, 520, height), fill=(247, 251, 255, 212))
    canvas.paste(left_overlay.convert("RGB"), (0, 0), left_overlay)
    draw = ImageDraw.Draw(canvas)

    badge_font = font(22, True)
    title_font = font(50, True)
    subtitle_font = font(24, False)
    tag_font = font(19, True)
    small_font = font(16, False)
    accent_font = font(18, True)

    badge_box = draw.textbbox((0, 0), brand, font=badge_font)
    badge_width = badge_box[2] - badge_box[0] + 36
    draw.rounded_rectangle((48, 38, 48 + badge_width, 72), radius=17, fill=(224, 241, 255), outline=(174, 211, 238))
    draw.text((64, 43), brand, font=badge_font, fill=(30, 91, 145))

    title_line1, title_line2 = wrap_two_lines(cover_title, first_limit=6)
    draw.text((48, 103), title_line1, font=title_font, fill=(18, 43, 69))
    if title_line2:
        draw.text((48, 165), title_line2, font=title_font, fill=(18, 43, 69))
    underline_y = 227 if title_line2 else 165
    for index in range(5):
        draw.line((52, underline_y + index, 274, underline_y + index), fill=(255, 195, 77), width=1)
    draw.text((50, 246), cover_subtitle, font=subtitle_font, fill=(63, 85, 106))

    accent_card = Image.new("RGBA", (178, 96), (0, 0, 0, 0))
    accent_draw = ImageDraw.Draw(accent_card)
    accent_draw.rounded_rectangle((10, 10, 168, 86), radius=18, fill=(255, 255, 255, 238), outline=(218, 226, 236), width=2)
    accent_draw.text((34, 34), accent, font=accent_font, fill=(96, 111, 128))
    accent_draw.line((28, 66, 148, 24), fill=(255, 96, 87), width=6)
    accent_card = accent_card.rotate(-7, resample=Image.Resampling.BICUBIC, expand=True)
    canvas.paste(accent_card.convert("RGB"), (288, 128), accent_card)

    footer_band = Image.new("RGBA", (470, 44), (27, 83, 132, 235))
    footer_draw = ImageDraw.Draw(footer_band)
    footer_draw.rounded_rectangle((0, 0, 470, 44), radius=22, fill=(27, 83, 132, 235))
    footer_message = cover_subtitle if len(cover_subtitle) <= 21 else cover_subtitle[:21]
    footer_box = footer_draw.textbbox((0, 0), footer_message, font=tag_font)
    footer_draw.text(((470 - (footer_box[2] - footer_box[0])) / 2, 10), footer_message, font=tag_font, fill="white")
    canvas.paste(footer_band.convert("RGB"), (48, 306), footer_band)

    base_x = 600
    base_y = 300
    colors = ["#377dff", "#ff6b5f", "#12b886", "#8b5cf6"]
    positions = [(0, 0), (108, -18), (192, 18), (64, 36)]
    for (offset_x, offset_y), label, color in zip(positions, keywords, colors):
        x = base_x + offset_x
        y = base_y + offset_y
        draw.rounded_rectangle((x - 45, y - 18, x + 45, y + 18), radius=18, fill=color)
        box = draw.textbbox((0, 0), label, font=small_font)
        draw.text((x - (box[2] - box[0]) / 2, y - 10), label, font=small_font, fill="white")

    db_x, db_y = 372, 55
    draw.ellipse((db_x - 28, db_y - 10, db_x + 28, db_y + 10), fill=(255, 255, 255), outline=(73, 145, 207), width=2)
    draw.rectangle((db_x - 28, db_y - 10, db_x + 28, db_y + 36), fill=(255, 255, 255), outline=(73, 145, 207), width=2)
    draw.ellipse((db_x - 28, db_y + 26, db_x + 28, db_y + 46), fill=(220, 240, 255), outline=(73, 145, 207), width=2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=95)


def write_summary(output_path: Path, summary: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary.strip() + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    article_path = Path(args.article).resolve()
    if not article_path.exists():
        raise FileNotFoundError(f"文章不存在：{article_path}")

    markdown = article_path.read_text(encoding="utf-8")
    stem = article_path.stem
    date_prefix = date_prefix_from_stem(stem)
    article_title = title_from_markdown(markdown, clean_article_name(stem))

    cover_title = args.cover_title.strip() or derive_cover_title(article_title)
    cover_subtitle = args.cover_subtitle.strip() or derive_cover_subtitle(article_title, args.summary)
    brand = args.brand.strip() or derive_brand(article_title, markdown)
    accent = args.accent.strip() or derive_accent(article_title, args.summary)
    keywords = derive_keywords(article_title, markdown)

    output_dir = article_path.parent / date_prefix
    hero_image = choose_hero_image(resolve_image_candidates(article_path, markdown))
    cover_path = output_dir / f"{stem}-公众号封面.png"
    summary_path = output_dir / f"{stem}-公众号列表摘要.txt"

    build_cover(
        output_path=cover_path,
        brand=brand,
        cover_title=cover_title,
        cover_subtitle=cover_subtitle,
        accent=accent,
        keywords=keywords,
        hero_image=hero_image,
    )
    write_summary(summary_path, args.summary)

    print(cover_path)
    print(summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
