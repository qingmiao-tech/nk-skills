import argparse
import collections
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".hevc", ".bmp"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Archive an exported WeChat 4.x chat JSON into monthly Obsidian Markdown files."
    )
    parser.add_argument("--chat-json", required=True, help="Path to export_chat.py JSON output.")
    parser.add_argument("--decrypted-dir", required=True, help="Root directory of decrypted WeChat databases.")
    parser.add_argument("--wechat-base", required=True, help="xwechat_files account directory, e.g. .../<wxid>_<suffix>.")
    parser.add_argument("--wechat-decrypt-tool", required=True, help="Directory containing decode_image.py.")
    parser.add_argument("--output", required=True, help="Output directory for Markdown archive.")
    parser.add_argument("--chat-name", help="Display name override. Defaults to chat JSON 'chat'.")
    parser.add_argument("--chat-username", help="Username override. Defaults to chat JSON 'username'.")
    parser.add_argument("--wechat-decrypt-config", help="wechat-decrypt config.json with image_aes_key/image_xor_key.")
    parser.add_argument("--image-aes-key", help="Temporary image AES key override. Do not persist in docs.")
    parser.add_argument("--image-xor-key", help="Temporary image XOR key override, decimal or 0x hex.")
    return parser.parse_args()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_image_keys(args):
    aes_key = args.image_aes_key
    xor_key = args.image_xor_key

    if args.wechat_decrypt_config:
        cfg_path = Path(args.wechat_decrypt_config)
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
                info[row["local_id"]] = {
                    "local_type": row["local_type"],
                    "create_time": row["create_time"],
                    "content": content or "",
                    "packed_info_data": row["packed_info_data"] or b"",
                }
        finally:
            con.close()

    if not info:
        raise RuntimeError(f"message table not found or empty: {table}")
    return info


def extract_image_md5(raw: dict) -> str:
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


def import_decode_image(tool_dir: Path):
    sys.path.insert(0, str(tool_dir))
    import decode_image  # noqa: PLC0415

    return decode_image


def decode_image_asset(decode_image, out_dir: Path, assets_dir: Path, attach_dir: Path,
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
        tmp_path = asset_month_dir / f"{image_md5}.unknown.tmp"
        try:
            result_path, fmt = decode_image.decrypt_dat_file(
                str(dat_path),
                out_path=str(tmp_path),
                aes_key=aes_key,
                xor_key=xor_key,
            )
            if not result_path or not fmt:
                if tmp_path.exists():
                    tmp_path.unlink()
                diagnostics["decrypt_empty_result"] += 1
                continue
            final_path = asset_month_dir / f"{image_md5}.{fmt}"
            os.replace(result_path, final_path)
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
        rel = image_map.get(message["local_id"])
        if rel:
            return f"{line_head}\n  ![]({rel})"
        image_md5 = extract_image_md5(raw_info.get(message["local_id"], {}))
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
    decoded_count = sum(1 for m in messages if m.get("type") == "image" and image_map.get(m["local_id"]))
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
    decrypted_dir = Path(args.decrypted_dir)
    wechat_base = Path(args.wechat_base)
    tool_dir = Path(args.wechat_decrypt_tool)
    out_dir = Path(args.output)
    assets_dir = out_dir / "assets"

    data = read_json(chat_json)
    chat_name = args.chat_name or data["chat"]
    chat_username = args.chat_username or data["username"]
    chat_hash = hashlib.md5(chat_username.encode("utf-8")).hexdigest()
    attach_dir = wechat_base / "msg" / "attach" / chat_hash
    aes_key, xor_key = load_image_keys(args)

    messages = sorted(data["messages"], key=lambda item: (item["timestamp"], item.get("local_id", 0)))
    raw_info = load_raw_message_info(decrypted_dir, chat_username)
    decode_image = import_decode_image(tool_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    image_map = {}
    image_diagnostics = collections.Counter()
    image_messages = [m for m in messages if m.get("type") == "image"]
    for index, message in enumerate(image_messages, start=1):
        raw = raw_info.get(message["local_id"], {})
        image_md5 = extract_image_md5(raw)
        rel = decode_image_asset(
            decode_image,
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
            image_map[message["local_id"]] = rel
        if index % 100 == 0:
            print(f"decoded images: {index}/{len(image_messages)} usable={len(image_map)}", flush=True)

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
        "image_diagnostics": dict(image_diagnostics),
        "output_dir": str(out_dir),
    }
    (out_dir / "归档说明.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
