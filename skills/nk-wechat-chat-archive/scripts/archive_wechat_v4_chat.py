import argparse
import collections
import datetime as dt
import glob
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".hevc", ".bmp"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Archive an exported WeChat 4.x chat JSON into monthly Obsidian Markdown files."
    )
    parser.add_argument("--chat-json", required=True, help="Path to export_chat.py JSON output.")
    parser.add_argument(
        "--decrypted-dir",
        help="Optional legacy decrypted DB root used when old chat JSON lacks image_md5.",
    )
    parser.add_argument(
        "--wechat-base",
        help="xwechat_files account directory. Required when decoding images.",
    )
    parser.add_argument(
        "--wechatauto-repo",
        help="Checkout containing wechatauto/media.py. Required when decoding images.",
    )
    parser.add_argument("--output", required=True, help="Output directory for Markdown archive.")
    parser.add_argument("--chat-name", help="Display name override. Defaults to chat JSON 'chat'.")
    parser.add_argument("--chat-username", help="Username override. Defaults to chat JSON 'username'.")
    parser.add_argument("--image-config", help="Private JSON with image_aes_key/image_xor_key.")
    parser.add_argument("--image-aes-key", help="Temporary image AES key override. Do not persist in docs.")
    parser.add_argument("--image-xor-key", help="Temporary image XOR key override, decimal or 0x hex.")
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Create Markdown with image placeholders without reading local databases or attachments.",
    )
    return parser.parse_args()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_image_keys(args):
    aes_key = args.image_aes_key
    xor_key = args.image_xor_key

    if args.image_config:
        cfg_path = Path(args.image_config)
        if cfg_path.exists():
            cfg = read_json(cfg_path)
            aes_key = aes_key or cfg.get("image_aes_key")
            xor_key = xor_key if xor_key is not None else cfg.get("image_xor_key")

    if xor_key is None or xor_key == "":
        xor_key_int = 0x88
    elif isinstance(xor_key, int):
        xor_key_int = xor_key
    else:
        xor_key_int = int(str(xor_key), 0)

    return aes_key, xor_key_int


