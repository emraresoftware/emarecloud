#!/usr/bin/env python3
"""PR degisikliklerini .ai-locks altindaki aktif lock dosyalariyla karsilastirir."""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _load_active_locks(lock_dir: str) -> dict[str, list[dict[str, str]]]:
    lock_map: dict[str, list[dict[str, str]]] = {}
    pattern = os.path.join(lock_dir, "*.json")
    for lock_path in glob.glob(pattern):
        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except Exception:
            continue

        durum = str(data.get("durum", "")).strip().lower()
        if durum != "active":
            continue

        ai = str(data.get("ai", "unknown"))
        gorev = str(data.get("gorev", "unknown"))
        lock_name = Path(lock_path).name
        for file_path in data.get("dosyalar", []) or []:
            normalized = _normalize(str(file_path))
            if not normalized:
                continue
            lock_map.setdefault(normalized, []).append(
                {
                    "lock_file": lock_name,
                    "ai": ai,
                    "gorev": gorev,
                }
            )
    return lock_map


def _changed_files(base_sha: str, head_sha: str) -> list[str]:
    out = _run(["git", "diff", "--name-only", f"{base_sha}...{head_sha}"])
    return [_normalize(line) for line in out.splitlines() if line.strip()]


def _write_summary(conflicts: dict[str, list[dict[str, str]]], changed: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    with open(summary_path, "a", encoding="utf-8") as f:
        if not conflicts:
            f.write("## AI Lock Guard\n")
            f.write("- Cakisma yok. PR degisiklikleri aktif lock dosyalariyla uyumlu.\n")
            return

        f.write("## AI Lock Guard\n")
        f.write("- Cakisma tespit edildi. Asagidaki dosyalar aktif lock altinda:\n\n")
        for file_path, owners in conflicts.items():
            f.write(f"- `{file_path}`\n")
            for owner in owners:
                f.write(
                    "  - "
                    f"gorev={owner['gorev']}, "
                    f"ai={owner['ai']}, "
                    f"lock={owner['lock_file']}\n"
                )
        f.write("\n")
        f.write("### PR degisen dosyalar\n")
        for file_path in changed:
            f.write(f"- `{file_path}`\n")


def _set_output(conflict: bool) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"conflict={'true' if conflict else 'false'}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI lock cakisma kontrolu")
    parser.add_argument("--lock-dir", default=".ai-locks", help="Lock dizini")
    parser.add_argument("--base-sha", default="", help="PR base SHA")
    parser.add_argument("--head-sha", default="", help="PR head SHA")
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Elle degisen dosya ekle (tekrarlanabilir)",
    )
    parser.add_argument(
        "--fail-on-conflict",
        action="store_true",
        help="Cakisma varsa non-zero don",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.base_sha and args.head_sha:
        try:
            changed = _changed_files(args.base_sha, args.head_sha)
        except Exception as exc:
            print(f"AI_LOCK_GUARD: git diff calismadi: {exc}")
            return 1
    else:
        changed = [_normalize(x) for x in args.changed_file if str(x).strip()]

    active_locks = _load_active_locks(args.lock_dir)
    conflicts: dict[str, list[dict[str, str]]] = {}
    for file_path in changed:
        if file_path in active_locks:
            conflicts[file_path] = active_locks[file_path]

    conflict = bool(conflicts)
    _set_output(conflict)
    _write_summary(conflicts, changed)

    if not conflict:
        print("AI_LOCK_GUARD: cakisma yok")
        return 0

    print("AI_LOCK_GUARD: aktif lock cakismasi var")
    for file_path, owners in conflicts.items():
        print(f"- {file_path}")
        for owner in owners:
            print(
                f"  gorev={owner['gorev']} ai={owner['ai']} lock={owner['lock_file']}"
            )

    if args.fail_on_conflict:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
