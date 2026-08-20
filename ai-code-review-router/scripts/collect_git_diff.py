#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收集 Git 差异上下文，输出给 Review Pack 后续步骤使用。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run_git(repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def git_text(repo: Path, args: list[str], check: bool = True) -> str:
    result = run_git(repo, args, check=check)
    return result.stdout.strip()


def resolve_default_base(repo: Path) -> str:
    candidates = [
        ["merge-base", "HEAD", "origin/main"],
        ["merge-base", "HEAD", "origin/master"],
        ["rev-parse", "HEAD~1"],
    ]
    for candidate in candidates:
        result = run_git(repo, candidate, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    raise SystemExit("无法自动确定 base，请显式传入 --base。")


def parse_name_status(text: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            files.append({"status": status, "old_path": parts[1], "path": parts[2]})
        else:
            files.append({"status": status, "path": parts[1] if len(parts) > 1 else ""})
    return files


def parse_numstat(text: str) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_raw, deleted_raw, path = parts[0], parts[1], parts[2]
        added = None if added_raw == "-" else int(added_raw)
        deleted = None if deleted_raw == "-" else int(deleted_raw)
        stats[path] = {"additions": added, "deletions": deleted}
    return stats


def tracked_paths(files: list[dict[str, Any]]) -> set[str]:
    return {item.get("path", "") for item in files if item.get("path")}


def count_text_lines(path: Path) -> int | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return len(data.decode("utf-8", errors="replace").splitlines())
    except OSError:
        return None


def read_text_preview(path: Path, max_chars: int) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    text = data.decode("utf-8", errors="replace")
    return text[:max_chars]


def synthetic_untracked_diff(path: str, text: str) -> str:
    lines = [
        f"diff --git a/{path} b/{path}",
        "new file mode 100644",
        "--- /dev/null",
        f"+++ b/{path}",
    ]
    lines.extend(f"+{line}" for line in text.splitlines())
    return "\n".join(lines)


def collect_untracked(repo: Path, dirty_status: list[str], existing_paths: set[str], max_chars_per_file: int) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    diff_parts: list[str] = []
    for line in dirty_status:
        if not line.startswith("?? "):
            continue
        rel_path = line[3:]
        if rel_path in existing_paths:
            continue
        abs_path = repo / rel_path
        if abs_path.is_dir():
            for child in sorted(path for path in abs_path.rglob("*") if path.is_file()):
                child_rel = child.relative_to(repo).as_posix()
                if child_rel in existing_paths:
                    continue
                additions = count_text_lines(child)
                items.append({"status": "??", "path": child_rel, "additions": additions, "deletions": 0})
                preview = read_text_preview(child, max_chars_per_file)
                if preview is not None:
                    diff_parts.append(synthetic_untracked_diff(child_rel, preview))
        else:
            additions = count_text_lines(abs_path)
            items.append({"status": "??", "path": rel_path, "additions": additions, "deletions": 0})
            preview = read_text_preview(abs_path, max_chars_per_file)
            if preview is not None:
                diff_parts.append(synthetic_untracked_diff(rel_path, preview))
    return items, diff_parts


def collect(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    if not repo.exists():
        raise SystemExit(f"仓库路径不存在：{repo}")
    if run_git(repo, ["rev-parse", "--is-inside-work-tree"], check=False).returncode != 0:
        raise SystemExit(f"不是 Git 仓库：{repo}")

    base = args.base or resolve_default_base(repo)
    head = args.head
    base_sha = git_text(repo, ["rev-parse", base])
    head_sha = git_text(repo, ["rev-parse", head])
    commit_range = f"{base_sha}..{head_sha}"
    range_expr = commit_range
    diff_target = commit_range
    if args.include_working_tree:
        diff_target = base_sha
        range_expr = f"{base_sha}..WORKTREE"

    name_status = git_text(repo, ["diff", "--name-status", diff_target])
    numstat = parse_numstat(git_text(repo, ["diff", "--numstat", diff_target]))
    files = parse_name_status(name_status)
    for item in files:
        item.update(numstat.get(item["path"], {"additions": 0, "deletions": 0}))

    commits = git_text(repo, ["log", "--oneline", "--decorate=short", commit_range], check=False)
    dirty_status = git_text(repo, ["status", "--short"], check=False)
    dirty_lines = dirty_status.splitlines()
    untracked_diff_parts: list[str] = []
    if args.include_untracked:
        untracked_files, untracked_diff_parts = collect_untracked(repo, dirty_lines, tracked_paths(files), args.max_untracked_chars_per_file)
        files.extend(untracked_files)
    diff_text = ""
    diff_truncated = False
    if args.include_diff:
        diff_text = git_text(repo, ["diff", "--find-renames", "--find-copies", diff_target], check=False)
        if untracked_diff_parts:
            diff_text = "\n".join(part for part in [diff_text, *untracked_diff_parts] if part)
        if len(diff_text) > args.max_diff_chars:
            diff_text = diff_text[: args.max_diff_chars]
            diff_truncated = True

    total_additions = sum(item.get("additions") or 0 for item in files)
    total_deletions = sum(item.get("deletions") or 0 for item in files)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "base": base,
        "head": head,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "range": range_expr,
        "dirty_status": dirty_lines,
        "commits": commits.splitlines(),
        "files": files,
        "totals": {
            "files": len(files),
            "additions": total_additions,
            "deletions": total_deletions,
            "commits": len([line for line in commits.splitlines() if line.strip()]),
        },
        "diff": diff_text,
        "diff_truncated": diff_truncated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="收集 Git diff 上下文。")
    parser.add_argument("--repo", default=".", help="被审查仓库路径，默认当前目录。")
    parser.add_argument("--base", help="审查基线，例如 main、origin/main 或提交 SHA。")
    parser.add_argument("--head", default="HEAD", help="审查目标，默认 HEAD。")
    parser.add_argument("--output", required=True, help="输出 JSON 路径。")
    parser.add_argument("--include-diff", action="store_true", help="包含截断后的完整 diff 文本。")
    parser.add_argument("--include-working-tree", action="store_true", help="把当前工作区相对 base 的改动纳入审查。")
    parser.add_argument("--include-untracked", action="store_true", help="把未跟踪文件纳入文件清单；建议与 --include-working-tree 一起使用。")
    parser.add_argument("--max-diff-chars", type=int, default=300_000, help="diff 最大字符数。")
    parser.add_argument("--max-untracked-chars-per-file", type=int, default=20_000, help="每个未跟踪文本文件纳入 diff 预览的最大字符数。")
    args = parser.parse_args()

    payload = collect(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入：{output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        raise SystemExit(exc.returncode)
