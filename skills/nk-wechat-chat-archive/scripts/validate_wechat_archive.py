#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


MESSAGE_RE = re.compile(r"(?m)^- \*\*\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\*\*")
IMAGE_RE = re.compile(r"!\[\]\(([^)]+)\)")
MONTH_RE = re.compile(r"^\d{4}-\d{2}\.md$")
MARKER = "## 聊天记录\n\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate message counts, image references, value output, and incremental preservation."
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--expected-messages", type=int)
    parser.add_argument("--expected-images", type=int)
    parser.add_argument("--expected-latest")
    parser.add_argument("--expected-requested-through")
    parser.add_argument("--expected-incremental", type=int)
    parser.add_argument("--history-baseline", help="Directory used to compare unchanged monthly files.")
    parser.add_argument("--changed-month", action="append", default=[], help="Month allowed to differ, repeatable.")
    parser.add_argument("--prefix-baseline", help="Directory whose changed-month bodies must be preserved as prefixes.")
    parser.add_argument("--forbid-month", action="append", default=[], help="Month that must not exist, repeatable.")
    parser.add_argument("--metadata-forbid", action="append", default=[], help="Text forbidden in metadata paths.")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_refs(files: list[Path]) -> tuple[int, list[tuple[str, str]]]:
    total = 0
    missing = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        for match in IMAGE_RE.finditer(text):
            total += 1
            target = (file.parent / match.group(1)).resolve()
            if not target.exists():
                missing.append((str(file), match.group(1)))
    return total, missing


def archive_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if MARKER not in text:
        raise RuntimeError(f"chat record marker not found: {path}")
    return text.split(MARKER, 1)[1]


def main() -> int:
    args = parse_args()
    archive = Path(args.archive).resolve()
    summary_path = archive / "归档说明.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    month_files = sorted(path for path in archive.iterdir() if path.is_file() and MONTH_RE.fullmatch(path.name))
    markdown_messages = sum(
        len(MESSAGE_RE.findall(path.read_text(encoding="utf-8"))) for path in month_files
    )
    raw_refs, raw_missing = count_refs(month_files)
    asset_files = [path for path in (archive / "assets").rglob("*") if path.is_file()]

    value_summary_path = archive / "价值过滤" / "价值过滤说明.json"
    value_summary = (
        json.loads(value_summary_path.read_text(encoding="utf-8"))
        if value_summary_path.exists()
        else None
    )
    value_files = sorted((archive / "价值过滤").glob("????-??-价值.md"))
    daily_files = sorted((archive / "价值过滤" / "每日简报").glob("????-??-??.md"))
    derived_refs, derived_missing = count_refs(value_files + daily_files)

    history_hashes_equal = True
    prefix_months_preserved = True
    changed = set(args.changed_month)
    if args.history_baseline:
        baseline = Path(args.history_baseline).resolve()
        baseline_files = sorted(
            path for path in baseline.iterdir()
            if path.is_file() and MONTH_RE.fullmatch(path.name)
        )
        for previous in baseline_files:
            month = previous.stem
            if month in changed:
                continue
            current = archive / previous.name
            history_hashes_equal &= current.exists() and sha256(current) == sha256(previous)
    if args.prefix_baseline:
        baseline = Path(args.prefix_baseline).resolve()
        for month in changed:
            previous = baseline / f"{month}.md"
            current = archive / f"{month}.md"
            if previous.exists():
                prefix_months_preserved &= current.exists() and archive_body(current).startswith(
                    archive_body(previous)
                )

    metadata_text = json.dumps(
        {"raw": summary, "value": value_summary}, ensure_ascii=False
    )
    forbidden_metadata = [text for text in args.metadata_forbid if text in metadata_text]
    forbidden_months = [month for month in args.forbid_month if (archive / f"{month}.md").exists()]

    expected_messages = args.expected_messages if args.expected_messages is not None else summary.get("messages")
    expected_images = args.expected_images if args.expected_images is not None else summary.get("image_messages")
    result = {
        "summary_messages": summary.get("messages"),
        "markdown_messages": markdown_messages,
        "summary_images": summary.get("image_messages"),
        "decoded_images": summary.get("decoded_images"),
        "images_skipped": summary.get("images_skipped", 0),
        "raw_image_refs": raw_refs,
        "asset_files": len(asset_files),
        "missing_raw_image_refs": len(raw_missing),
        "value_source_messages": value_summary.get("source_messages") if value_summary else None,
        "kept_messages": value_summary.get("kept_messages") if value_summary else None,
        "daily_digest_files": len(daily_files),
        "latest_daily_digest": daily_files[-1].stem if daily_files else None,
        "derived_image_refs": derived_refs,
        "missing_derived_image_refs": len(derived_missing),
        "month_files": [path.name for path in month_files],
        "history_hashes_equal": history_hashes_equal,
        "prefix_months_preserved": prefix_months_preserved,
        "forbidden_months_found": forbidden_months,
        "forbidden_metadata_found": forbidden_metadata,
        "archive_latest": summary.get("archive_latest"),
        "requested_through": summary.get("requested_through"),
        "incremental_messages": summary.get("incremental_messages"),
    }
    expected_decoded_images = expected_images - result["images_skipped"]
    checks = [
        result["summary_messages"] == expected_messages,
        result["markdown_messages"] == expected_messages,
        result["summary_images"] == expected_images,
        0 <= result["images_skipped"] <= expected_images,
        result["decoded_images"] == expected_decoded_images,
        result["raw_image_refs"] == expected_decoded_images,
        result["asset_files"] == expected_decoded_images,
        result["missing_raw_image_refs"] == 0,
        result["missing_derived_image_refs"] == 0,
        result["history_hashes_equal"],
        result["prefix_months_preserved"],
        not result["forbidden_months_found"],
        not result["forbidden_metadata_found"],
    ]
    if value_summary:
        checks.append(result["value_source_messages"] == expected_messages)
    if args.expected_latest:
        checks.append(result["archive_latest"] == args.expected_latest)
    if args.expected_requested_through:
        checks.append(result["requested_through"] == args.expected_requested_through)
    if args.expected_incremental is not None:
        checks.append(result["incremental_messages"] == args.expected_incremental)
    result["passed"] = all(checks)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
