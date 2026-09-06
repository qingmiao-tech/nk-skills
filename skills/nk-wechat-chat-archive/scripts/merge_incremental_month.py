#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path


MARKER = "## 聊天记录\n\n"
MESSAGE_RE = re.compile(
    r"(?m)^- \*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\*\*"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keep an existing monthly chat body and append messages after a verified cutoff."
    )
    parser.add_argument("--existing", required=True)
    parser.add_argument("--generated", required=True)
    parser.add_argument("--cutoff", required=True, help="Exact latest timestamp in the existing file.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-new", type=int)
    return parser.parse_args()


def split_document(text: str) -> tuple[str, str]:
    if MARKER not in text:
        raise RuntimeError("chat record marker not found")
    header, body = text.split(MARKER, 1)
    return header + MARKER, body


def message_blocks(body: str) -> list[tuple[str, str]]:
    matches = list(MESSAGE_RE.finditer(body))
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        blocks.append((match.group(1), body[match.start():end]))
    return blocks


def merge_documents(existing_text: str, generated_text: str, cutoff_text: str) -> tuple[str, int, int]:
    cutoff = dt.datetime.strptime(cutoff_text, "%Y-%m-%d %H:%M:%S")
    generated_header, generated_body = split_document(generated_text)
    _, existing_body = split_document(existing_text)
    existing_blocks = message_blocks(existing_body)
    if not existing_blocks:
        raise RuntimeError("existing archive contains no messages")
    existing_latest = dt.datetime.strptime(existing_blocks[-1][0], "%Y-%m-%d %H:%M:%S")
    if existing_latest != cutoff:
        raise RuntimeError(
            f"existing latest mismatch: expected {cutoff}, got {existing_latest}"
        )
    appended = [
        block
        for timestamp, block in message_blocks(generated_body)
        if dt.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S") > cutoff
    ]
    merged_body = existing_body.rstrip() + "\n\n" + "".join(appended).rstrip() + "\n"
    return generated_header + merged_body, len(existing_blocks), len(appended)


def main() -> int:
    args = parse_args()
    existing_path = Path(args.existing)
    generated_path = Path(args.generated)
    merged, existing_count, appended_count = merge_documents(
        existing_path.read_text(encoding="utf-8"),
        generated_path.read_text(encoding="utf-8"),
        args.cutoff,
    )
    if args.expected_new is not None and appended_count != args.expected_new:
        raise RuntimeError(
            f"new message count mismatch: expected {args.expected_new}, got {appended_count}"
        )
    Path(args.output).write_text(merged, encoding="utf-8")
    print(
        f"existing_messages={existing_count} appended_messages={appended_count} "
        f"total_messages={existing_count + appended_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
