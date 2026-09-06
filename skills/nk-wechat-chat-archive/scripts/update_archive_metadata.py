#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record an incremental WeChat archive boundary in raw and value-filter metadata."
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--previous-cutoff", required=True)
    parser.add_argument("--incremental-messages", required=True, type=int)
    parser.add_argument("--archive-latest", required=True)
    parser.add_argument("--requested-through", required=True, help="YYYY-MM-DD")
    parser.add_argument("--session-latest-observed")
    return parser.parse_args()


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    archive = Path(args.archive).resolve()
    requested = dt.datetime.strptime(args.requested_through, "%Y-%m-%d").date()
    excluded_from = requested + dt.timedelta(days=1)
    observed = args.session_latest_observed or args.archive_latest
    note = (
        f"已完整归档至用户指定的 {requested.isoformat()}；"
        f"{excluded_from.isoformat()} 及之后消息未纳入本次范围。"
    )
    shared = {
        "freshness_status": "complete",
        "scope_status": "complete_through_requested_date",
        "previous_cutoff": args.previous_cutoff,
        "incremental_messages": args.incremental_messages,
        "archive_latest": args.archive_latest,
        "session_latest": observed,
        "session_latest_observed": observed,
        "requested_through": requested.isoformat(),
        "freshness_note": note,
    }

    raw_path = archive / "归档说明.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw.update(shared)
    raw["output_dir"] = str(archive)
    write_json(raw_path, raw)

    value_path = archive / "价值过滤" / "价值过滤说明.json"
    if value_path.exists():
        value_dir = value_path.parent
        value = json.loads(value_path.read_text(encoding="utf-8"))
        value.update(shared)
        value["archive_dir"] = str(archive)
        value["output_dir"] = str(value_dir)
        value["value_files"] = [
            str(path.resolve()) for path in sorted(value_dir.glob("????-??-价值.md"))
        ]
        daily_dir = value_dir / "每日简报"
        value["daily_digest_files"] = [
            str(path.resolve()) for path in sorted(daily_dir.glob("????-??-??.md"))
        ]
        write_json(value_path, value)

    print(
        json.dumps(
            {
                "archive_latest": args.archive_latest,
                "session_latest_observed": observed,
                "requested_through": requested.isoformat(),
                "incremental_messages": args.incremental_messages,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
