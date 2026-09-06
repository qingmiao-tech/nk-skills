#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path, PurePath


TYPE_MAP = {
    1: "text",
    3: "image",
    34: "voice",
    43: "video",
    47: "sticker",
    48: "location",
    49: "link_or_file",
    10000: "system",
}
MESSAGE_COLUMNS = (
    "local_id, local_type, server_id, real_sender_id, create_time, "
    "message_content, packed_info_data, sort_seq"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export one chat from a local Windows WeChat 4.x account."
    )
    parser.add_argument("--wechatauto-repo", required=True, help="Checkout containing wechatauto/db.py.")
    parser.add_argument("--db-root", required=True, help="xwechat_files directory containing account folders.")
    parser.add_argument("--account", help="Account folder name. Defaults to the most recently active account.")
    parser.add_argument("--workdir", required=True, help="Private key and decrypted database cache.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--chat", help="Exact chat name, username, or message-table md5.")
    source.add_argument("--archive-summary", help="Existing 归档说明.json used to reuse exact chat identity.")
    parser.add_argument("--output", required=True, help="Filtered or complete chat JSON output.")
    parser.add_argument("--full-output", help="Optional copy of the complete current chat JSON.")
    parser.add_argument("--image-config", help="Optional private image key JSON output for the archive step.")
    parser.add_argument("--through", help="Inclusive local cutoff: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.")
    parser.add_argument("--previous-cutoff", help="Previous inclusive cutoff used for incremental statistics.")
    parser.add_argument("--expected-previous-count", type=int, help="Fail if the old range count has drifted.")
    return parser.parse_args()


