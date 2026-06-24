#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)(\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]+"),
]

PATH_PATTERN = re.compile(
    r"(?i)([a-z]:[\\/][^\s\"'`<>|]+|(?:\.{1,2}[\\/])?[a-z0-9_.\-\u4e00-\u9fff]+(?:[\\/][a-z0-9_.\-\u4e00-\u9fff]+)+)"
)
COMMAND_HINT_PATTERN = re.compile(
    r"(?i)\b(rg|git|python|node|npm|pnpm|mvn|gradle|docker|kubectl|lark-cli|hermes|codex|claude|pwsh|powershell)\b[^\n\r]{0,180}"
)
ERROR_PATTERN = re.compile(
    r"(?i)(error|exception|failed|timeout|permission denied|traceback|错误|失败|异常|超时|权限)"
)


def redact(text: str) -> str:
    value = text
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(lambda match: f"{match.group(1)}{match.group(2) if match.lastindex and match.lastindex >= 2 else ''}[REDACTED]", value)
    return value


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("input_text") or item.get("output_text") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("input_text") or content.get("output_text") or "")
    return ""


def message_text(payload: dict[str, Any]) -> tuple[str, str]:
    role = payload.get("role") or ""
    content = payload.get("content")
    if payload.get("type") == "message":
        return role, text_from_content(content)
    return role, ""


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"type": "raw", "payload": {"text": line}})
    return events


def first_sentence(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def unique(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip().rstrip(".,;)")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def build_digest(events: list[dict[str, Any]], source: Path) -> str:
    session_meta: dict[str, Any] = {}
    user_messages: list[str] = []
    assistant_messages: list[str] = []
    event_types: Counter[str] = Counter()
    paths: list[str] = []
    commands: list[str] = []
    errors: list[str] = []

    for event in events:
        event_type = str(event.get("type") or "")
        event_types[event_type] += 1
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}

        if event_type == "session_meta":
            session_meta = payload

        text = ""
        if event_type == "response_item" and isinstance(payload, dict):
            role, text = message_text(payload)
            if role == "user" and text:
                user_messages.append(redact(text))
            elif role == "assistant" and text:
                assistant_messages.append(redact(text))
        elif event_type == "event_msg" and isinstance(payload, dict):
            text = text_from_content(payload.get("message") or payload.get("text") or "")
        elif event_type == "raw":
            text = text_from_content(payload.get("text") or "")

        if text:
            clean = redact(text)
            paths.extend(PATH_PATTERN.findall(clean))
            commands.extend(match.group(0) for match in COMMAND_HINT_PATTERN.finditer(clean))
            if ERROR_PATTERN.search(clean):
                errors.append(first_sentence(clean, 240))

    title_seed = first_sentence(user_messages[0], 80) if user_messages else source.stem
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session_id = session_meta.get("id") or ""
    cwd = session_meta.get("cwd") or ""

    lines = [
        f"# Codex 会话证据包：{title_seed}",
        "",
        "## 元数据",
        "",
        f"- 生成时间: {now}",
        f"- session_id: {session_id}",
        f"- cwd: {cwd}",
        f"- rollout_path: {source}",
        f"- 事件数: {len(events)}",
        f"- 事件类型: {', '.join(f'{key}={value}' for key, value in event_types.most_common())}",
        "",
        "## 用户请求摘录",
        "",
    ]

    for index, message in enumerate(user_messages[:12], 1):
        lines.append(f"{index}. {first_sentence(message, 260)}")

    lines.extend(["", "## 助手关键回复摘录", ""])
    for index, message in enumerate(assistant_messages[-12:], 1):
        lines.append(f"{index}. {first_sentence(message, 320)}")

    lines.extend(["", "## 路径线索", ""])
    for item in unique(paths, 40):
        lines.append(f"- `{item}`")

    lines.extend(["", "## 命令线索", ""])
    for item in unique(commands, 40):
        lines.append(f"- `{item}`")

    lines.extend(["", "## 错误与风险线索", ""])
    if errors:
        for item in unique(errors, 20):
            lines.append(f"- {item}")
    else:
        lines.append("- 未在会话文本中发现明显错误关键词。")

    lines.extend(
        [
            "",
            "## 沉淀判断待填",
            "",
            "- 建议评分:",
            "- 建议类型: 不沉淀 / 轻量 handoff / 正式知识库文档",
            "- 建议目录:",
            "- 必须保留的事实:",
            "- 需要脱敏或跳过的内容:",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract a compact digest from a Codex JSONL session.")
    parser.add_argument("--input", required=True, help="Path to a Codex rollout JSONL file.")
    parser.add_argument("--output", help="Optional Markdown output path. Prints to stdout when omitted.")
    return parser.parse_args()


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    configure_stdout()
    args = parse_args()
    source = Path(args.input).expanduser().resolve()
    digest = build_digest(load_events(source), source)
    if args.output:
        target = Path(args.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(digest, encoding="utf-8", newline="\n")
        print(target)
        return 0
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
