#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


WECHATAUTO_URL = "https://github.com/fanyuantaier/wechatauto-replica.git"
WECHATAUTO_REF = "v1.2.0.3"
RUNTIME_PACKAGES = (
    "cryptography>=41,<49",
    "zstandard>=0.22,<1",
    "imageio-ffmpeg>=0.4.9,<1",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the pinned local tool for the Windows WeChat 4.x archive workflow."
    )
    parser.add_argument("--tools-dir", required=True, help="Directory that will contain tool checkouts.")
    parser.add_argument("--python", default=sys.executable, help="Python used to create the isolated venv.")
    parser.add_argument("--install-deps", action="store_true", help="Create a venv and install runtime packages.")
    parser.add_argument("--update", action="store_true", help="Fetch and checkout the requested refs in clean repos.")
    parser.add_argument("--wechatauto-ref", default=WECHATAUTO_REF)
    return parser.parse_args()


def run(command: list[str], cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "no command output").strip().splitlines()
        last_line = detail[-1] if detail else "no command output"
        raise RuntimeError(f"command failed: {command[0]} ({last_line})") from exc
    return completed.stdout.strip()


def ensure_checkout(destination: Path, url: str, ref: str, update: bool) -> str:
    if destination.exists():
        if not (destination / ".git").is_dir():
            raise RuntimeError(f"tool destination exists but is not a Git repository: {destination}")
        dirty = run(["git", "status", "--porcelain"], destination)
        if dirty:
            raise RuntimeError(f"refusing to change dirty tool checkout: {destination}")
        if update:
            run(["git", "fetch", "--tags", "--prune", "origin"], destination)
            run(["git", "checkout", "--detach", ref], destination)
        current = run(["git", "rev-parse", "HEAD"], destination)
        requested = run(["git", "rev-parse", f"{ref}^{{commit}}"], destination)
        if current != requested:
            raise RuntimeError(
                f"tool checkout does not match requested ref {ref}: {destination}; "
                "rerun with --update after confirming the checkout is clean"
            )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", url, str(destination)])
        run(["git", "checkout", "--detach", ref], destination)
    return run(["git", "rev-parse", "HEAD"], destination)


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> int:
    args = parse_args()
    if sys.platform != "win32":
        raise RuntimeError("the live WeChat database workflow is supported only on Windows")
    if shutil.which("git") is None:
        raise RuntimeError("git is required to prepare the external tools")

    tools_dir = Path(args.tools_dir).resolve()
    tools_dir.mkdir(parents=True, exist_ok=True)
    checkouts = {
        "wechatauto-replica": (
            WECHATAUTO_URL,
            args.wechatauto_ref,
        ),
    }
    revisions = {}
    for name, (url, ref) in checkouts.items():
        revisions[name] = ensure_checkout(tools_dir / name, url, ref, args.update)

    runtime = None
    if args.install_deps:
        venv_dir = tools_dir / ".venv"
        python = venv_python(venv_dir)
        if not python.exists():
            run([args.python, "-m", "venv", str(venv_dir)])
        run([str(python), "-m", "pip", "install", *RUNTIME_PACKAGES])
        runtime = str(python)

    print(
        json.dumps(
            {
                "tools_dir": str(tools_dir),
                "revisions": revisions,
                "runtime_python": runtime,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
