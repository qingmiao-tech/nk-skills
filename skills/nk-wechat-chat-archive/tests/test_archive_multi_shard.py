import hashlib
import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "archive_wechat_v4_chat.py"
SPEC = importlib.util.spec_from_file_location("archive_wechat_v4_chat", SCRIPT)
ARCHIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ARCHIVE)


class MultiShardMessageIdentityTest(unittest.TestCase):
    def test_same_local_id_in_two_shards_keeps_both_messages(self):
        chat_username = "test@chatroom"
        table = "Msg_" + hashlib.md5(chat_username.encode("utf-8")).hexdigest()

        with tempfile.TemporaryDirectory() as temp_dir:
            message_dir = Path(temp_dir) / "message"
            message_dir.mkdir()

            for shard, create_time, content in (
                ("message_0.db", 100, "older"),
                ("message_1.db", 200, "newer"),
            ):
                db_path = message_dir / shard
                with closing(sqlite3.connect(db_path)) as connection:
                    connection.execute(
                        f"""
                        CREATE TABLE [{table}] (
                            local_id INTEGER,
                            local_type INTEGER,
                            create_time INTEGER,
                            message_content TEXT,
                            WCDB_CT_message_content INTEGER,
                            packed_info_data BLOB
                        )
                        """
                    )
                    connection.execute(
                        f"INSERT INTO [{table}] VALUES (?, ?, ?, ?, ?, ?)",
                        (7, 3, create_time, content, 0, b""),
                    )
                    connection.commit()

            raw_info = ARCHIVE.load_raw_message_info(Path(temp_dir), chat_username)

        self.assertEqual("older", raw_info[("db", "message_0.db", 7)]["content"])
        self.assertEqual("newer", raw_info[("db", "message_1.db", 7)]["content"])
        self.assertEqual("older", raw_info[("legacy", 7, 100)]["content"])
        self.assertEqual("newer", raw_info[("legacy", 7, 200)]["content"])

    def test_render_uses_timestamp_and_local_id_for_image_lookup(self):
        older = {"local_id": 7, "timestamp": 100, "sender": "teacher", "type": "image"}
        newer = {"local_id": 7, "timestamp": 200, "sender": "teacher", "type": "image"}
        image_map = {
            ("legacy", 7, 100): "assets/1970-01/older.jpg",
            ("legacy", 7, 200): "assets/1970-01/newer.jpg",
        }

        older_rendered = ARCHIVE.render_message(older, {}, image_map)
        newer_rendered = ARCHIVE.render_message(newer, {}, image_map)

        self.assertIn("older.jpg", older_rendered)
        self.assertIn("newer.jpg", newer_rendered)

    def test_render_prefers_explicit_source_db_identity(self):
        message = {
            "source_db": "message_1.db",
            "local_id": 7,
            "timestamp": 200,
            "sender": "teacher",
            "type": "image",
        }
        image_map = {
            ("db", "message_1.db", 7): "assets/1970-01/source-aware.jpg",
        }

        rendered = ARCHIVE.render_message(message, {}, image_map)

        self.assertIn("source-aware.jpg", rendered)


if __name__ == "__main__":
    unittest.main()
