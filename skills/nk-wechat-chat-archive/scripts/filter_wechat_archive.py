#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


MESSAGE_HEAD_RE = re.compile(r"^- \*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\*\* `([^`]+)`(?:\s*(.*))?$")
MONTH_FILE_RE = re.compile(r"^\d{4}-\d{2}\.md$")
IMAGE_RE = re.compile(r"!\[\]\(([^)]+)\)")
URL_RE = re.compile(r"https?://|www\.|github\.com|docs?\.|feishu\.cn|kdocs\.cn", re.IGNORECASE)

NOISE_SHORT_RE = re.compile(
    r"^(嗯+|啊+|哦+|好+|好的|可以|行|对|是的|不是|收到|已收到|谢谢|感谢|辛苦|"
    r"哈哈+|嘿嘿+|666+|牛|赞|ok|OK|mark|码住|蹲|学习了|已看|已阅|同问|求|"
    r"早|早上好|晚安|加油|冲|没事|嗯嗯|对的|是|不是的)$"
)
BRACKET_EMOJI_RE = re.compile(r"^(\[[^\]]{1,8}\]){1,6}$")

BASE_KEYWORDS = {
    "关键问答": [
        "#提问", "请教", "请问", "求问", "求助", "怎么", "如何", "为什么", "有没有",
        "能不能", "是不是", "哪里", "哪个", "吗", "？", "?",
    ],
    "工具资源": [
        "[链接/文件]", "链接", "文件", "文档", "教程", "资料", "下载", "网址", "github",
        "prompt", "Prompt", "插件", "工具", "模型", "AI", "GPT", "Claude", "Gemini",
        "DeepSeek", "小红书", "客服", "智能体", "Agent",
    ],
    "案例实操": [
        "案例", "实操", "测试", "截图", "设置", "流程", "步骤", "操作", "发布", "账号",
        "店铺", "商品", "选品", "模板", "投流", "笔记", "爆款", "转化", "跑通",
        "踩坑", "报错", "解决", "验证", "复盘", "配置", "关联",
    ],
    "方法总结": [
        "建议", "注意", "一定要", "不要", "需要", "最好", "可以先", "核心", "关键",
        "方法", "原则", "总结", "思路", "逻辑", "本质", "经验", "结论", "优先",
    ],
    "行动跟进": [
        "今天", "明天", "今晚", "本周", "截止", "报名", "提交", "记得", "提醒",
        "安排", "待办", "计划", "跟进", "清单", "行程", "会议", "直播", "作业",
    ],
}

PROFILE_KEYWORDS = {
    "learning": {
        "关键问答": ["课程", "学习", "作业", "老师", "助教", "答疑"],
        "案例实操": ["练习", "复盘", "手册"],
    },
    "project": {
        "行动跟进": ["需求", "进度", "风险", "上线", "交付", "版本", "排期"],
        "案例实操": ["BUG", "bug", "修复", "联调", "验收"],
    },
    "customer": {
        "行动跟进": ["客户", "需求", "报价", "合同", "付款", "售后", "风险"],
        "方法总结": ["沟通", "确认", "反馈"],
    },
    "activity": {
        "行动跟进": ["时间", "地点", "日程", "行程", "报名", "签到", "集合", "交通", "酒店"],
        "工具资源": ["资料", "链接", "地图", "地址"],
    },
    "general": {},
}

CATEGORY_ORDER = ["关键问答", "工具资源", "案例实操", "方法总结", "行动跟进", "图片资料", "上下文"]


@dataclass
class Message:
    timestamp: dt.datetime
    sender: str
    tail: str
    continuation: list[str]
    source_file: Path
    source_line: int
    month: str
    kind: str
    score: int = 0
    categories: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    noise: bool = False
    selected: bool = False

    @property
    def day(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")

    @property
    def body(self) -> str:
        lines = []
        if self.tail:
            lines.append(self.tail)
        lines.extend(self.continuation)
        return "\n".join(lines).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter archived WeChat monthly Markdown into value notes and daily briefs."
    )
    parser.add_argument("--archive-dir", required=True, help="Directory containing YYYY-MM.md archive files.")
    parser.add_argument("--output", help="Output directory. Defaults to <archive-dir>/价值过滤.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_KEYWORDS),
        default="learning",
        help="Keyword profile for digest focus.",
    )
    parser.add_argument("--min-score", type=int, default=4, help="Minimum score to keep a message.")
    parser.add_argument("--context-window", type=int, default=0, help="Keep nearby non-noise messages as context.")
    parser.add_argument("--image-context-window", type=int, default=2, help="Keep images near selected messages.")
    parser.add_argument("--image-context-minutes", type=int, default=8, help="Max minutes for image context rescue.")
    parser.add_argument("--daily-digest", action="store_true", help="Write per-day digest files.")
    parser.add_argument("--daily-limit", type=int, default=12, help="Max messages in each daily digest.")
    return parser.parse_args()


