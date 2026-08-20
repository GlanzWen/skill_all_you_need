#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键生成 AI Code Review Router 的 Review Pack。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> str:
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.stdout.strip()


def print_finish(output_dir: Path) -> None:
    payload_path = output_dir / "review-pack.json"
    if not payload_path.exists():
        print(f"已生成 Review Pack：{output_dir}")
        return
    payload: dict[str, Any] = json.loads(payload_path.read_text(encoding="utf-8"))
    units = payload.get("units", [])
    counts = {severity: sum(1 for unit in units if unit.get("severity") == severity) for severity in ["P0", "P1", "P2", "P3"]}
    print("")
    print("Review Pack 生成完成")
    print(f"- 摘要：{output_dir / '00-summary.md'}")
    print(f"- 分诊：{output_dir / '01-human-routing.md'}")
    print(f"- 卡片：{output_dir / 'cards'}")
    print(f"- 结构化数据：{output_dir / 'review-pack.json'}")
    print(f"- 风险卡片：P0={counts['P0']} P1={counts['P1']} P2={counts['P2']} P3={counts['P3']}")
    print("- 边界：这是静态初审和人工分诊包，不是人工 Review 通过结论。")


def main() -> int:
    parser = argparse.ArgumentParser(description="一键生成本地 Review Pack。")
    parser.add_argument("--repo", default=".", help="被审查仓库路径，默认当前目录。")
    parser.add_argument("--base", help="审查基线，例如 main、origin/main 或提交 SHA。未提供时尝试自动推断。")
    parser.add_argument("--head", default="HEAD", help="审查目标，默认 HEAD。")
    parser.add_argument("--output-dir", default="review-pack", help="Review Pack 输出目录。")
    parser.add_argument("--committed-only", action="store_true", help="只审查 base..head 已提交差异，不纳入当前工作区和未跟踪文件。")
    parser.add_argument("--max-diff-chars", type=int, default=300_000, help="diff 最大字符数。")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    input_dir = output_dir / "input"
    diff_context = input_dir / "diff-context.json"
    review_units = input_dir / "review-units.json"

    collect_cmd = [
        "python3",
        str(ROOT / "scripts/collect_git_diff.py"),
        "--repo",
        args.repo,
        "--head",
        args.head,
        "--output",
        str(diff_context),
        "--include-diff",
        "--max-diff-chars",
        str(args.max_diff_chars),
    ]
    if args.base:
        collect_cmd.extend(["--base", args.base])
    if not args.committed_only:
        collect_cmd.extend(["--include-working-tree", "--include-untracked"])

    run(collect_cmd)
    run(
        [
            "python3",
            str(ROOT / "scripts/classify_review_units.py"),
            "--input",
            str(diff_context),
            "--output",
            str(review_units),
        ]
    )
    run(
        [
            "python3",
            str(ROOT / "scripts/render_review_pack.py"),
            "--input",
            str(review_units),
            "--output-dir",
            str(output_dir),
        ]
    )
    print_finish(output_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, file=sys.stdout)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        raise SystemExit(exc.returncode)
