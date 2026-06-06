from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CONFIG_ENV_NAME = "WECHAT_PUBLISH_CONFIG"
ROOT_ENV_NAME = "WECHAT_PUBLISH_ROOT"
CONFIG_FILENAME = ".wechat-publish.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "publish_doc_root": "07.发布文案",
    "article_library_json": "08.数据反馈/公众号文章库/AI南柯-文章列表.json",
    "article_library_md": "08.数据反馈/公众号文章库/AI南柯-文章列表.md",
    "header_template": "07.发布文案/模板/公众号/AI南柯-header-card.md",
    "footer_template": "07.发布文案/模板/公众号/AI南柯-footer.md",
    "publish_index_filename": "发布索引.md",
    "related_articles_limit": 5,
    "wechat_session_file": "skills/wechat-draft-publisher/scripts/session.json",
    "opencli_daemon_url": "http://127.0.0.1:19825",
}


def looks_like_vault_root(path: Path) -> bool:
    return (path / CONFIG_FILENAME).exists() or (path / DEFAULT_CONFIG["publish_doc_root"]).exists()


def resolve_project_root(script_file: str | Path) -> Path:
    env_root = os.environ.get(ROOT_ENV_NAME, "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()

    script_path = Path(script_file).resolve()
    for parent in script_path.parents:
        if looks_like_vault_root(parent):
            return parent.resolve()

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if looks_like_vault_root(candidate):
            return candidate.resolve()

    if len(script_path.parents) >= 3 and script_path.parent.name == "wechat-cover-summary-tool":
        return script_path.parents[2].resolve()

    return cwd


def find_config_path(repo_root: Path) -> Path | None:
    env_value = os.environ.get(CONFIG_ENV_NAME, "").strip()
    candidates = []
    if env_value:
        candidates.append(Path(env_value))
    candidates.append(repo_root / CONFIG_FILENAME)

    for candidate in candidates:
        resolved = candidate.expanduser()
        if not resolved.is_absolute():
            resolved = repo_root / resolved
        if resolved.exists():
            return resolved.resolve()
    return None


def load_config(repo_root: Path) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    config_path = find_config_path(repo_root)
    if not config_path:
        return config

    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须是 JSON 对象: {config_path}")

    for key, value in data.items():
        if value is not None:
            config[key] = value
    return config


def resolve_config_path(repo_root: Path, config: dict[str, Any], key: str) -> Path:
    value = str(config.get(key) or DEFAULT_CONFIG[key])
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def resolve_optional_config_path(repo_root: Path, config: dict[str, Any], key: str) -> Path | None:
    value = str(config.get(key) or "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def resolve_config_int(config: dict[str, Any], key: str) -> int:
    value = config.get(key, DEFAULT_CONFIG[key])
    return int(value)