def read_archive_info(archive_dir: Path) -> dict:
    path = archive_dir / "归档说明.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def month_files(archive_dir: Path) -> list[Path]:
    return sorted(path for path in archive_dir.iterdir() if path.is_file() and MONTH_FILE_RE.match(path.name))


def parse_month_file(path: Path) -> tuple[str, list[Message]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    chat_name = ""
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        chat_name = re.sub(r"\s+-\s+\d{4}-\d{2}$", "", title)

    messages: list[Message] = []
    current: dict | None = None

    def flush_current() -> None:
        nonlocal current
        if not current:
            return
        body_lines = [current["tail"], *current["continuation"]]
        body = "\n".join(line for line in body_lines if line is not None)
        kind = detect_kind(current["sender"], body)
        messages.append(
            Message(
                timestamp=current["timestamp"],
                sender=current["sender"],
                tail=current["tail"],
                continuation=current["continuation"],
                source_file=path,
                source_line=current["source_line"],
                month=path.stem,
                kind=kind,
            )
        )
        current = None

    for index, line in enumerate(lines, start=1):
        match = MESSAGE_HEAD_RE.match(line)
        if match:
            flush_current()
            current = {
                "timestamp": dt.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S"),
                "sender": match.group(2),
                "tail": (match.group(3) or "").strip(),
                "continuation": [],
                "source_line": index,
            }
            continue
        if current is not None:
            if line == "":
                continue
            current["continuation"].append(line)

    flush_current()
    return chat_name, messages


def detect_kind(sender: str, body: str) -> str:
    if sender == "系统" or "[系统]" in body or "撤回了一条消息" in body:
        return "system"
    if IMAGE_RE.search(body):
        return "image"
    if "[链接/文件]" in body:
        return "link_or_file"
    if "[视频]" in body:
        return "video"
    return "text"


def clean_text(body: str) -> str:
    text = IMAGE_RE.sub(" ", body)
    text = re.sub(r"^\s*↳ 回复 .*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"\[[^\]]{1,8}\]", " ", text)
    text = re.sub(r"[`*_>#-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def is_noise(message: Message) -> bool:
    if message.kind == "system":
        return True
    text = clean_text(message.body)
    raw = re.sub(r"\s+", "", message.body)
    if not text and message.kind != "image":
        return True
    if "撤回了一条消息" in message.body:
        return True
    if BRACKET_EMOJI_RE.match(raw):
        return True
    if compact_len(text) <= 12 and NOISE_SHORT_RE.match(text):
        return True
    return False


def merged_keywords(profile: str) -> dict[str, list[str]]:
    merged = {category: list(words) for category, words in BASE_KEYWORDS.items()}
    for category, words in PROFILE_KEYWORDS.get(profile, {}).items():
        merged.setdefault(category, []).extend(words)
    return merged


def score_message(message: Message, profile: str) -> None:
    message.noise = is_noise(message)
    if message.noise:
        message.score = -10
        message.categories = []
        message.reasons = ["闲聊/系统消息"]
        return

    body = message.body
    text = clean_text(body)
    score = 0
    categories: list[str] = []
    reasons: list[str] = []
    keywords = merged_keywords(profile)

    if message.kind == "image":
        score += 1
        categories.append("图片资料")
        reasons.append("图片/截图")
    if message.kind == "link_or_file" or URL_RE.search(body):
        score += 3
        categories.append("工具资源")
        reasons.append("链接/文件/资源")

    for category in CATEGORY_ORDER:
        for word in keywords.get(category, []):
            if word in body:
                if category not in categories:
                    categories.append(category)
                score += 2 if category in {"关键问答", "案例实操", "方法总结"} else 1
                reasons.append(word)
                break

    text_length = compact_len(text)
    if text_length >= 80:
        score += 2
        reasons.append("长文本")
    elif text_length >= 32:
        score += 1
        reasons.append("信息量")

    if "↳ 回复" in body:
        score += 1
        reasons.append("上下文回复")
    if re.search(r"\d", body):
        score += 1
        reasons.append("包含数字")
    if "#" in body:
        score += 1
        reasons.append("标签")

    message.score = score
    message.categories = ordered_unique(categories)
    message.reasons = ordered_unique(reasons)


def ordered_unique(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def select_messages(messages: list[Message], args: argparse.Namespace) -> None:
    for message in messages:
        score_message(message, args.profile)
        message.selected = message.score >= args.min_score

    selected_indices = {index for index, message in enumerate(messages) if message.selected}

    for index, message in enumerate(messages):
        if message.selected or message.kind != "image" or message.noise:
            continue
        start = max(0, index - args.image_context_window)
        end = min(len(messages), index + args.image_context_window + 1)
        for nearby_index in range(start, end):
            nearby = messages[nearby_index]
            if not nearby.selected or nearby.day != message.day:
                continue
            delta = abs((nearby.timestamp - message.timestamp).total_seconds()) / 60
            if delta <= args.image_context_minutes:
                message.selected = True
                message.score = max(message.score, args.min_score)
                message.categories = ordered_unique(["图片资料", *message.categories])
                message.reasons = ordered_unique(["邻近高价值消息", *message.reasons])
                selected_indices.add(index)
                break

    if args.context_window <= 0:
        return
    for index in list(selected_indices):
        anchor = messages[index]
        start = max(0, index - args.context_window)
        end = min(len(messages), index + args.context_window + 1)
        for nearby_index in range(start, end):
            nearby = messages[nearby_index]
            if nearby.selected or nearby.noise or nearby.day != anchor.day:
                continue
            nearby.selected = True
            nearby.categories = ordered_unique(["上下文", *nearby.categories])
            nearby.reasons = ordered_unique(["邻近高价值消息", *nearby.reasons])
            nearby.score = max(nearby.score, args.min_score)


def primary_category(message: Message) -> str:
    for category in CATEGORY_ORDER:
        if category in message.categories:
            return category
    return "上下文"


def rewrite_image_refs(text: str, source_file: Path, output_file: Path) -> str:
    def replace(match: re.Match) -> str:
        rel = match.group(1)
        if rel.startswith(("http://", "https://", "data:")):
            return match.group(0)
        source_image = (source_file.parent / rel).resolve()
        new_rel = os.path.relpath(source_image, output_file.parent).replace("\\", "/")
        return f"![]({new_rel})"

    return IMAGE_RE.sub(replace, text)


def render_message(message: Message, output_file: Path, include_reason: bool = False) -> str:
    category = primary_category(message)
    first = f"- **{message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}** `{message.sender}` `{category}`"
    tail = rewrite_image_refs(message.tail, message.source_file, output_file)
    if tail:
        first = f"{first} {tail}"
    lines = [first.rstrip()]
    for line in message.continuation:
        lines.append(rewrite_image_refs(line, message.source_file, output_file))
    if include_reason:
        reasons = "、".join(message.reasons[:4]) if message.reasons else "规则命中"
        lines.append(f"  - 保留原因：{reasons}；得分：{message.score}")
    return "\n".join(lines)


def day_groups(messages: list[Message]) -> dict[str, list[Message]]:
    grouped: dict[str, list[Message]] = collections.defaultdict(list)
    for message in messages:
        if message.selected:
            grouped[message.day].append(message)
    return dict(sorted(grouped.items()))


def category_groups(messages: list[Message]) -> dict[str, list[Message]]:
    grouped: dict[str, list[Message]] = collections.defaultdict(list)
    for message in messages:
        grouped[primary_category(message)].append(message)
    return {category: grouped[category] for category in CATEGORY_ORDER if grouped.get(category)}


def write_month_value_file(
    output_dir: Path,
    chat_name: str,
    month: str,
    source_file: Path,
    month_messages: list[Message],
) -> Path:
    kept = [message for message in month_messages if message.selected]
    output_file = output_dir / f"{month}-价值.md"
    source_rel = os.path.relpath(source_file.resolve(), output_file.parent).replace("\\", "/")
    keep_rate = f"{len(kept) / len(month_messages):.1%}" if month_messages else "0%"
    lines = [
        f"# {chat_name} - {month} 价值过滤",
        "",
        f"- 来源归档：`{source_rel}`",
        f"- 原始消息：{len(month_messages)}",
        f"- 保留消息：{len(kept)}",
        f"- 过滤比例：{keep_rate}",
        "- 说明：自动过滤寒暄、系统消息和低信息密度短句，保留关键问答、工具资源、案例实操、方法总结、行动跟进和相关图片。",
        "",
    ]
    if not kept:
        lines.extend(["## 本月未筛出高价值消息", ""])
    for day, items in day_groups(month_messages).items():
        lines.extend([f"## {day}", ""])
        for category, category_items in category_groups(items).items():
            lines.extend([f"### {category}", ""])
            for message in category_items:
                lines.append(render_message(message, output_file))
                lines.append("")
    output_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_file


def excerpt(message: Message, limit: int = 90) -> str:
    text = clean_text(message.body)
    if not text and message.kind == "image":
        text = "图片/截图"
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def write_daily_digest(output_dir: Path, chat_name: str, day: str, messages: list[Message], limit: int) -> Path:
    daily_dir = output_dir / "每日简报"
    daily_dir.mkdir(parents=True, exist_ok=True)
    output_file = daily_dir / f"{day}.md"
    ranked = sorted(messages, key=lambda item: (-item.score, item.timestamp))[:limit]
    by_category = category_groups(ranked)
    lines = [
        f"# {chat_name} - {day} 学习简报",
        "",
        f"- 高价值消息：{len(messages)}",
        f"- 简报摘录：{len(ranked)}",
        "",
        "## 今日重点",
        "",
    ]
    for message in ranked[:5]:
        lines.append(f"- `{primary_category(message)}` {excerpt(message)}")
    lines.append("")
    for category, items in by_category.items():
        lines.extend([f"## {category}", ""])
        for message in sorted(items, key=lambda item: item.timestamp):
            lines.append(render_message(message, output_file, include_reason=True))
            lines.append("")
    output_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_file


def clean_generated_output(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for path in output_dir.glob("*-价值.md"):
        path.unlink()
    summary = output_dir / "价值过滤说明.json"
    if summary.exists():
        summary.unlink()
    daily_dir = output_dir / "每日简报"
    if daily_dir.exists():
        for path in daily_dir.glob("*.md"):
            path.unlink()


def main() -> int:
    args = parse_args()
    archive_dir = Path(args.archive_dir).resolve()
    output_dir = Path(args.output).resolve() if args.output else archive_dir / "价值过滤"
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_generated_output(output_dir)

    archive_info = read_archive_info(archive_dir)
    all_messages: list[Message] = []
    detected_chat_name = archive_info.get("chat") or archive_dir.name
    source_months: dict[str, Path] = {}

    files = month_files(archive_dir)
    if not files:
        raise FileNotFoundError(f"未找到月度归档文件: {archive_dir / 'YYYY-MM.md'}")

    for file in files:
        chat_name, messages = parse_month_file(file)
        if chat_name:
            detected_chat_name = chat_name
        source_months[file.stem] = file
        all_messages.extend(messages)

    select_messages(all_messages, args)

    messages_by_month: dict[str, list[Message]] = collections.defaultdict(list)
    for message in all_messages:
        messages_by_month[message.month].append(message)

    value_files = []
    for month, messages in sorted(messages_by_month.items()):
        value_files.append(
            write_month_value_file(output_dir, detected_chat_name, month, source_months[month], messages)
        )

    daily_files = []
    if args.daily_digest:
        selected_by_day: dict[str, list[Message]] = collections.defaultdict(list)
        for message in all_messages:
            if message.selected:
                selected_by_day[message.day].append(message)
        for day, messages in sorted(selected_by_day.items()):
            daily_files.append(write_daily_digest(output_dir, detected_chat_name, day, messages, args.daily_limit))

    selected = [message for message in all_messages if message.selected]
    categories = collections.Counter(primary_category(message) for message in selected)
    summary = {
        "chat": detected_chat_name,
        "profile": args.profile,
        "archive_dir": str(archive_dir),
        "output_dir": str(output_dir),
        "source_messages": len(all_messages),
        "kept_messages": len(selected),
        "removed_messages": len(all_messages) - len(selected),
        "keep_rate": round(len(selected) / len(all_messages), 4) if all_messages else 0,
        "months": {
            month: {
                "source": len(messages),
                "kept": sum(1 for message in messages if message.selected),
            }
            for month, messages in sorted(messages_by_month.items())
        },
        "categories": dict(categories),
        "value_files": [str(path) for path in value_files],
        "daily_digest_files": [str(path) for path in daily_files],
    }
    (output_dir / "价值过滤说明.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