def load_database_module(repo: Path):
    module_path = repo / "wechatauto" / "db.py"
    spec = importlib.util.spec_from_file_location("wechat_archive_db", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load database module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_local_time(value: str, end_of_day: bool = False) -> dt.datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d" and end_of_day:
                parsed = parsed.replace(hour=23, minute=59, second=59)
            return parsed
        except ValueError:
            continue
    raise ValueError(f"invalid local time: {value}")


def message_identity(message: dict) -> tuple:
    return message["source_db"], message["local_id"]


def format_timestamp(messages: list[dict], index: int) -> str | None:
    if not messages:
        return None
    return dt.datetime.fromtimestamp(messages[index]["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")


def resolve_chat(db, query: str) -> tuple[str, str, str]:
    chats = db.list_message_chats()
    query_folded = query.casefold()
    exact = [
        item for item in chats
        if query in {item.get("username"), item.get("md5"), item.get("name")}
    ]
    if len(exact) == 1:
        item = exact[0]
        return item["username"], item["name"], item["md5"]
    if len(exact) > 1:
        raise RuntimeError("chat query is ambiguous; use the exact username from an existing archive")

    partial = [
        item for item in chats
        if query_folded in str(item.get("name") or "").casefold()
    ]
    if len(partial) == 1:
        item = partial[0]
        return item["username"], item["name"], item["md5"]
    if len(partial) > 1:
        raise RuntimeError("chat query has multiple partial matches; use an exact name or username")

    if query.endswith("@chatroom"):
        return query, query, hashlib.md5(query.encode("utf-8")).hexdigest()
    if re.fullmatch(r"[0-9a-fA-F]{32}", query):
        return query.lower(), query, query.lower()
    raise RuntimeError("chat was not found in the current local database")


def normalized_type(local_type: int) -> str:
    code = local_type
    if code not in TYPE_MAP and isinstance(code, int) and code > 0xFFFF:
        code &= 0xFF
    return TYPE_MAP.get(code, "other")


def shard_sender_map(connection) -> dict[int, str]:
    try:
        rows = connection.execute("SELECT rowid, user_name FROM Name2Id").fetchall()
    except Exception:
        return {}
    return {int(row[0]): row[1] for row in rows if row[1]}


def contact_nicknames(db) -> dict[str, str]:
    for rel, path, _ in db._db_files:
        if Path(path).name != "contact.db":
            continue
        connection = db._open(rel)
        try:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(contact)").fetchall()
            }
            sql = "SELECT username, nick_name, remark FROM contact"
            if "local_type" in columns:
                sql += " WHERE local_type != 3"
            return {
                username: remark or nickname or username
                for username, nickname, remark in connection.execute(sql)
                if username
            }
        finally:
            connection.close()
    return {}


def sender_label(
    sender_id,
    shard_map: dict,
    nicknames: dict,
    self_info: dict,
    chat_username: str,
    chat_name: str,
) -> str:
    username = shard_map.get(sender_id, "") if isinstance(sender_id, int) else ""
    self_username = self_info.get("username") or ""
    if chat_username.endswith("@chatroom"):
        if not username or username == chat_username:
            return ""
        if username == self_username:
            return "me"
        return nicknames.get(username, username)
    if username == chat_username:
        return chat_name
    if username and username == self_username:
        return "me"
    if username:
        return nicknames.get(username, username)
    if sender_id in (2, "2"):
        return "me"
    return ""


def strip_group_sender_prefix(content: str, is_group: bool) -> str:
    if not is_group or ":\n" not in content:
        return content
    prefix, remainder = content.split(":\n", 1)
    if 0 < len(prefix) <= 128 and "<" not in prefix and ">" not in prefix:
        return remainder
    return content


def xml_root(content: str):
    text = content.strip()
    if not text.startswith("<"):
        return None
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def first_xml_text(root, paths: tuple[str, ...]) -> str:
    for path in paths:
        node = root.find(path)
        if node is not None and node.text and node.text.strip():
            return node.text.strip()
    return ""


def readable_content(content, message_type: str, is_group: bool) -> str:
    if content is None:
        return ""
    text = strip_group_sender_prefix(str(content), is_group).strip()
    if message_type in {"image", "sticker", "video", "voice"}:
        return ""
    if message_type == "text" or not text:
        return text

    root = xml_root(text)
    if root is None:
        return text
    if message_type == "link_or_file":
        title = first_xml_text(root, (".//appmsg/title", ".//title"))
        description = first_xml_text(root, (".//appmsg/des", ".//des"))
        url = first_xml_text(root, (".//appmsg/url", ".//url"))
        parts = [part for part in (title, description, url) if part]
        return "\n".join(dict.fromkeys(parts))
    if message_type == "location":
        location = root.find(".//location")
        if location is not None:
            place = location.get("poiname") or ""
            label = location.get("label") or ""
            return " · ".join(dict.fromkeys(part for part in (place, label) if part))
    if message_type == "system":
        return first_xml_text(
            root,
            (".//replacemsg", ".//content", ".//plain", ".//title"),
        )
    return text


def export_messages(
    db,
    db_module,
    chat_username: str,
    chat_name: str,
    chat_md5: str,
) -> list[dict]:
    table = "Msg_" + chat_md5
    nicknames = contact_nicknames(db)
    self_info = db.get_self_info()
    messages = []
    for rel in db._message_dbs():
        connection = db._open(rel)
        try:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            shard_map = shard_sender_map(connection)
            rows = connection.execute(
                f"SELECT {MESSAGE_COLUMNS} FROM [{table}]"
            ).fetchall()
            source_db = PurePath(rel.replace("\\", "/")).name
            for row in rows:
                exported = db._export_row(row, db_module.MSG_TYPE_NAMES)
                message = {
                    "source_db": source_db,
                    "local_id": exported["local_id"],
                    "timestamp": exported["create_time"],
                    "sender": sender_label(
                        exported["sender_id"],
                        shard_map,
                        nicknames,
                        self_info,
                        chat_username,
                        chat_name,
                    ),
                }
                message_type = normalized_type(exported["type_code"])
                if message_type != "text":
                    message["type"] = message_type
                content = readable_content(
                    exported.get("content"),
                    message_type,
                    chat_username.endswith("@chatroom"),
                )
                if content:
                    message["content"] = content
                if message_type == "image" and exported.get("md5"):
                    message["image_md5"] = exported["md5"]
                messages.append(message)
        finally:
            connection.close()

    messages.sort(
        key=lambda item: (item["timestamp"], item["source_db"], item["local_id"])
    )
    identities = [message_identity(message) for message in messages]
    duplicate_count = len(identities) - len(set(identities))
    if duplicate_count:
        raise RuntimeError(f"duplicate message identities: {duplicate_count}")
    if not messages:
        raise RuntimeError("the selected chat has no messages in the prepared database shards")
    return messages


def write_image_config(path: str, db) -> None:
    if not db.cfg_dword:
        raise RuntimeError("image key derivation is unavailable; keep WeChat open and retry")
    data = {
        "image_aes_key": hashlib.md5(
            (str(db.cfg_dword) + db.wxid).encode("utf-8")
        ).hexdigest()[:16],
        "image_xor_key": db.cfg_dword & 0xFF,
    }
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if sys.platform != "win32":
        raise RuntimeError("live WeChat database export is supported only on Windows")

    db_module = load_database_module(Path(args.wechatauto_repo).resolve())
    db = db_module.WeChatDB(
        db_dir=str(Path(args.db_root).resolve()),
        account=args.account,
        workdir=str(Path(args.workdir).resolve()),
    )
    if db.unkeyed:
        raise RuntimeError(f"database key verification failed for {len(db.unkeyed)} files")

    if args.archive_summary:
        summary = json.loads(Path(args.archive_summary).read_text(encoding="utf-8"))
        chat_username = summary["username"]
        chat_name = summary.get("chat") or chat_username
        chat_md5 = (
            chat_username.lower()
            if re.fullmatch(r"[0-9a-fA-F]{32}", chat_username)
            else hashlib.md5(chat_username.encode("utf-8")).hexdigest()
        )
    else:
        chat_username, chat_name, chat_md5 = resolve_chat(db, args.chat)

    messages = export_messages(db, db_module, chat_username, chat_name, chat_md5)
    if args.image_config:
        write_image_config(args.image_config, db)

    complete = {
        "chat": chat_name,
        "username": chat_username,
        "exported_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
    }
    if chat_username.endswith("@chatroom"):
        complete["is_group"] = True

    if args.full_output:
        full_path = Path(args.full_output).resolve()
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(json.dumps(complete, ensure_ascii=False, indent=2), encoding="utf-8")

    cutoff = parse_local_time(args.through, end_of_day=True) if args.through else None
    cutoff_ts = int(cutoff.timestamp()) if cutoff else None
    selected = [
        message for message in messages
        if cutoff_ts is None or message["timestamp"] <= cutoff_ts
    ]

    previous_messages = []
    incremental = []
    if args.previous_cutoff:
        previous_ts = int(parse_local_time(args.previous_cutoff).timestamp())
        if cutoff_ts is not None and cutoff_ts < previous_ts:
            raise ValueError("--through cannot be earlier than --previous-cutoff")
        previous_messages = [message for message in messages if message["timestamp"] <= previous_ts]
        incremental = [message for message in selected if message["timestamp"] > previous_ts]
        if args.expected_previous_count is not None and len(previous_messages) != args.expected_previous_count:
            raise RuntimeError(
                "previous range count mismatch: "
                f"expected {args.expected_previous_count}, got {len(previous_messages)}"
            )
    elif args.expected_previous_count is not None:
        raise ValueError("--expected-previous-count requires --previous-cutoff")

    latest_selected = format_timestamp(selected, -1)
    latest_observed = format_timestamp(messages, -1)
    output = dict(
        complete,
        messages=selected,
        archive_latest=latest_selected,
        session_latest_observed=latest_observed,
        requested_through=cutoff.date().isoformat() if cutoff else None,
        previous_cutoff=args.previous_cutoff,
        incremental_messages=len(incremental) if args.previous_cutoff else None,
        excluded_after_cutoff=len(messages) - len(selected),
    )
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    months = Counter(
        dt.datetime.fromtimestamp(message["timestamp"]).strftime("%Y-%m")
        for message in selected
    )
    print(
        json.dumps(
            {
                "database_count": len(db._db_files),
                "verified_keys": len(db._keys),
                "unkeyed": len(db.unkeyed),
                "full_count": len(messages),
                "selected_count": len(selected),
                "previous_count": len(previous_messages) if args.previous_cutoff else None,
                "incremental_count": len(incremental) if args.previous_cutoff else None,
                "first_incremental": format_timestamp(incremental, 0),
                "latest_selected": latest_selected,
                "latest_observed": latest_observed,
                "excluded_after_cutoff": len(messages) - len(selected),
                "duplicates": 0,
                "months": dict(sorted(months.items())),
                "image_messages": sum(1 for message in selected if message.get("type") == "image"),
                "image_md5_available": sum(1 for message in selected if message.get("image_md5")),
                "image_config_written": bool(args.image_config),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
