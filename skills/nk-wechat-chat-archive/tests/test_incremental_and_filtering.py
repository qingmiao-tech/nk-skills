import argparse
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = SKILL_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


merge = load_script("merge_incremental_month.py")
filtering = load_script("filter_wechat_archive.py")
exporter = load_script("export_wechat_chat.py")


class IncrementalMergeTest(unittest.TestCase):
    def test_existing_body_is_preserved_and_new_message_is_appended(self):
        existing = (
            "# Chat - 2026-08\n\n"
            "- 消息数：1\n\n"
            "## 聊天记录\n\n"
            "- **2026-08-01 09:00:00** `A` old\n"
        )
        generated = (
            "# Chat - 2026-08\n\n"
            "- 消息数：2\n\n"
            "## 聊天记录\n\n"
            "- **2026-08-01 09:00:00** `A` regenerated\n\n"
            "- **2026-08-02 10:00:00** `B` new\n"
        )

        result, existing_count, appended_count = merge.merge_documents(
            existing,
            generated,
            "2026-08-01 09:00:00",
        )

        self.assertEqual(existing_count, 1)
        self.assertEqual(appended_count, 1)
        self.assertIn("`A` old", result)
        self.assertNotIn("`A` regenerated", result)
        self.assertIn("`B` new", result)


class CustomKeywordTest(unittest.TestCase):
    def test_custom_keyword_can_select_domain_specific_message(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keywords.json"
            path.write_text(
                json.dumps({"案例实操": ["专属业务词"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            message = filtering.Message(
                timestamp=datetime(2026, 8, 1, 9, 0, 0),
                sender="A",
                tail="这是专属业务词",
                continuation=[],
                source_file=Path("2026-08.md"),
                source_line=1,
                month="2026-08",
                kind="text",
            )
            args = argparse.Namespace(
                profile="general",
                keywords_file=str(path),
                min_score=2,
                image_context_window=0,
                image_context_minutes=0,
                context_window=0,
            )

            filtering.select_messages([message], args)

            self.assertTrue(message.selected)
            self.assertIn("案例实操", message.categories)

    def test_custom_keyword_rejects_unknown_category(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keywords.json"
            path.write_text('{"未知分类": ["词"]}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported keyword category"):
                filtering.load_custom_keywords(str(path))


class TextOnlyArchiveTest(unittest.TestCase):
    def test_skip_images_needs_no_database_or_external_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "chat.json"
            output = root / "archive"
            source.write_text(
                json.dumps(
                    {
                        "chat": "Test Chat",
                        "username": "test@chatroom",
                        "messages": [
                            {
                                "source_db": "message_0.db",
                                "local_id": 1,
                                "timestamp": 1785546000,
                                "sender": "A",
                                "content": "hello",
                            },
                            {
                                "source_db": "message_0.db",
                                "local_id": 2,
                                "timestamp": 1785546060,
                                "sender": "B",
                                "type": "image",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "archive_wechat_v4_chat.py"),
                    "--chat-json",
                    str(source),
                    "--skip-images",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads((output / "归档说明.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["messages"], 2)
            self.assertEqual(summary["image_messages"], 1)
            self.assertEqual(summary["decoded_images"], 0)
            self.assertEqual(summary["images_skipped"], 1)
            self.assertIn("图片未能解密", next(output.glob("????-??.md")).read_text(encoding="utf-8"))

            validated = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "validate_wechat_archive.py"),
                    "--archive",
                    str(output),
                    "--expected-messages",
                    "2",
                    "--expected-images",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)

            baseline = root / "baseline"
            baseline.mkdir()
            (baseline / "2025-12.md").write_text(
                "# Historical\n\n## 聊天记录\n\n- **2025-12-01 09:00:00** `A` old\n",
                encoding="utf-8",
            )
            missing_history = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "validate_wechat_archive.py"),
                    "--archive",
                    str(output),
                    "--history-baseline",
                    str(baseline),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(missing_history.returncode, 1)


class DirectExporterTest(unittest.TestCase):
    def test_export_keeps_same_local_id_from_different_shards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chat_username = "test@chatroom"
            table = "Msg_" + __import__("hashlib").md5(chat_username.encode()).hexdigest()
            paths = []
            for index in range(2):
                path = root / f"message_{index}.db"
                connection = sqlite3.connect(path)
                connection.execute("CREATE TABLE Name2Id(user_name TEXT PRIMARY KEY, is_session INTEGER)")
                connection.execute("INSERT INTO Name2Id(rowid, user_name, is_session) VALUES(3, ?, 0)", (f"user{index}",))
                connection.execute(
                    f"CREATE TABLE [{table}]("
                    "local_id INTEGER, local_type INTEGER, server_id INTEGER, "
                    "real_sender_id INTEGER, create_time INTEGER, message_content TEXT, "
                    "packed_info_data BLOB, sort_seq INTEGER)"
                )
                connection.execute(
                    f"INSERT INTO [{table}] VALUES(1, 1, 10, 3, ?, ?, NULL, ?)",
                    (1785546000 + index, f"text-{index}", index),
                )
                connection.commit()
                connection.close()
                paths.append(path)

            class FakeDB:
                _db_files = []

                def get_self_info(self):
                    return {"username": "self", "nick_name": "Me"}

                def _message_dbs(self):
                    return [f"message/{path.name}" for path in paths]

                def _open(self, rel):
                    connection = sqlite3.connect(root / Path(rel).name)
                    connection.row_factory = sqlite3.Row
                    return connection

                def _export_row(self, row, _type_names):
                    return {
                        "local_id": row["local_id"],
                        "type_code": row["local_type"],
                        "sender_id": row["real_sender_id"],
                        "create_time": row["create_time"],
                        "content": row["message_content"],
                        "md5": None,
                    }

            messages = exporter.export_messages(
                FakeDB(),
                SimpleNamespace(MSG_TYPE_NAMES={1: "文本"}),
                chat_username,
                "Test Chat",
                table.removeprefix("Msg_"),
            )

            self.assertEqual(len(messages), 2)
            self.assertEqual({message["source_db"] for message in messages}, {"message_0.db", "message_1.db"})
            self.assertEqual({message["local_id"] for message in messages}, {1})
            self.assertEqual({message["sender"] for message in messages}, {"user0", "user1"})


if __name__ == "__main__":
    unittest.main()