def markdown_escape(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("\r\n", "\n").replace("\r", "\n").strip()


def month_of(timestamp: int) -> str:
    return dt.datetime.fromtimestamp(timestamp).strftime("%Y-%m")


def time_of(timestamp: int) -> str:
    return dt.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def message_key(message: dict) -> tuple:
    source_db = message.get("source_db")
    if source_db:
        return "db", Path(source_db).name, message["local_id"]
    return "legacy", message["local_id"], message["timestamp"]


def load_raw_message_info(decrypted_dir: Path, chat_username: str):
    table = "Msg_" + hashlib.md5(chat_username.encode("utf-8")).hexdigest()
    dbs = sorted((decrypted_dir / "message").glob("message_*.db"))
    if not dbs:
        raise FileNotFoundError(f"message databases not found under: {decrypted_dir / 'message'}")

    try:
        import zstandard as zstd  # noqa: PLC0415
    except ModuleNotFoundError:
        zstd = None
    dctx = zstd.ZstdDecompressor() if zstd else None
    info = {}

    for db in dbs:
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            cur.close()
            con.close()
            continue
        query = f"""
        SELECT local_id, local_type, create_time, message_content,
               WCDB_CT_message_content, packed_info_data
        FROM [{table}]
        ORDER BY create_time ASC
        """
        try:
            for row in cur.execute(query):
                content = row["message_content"]
                if isinstance(content, bytes) and row["WCDB_CT_message_content"] == 4 and dctx:
                    try:
                        content = dctx.decompress(content).decode("utf-8", errors="replace")
                    except Exception:
                        content = ""
                elif isinstance(content, bytes) and row["WCDB_CT_message_content"] == 4:
                    content = ""
                elif isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
                raw = {
                    "local_type": row["local_type"],
                    "create_time": row["create_time"],
                    "content": content or "",
                    "packed_info_data": row["packed_info_data"] or b"",
                }
                db_key = ("db", db.name, row["local_id"])
                if db_key in info:
                    raise RuntimeError(f"duplicate message key in {db.name}: {row['local_id']}")
                info[db_key] = raw

                legacy_key = ("legacy", row["local_id"], row["create_time"])
                if legacy_key in info:
                    info[legacy_key] = None
                else:
                    info[legacy_key] = raw
        finally:
            cur.close()
            con.close()

    if not info:
        raise RuntimeError(f"message table not found or empty: {table}")
    return info


def extract_image_md5(raw: dict) -> str:
    explicit = raw.get("image_md5") or raw.get("md5")
    if explicit and re.fullmatch(r"[0-9a-fA-F]{32}", str(explicit)):
        return str(explicit).lower()

    packed = raw.get("packed_info_data") or b""
    if packed:
        text = packed.decode("utf-8", errors="ignore")
        matches = re.findall(r"[0-9a-f]{32}", text)
        if matches:
            return matches[-1]

    content = raw.get("content") or ""
    try:
        xml_text = content.split(":\n", 1)[1] if ":\n" in content else content
        root = ET.fromstring(xml_text)
        img = root.find(".//img")
        if img is not None:
            for attr in ("md5", "originsourcemd5"):
                value = img.get(attr)
                if value and re.fullmatch(r"[0-9a-f]{32}", value):
                    return value
    except Exception:
        pass
    return ""


def dat_candidates(attach_dir: Path, image_md5: str, message_month: str):
    if not image_md5:
        return []

    patterns = [
        attach_dir / message_month / "Img" / f"{image_md5}*.dat",
        attach_dir / "*" / "Img" / f"{image_md5}*.dat",
    ]
    paths = []
    for pattern in patterns:
        paths.extend(Path(p) for p in glob.glob(str(pattern)))

    def priority(path: Path):
        name = path.stem
        if name.endswith("_h"):
            return 0
        if name.endswith("_W"):
            return 1
        if name.endswith("_t"):
            return 2
        return 3

    unique = []
    seen = set()
    for path in sorted(paths, key=priority):
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def load_media_downloader(repo: Path):
    module_path = repo / "wechatauto" / "media.py"
    spec = importlib.util.spec_from_file_location("wechat_archive_media", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load media module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MediaDownloader(None)


def image_extension(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:4] in {b"GIF8"}:
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == b"BM":
        return "bmp"
    return ""


def decode_image_asset(media, out_dir: Path, assets_dir: Path, attach_dir: Path,
                       image_md5: str, message_month: str, aes_key: str, xor_key: int,
                       diagnostics: collections.Counter) -> str:
    if not image_md5:
        diagnostics["missing_md5"] += 1
        return ""

    asset_month_dir = assets_dir / message_month
    existing = sorted(asset_month_dir.glob(f"{image_md5}.*")) if asset_month_dir.exists() else []
    existing = [p for p in existing if p.suffix.lower() in IMAGE_SUFFIXES]
    if existing:
        return existing[0].relative_to(out_dir).as_posix()

    candidates = dat_candidates(attach_dir, image_md5, message_month)
    if not candidates:
        diagnostics["missing_dat"] += 1
        return ""

    for dat_path in candidates:
        asset_month_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = asset_month_dir / f"{image_md5}.tmp"
        try:
            data = media.decrypt_image(str(dat_path), aes_key=aes_key, xor_key=xor_key)
            if data[:4] == b"wxgf":
                data = media._wxgf_to_jpg(data)
                if not data:
                    diagnostics["wxgf_conversion_unavailable"] += 1
                    continue
            extension = image_extension(data)
            if not extension:
                diagnostics["unknown_image_format"] += 1
                continue
            tmp_path.write_bytes(data)
            final_path = asset_month_dir / f"{image_md5}.{extension}"
            os.replace(tmp_path, final_path)
            return final_path.relative_to(out_dir).as_posix()
        except ModuleNotFoundError as exc:
            diagnostics[f"missing_module:{exc.name}"] += 1
            if tmp_path.exists():
                tmp_path.unlink()
            return ""
        except Exception as exc:
            diagnostics[type(exc).__name__] += 1
            if tmp_path.exists():
                tmp_path.unlink()
            continue
    diagnostics["all_candidates_failed"] += 1
    return ""


def render_message(message: dict, raw_info: dict, image_map: dict) -> str:
    ts = time_of(message["timestamp"])
    sender = message.get("sender") or "系统"
    msg_type = message.get("type", "text")
    content = markdown_escape(message.get("content") or "")
    line_head = f"- **{ts}** `{sender}`"

    if msg_type == "image":
        key = message_key(message)
        rel = image_map.get(key)
        if rel:
            return f"{line_head}\n  ![]({rel})"
        image_md5 = extract_image_md5(raw_info.get(key) or {})
        suffix = f" {image_md5}" if image_md5 else ""
        return f"{line_head} [图片未能解密{suffix}]"

    if msg_type == "text":
        if "\n" in content:
            return f"{line_head}\n  {content.replace(chr(10), chr(10) + '  ')}"
        return f"{line_head} {content}"

    label = {
        "link_or_file": "链接/文件",
        "sticker": "表情",
        "system": "系统",
        "video": "视频",
        "voice": "语音",
        "contact_card": "名片",
        "location": "位置",
        "recall": "撤回",
        "transfer": "转账",
    }.get(msg_type, msg_type)
    if content:
        if "\n" in content:
            return f"{line_head} [{label}]\n  {content.replace(chr(10), chr(10) + '  ')}"
        return f"{line_head} [{label}] {content}"
    return f"{line_head} [{label}]"


def write_month_file(out_dir: Path, chat_name: str, chat_username: str, month: str,
                     messages: list, raw_info: dict, image_map: dict):
    type_counter = collections.Counter(m.get("type", "text") for m in messages)
    first_time = time_of(messages[0]["timestamp"])
    last_time = time_of(messages[-1]["timestamp"])
    image_count = type_counter.get("image", 0)
    decoded_count = sum(
        1
        for m in messages
        if m.get("type") == "image" and image_map.get(message_key(m))
    )
    lines = [
        f"# {chat_name} - {month}",
        "",
        f"- 群/联系人 ID：`{chat_username}`",
        f"- 消息数：{len(messages)}",
        f"- 时间范围：{first_time} ~ {last_time}",
        f"- 图片：{decoded_count}/{image_count} 已解密并本地化",
        f"- 类型统计：{dict(type_counter)}",
        "",
        "## 聊天记录",
        "",
    ]
    for message in messages:
        lines.append(render_message(message, raw_info, image_map))
        lines.append("")
    (out_dir / f"{month}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main():
    args = parse_args()
    chat_json = Path(args.chat_json)
    out_dir = Path(args.output)
    assets_dir = out_dir / "assets"

    data = read_json(chat_json)
    chat_name = args.chat_name or data["chat"]
    chat_username = args.chat_username or data["username"]

    messages = sorted(
        data["messages"],
        key=lambda item: (
            item["timestamp"],
            Path(item.get("source_db", "")).name,
            item.get("local_id", 0),
        ),
    )
    identities = [message_key(message) for message in messages]
    if len(identities) != len(set(identities)):
        raise ValueError("chat JSON contains duplicate message identities")

    image_messages = [message for message in messages if message.get("type") == "image"]
    decode_images = bool(image_messages) and not args.skip_images
    raw_info = {}
    media = None
    attach_dir = None
    aes_key = None
    xor_key = None
    if decode_images:
        required = {
            "--wechat-base": args.wechat_base,
            "--wechatauto-repo": args.wechatauto_repo,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "image decoding requires: " + ", ".join(missing) + "; or pass --skip-images"
            )
        wechat_base = Path(args.wechat_base)
        wechatauto_repo = Path(args.wechatauto_repo)
        chat_hash = hashlib.md5(chat_username.encode("utf-8")).hexdigest()
        attach_dir = wechat_base / "msg" / "attach" / chat_hash
        aes_key, xor_key = load_image_keys(args)
        if args.decrypted_dir:
            raw_info = load_raw_message_info(Path(args.decrypted_dir), chat_username)
        for message in image_messages:
            image_md5 = message.get("image_md5") or message.get("md5")
            if image_md5:
                raw_info.setdefault(message_key(message), {})["image_md5"] = image_md5
        media = load_media_downloader(wechatauto_repo)

    out_dir.mkdir(parents=True, exist_ok=True)
    if decode_images:
        assets_dir.mkdir(parents=True, exist_ok=True)

    image_map = {}
    image_diagnostics = collections.Counter()
    if decode_images:
        for index, message in enumerate(image_messages, start=1):
            key = message_key(message)
            raw = raw_info.get(key) or {}
            image_md5 = extract_image_md5(raw)
            rel = decode_image_asset(
                media,
                out_dir,
                assets_dir,
                attach_dir,
                image_md5,
                month_of(message["timestamp"]),
                aes_key,
                xor_key,
                image_diagnostics,
            )
            if rel:
                image_map[key] = rel
            if index % 100 == 0:
                print(
                    f"decoded images: {index}/{len(image_messages)} usable={len(image_map)}",
                    flush=True,
                )

    by_month = collections.defaultdict(list)
    for message in messages:
        by_month[month_of(message["timestamp"])].append(message)
    for month in sorted(by_month):
        write_month_file(out_dir, chat_name, chat_username, month, by_month[month], raw_info, image_map)

    summary = {
        "chat": chat_name,
        "username": chat_username,
        "messages": len(messages),
        "months": {month: len(items) for month, items in sorted(by_month.items())},
        "image_messages": len(image_messages),
        "decoded_images": len(image_map),
        "images_skipped": len(image_messages) if args.skip_images else 0,
        "image_diagnostics": dict(image_diagnostics),
        "output_dir": str(out_dir),
    }
    for key in (
        "archive_latest",
        "session_latest_observed",
        "requested_through",
        "previous_cutoff",
        "incremental_messages",
        "excluded_after_cutoff",
    ):
        if data.get(key) is not None:
            summary[key] = data[key]
    (out_dir / "归档说明.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
