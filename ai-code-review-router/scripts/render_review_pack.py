#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Review Unit 渲染成人工可读的 Review Pack。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|")


def file_line(item: dict[str, Any]) -> str:
    additions = item.get("additions")
    deletions = item.get("deletions")
    stats = "binary" if additions is None or deletions is None else f"+{additions}/-{deletions}"
    status = item.get("status", "?")
    path = item.get("path", "")
    if item.get("old_path"):
        path = f"{item['old_path']} -> {path}"
    return f"- `{path}`（{status}，{stats}）"


def severity_counts(units: list[dict[str, Any]]) -> dict[str, int]:
    return {severity: sum(1 for unit in units if unit["severity"] == severity) for severity in SEVERITY_ORDER}


def merge_gate(severity: str) -> str:
    if severity == "P0":
        return "是，阻断合并"
    if severity == "P1":
        return "合并前必须确认"
    if severity == "P2":
        return "建议确认"
    return "否，抽查即可"


def render_summary(payload: dict[str, Any]) -> str:
    source = payload["source"]
    units = payload["units"]
    counts = severity_counts(units)
    totals = source.get("totals", {})
    lines = [
        "# Code Review 初审摘要",
        "",
        "## 审查范围",
        "",
        f"- 仓库：`{source.get('repo')}`",
        f"- 范围：`{source.get('range')}`",
        f"- Base：`{source.get('base')}` / `{source.get('base_sha')}`",
        f"- Head：`{source.get('head')}` / `{source.get('head_sha')}`",
        f"- 生成时间：`{payload.get('generated_at')}`",
        "",
        "## 差异规模",
        "",
        f"- 文件数：{totals.get('files', 0)}",
        f"- 新增/删除：+{totals.get('additions', 0)} / -{totals.get('deletions', 0)}",
        f"- 提交数：{totals.get('commits', 0)}",
        f"- diff 是否截断：{'是' if source.get('diff_truncated') else '否'}",
        "",
        "## 风险总览",
        "",
        "| 严重度 | 卡片数 |",
        "| --- | ---: |",
    ]
    for severity in ["P0", "P1", "P2", "P3"]:
        lines.append(f"| {severity} | {counts[severity]} |")

    lines.extend(["", "## 优先人工查看", ""])
    for unit in units[:5]:
        lines.append(f"- [{unit['severity']} {unit['title']}]({unit['card_file']})：{unit['reviewer']}，建议 {unit['estimated_minutes']} 分钟")
    if not units:
        lines.append("- 未生成 Review Card。")

    lines.extend(["", "## 已知边界", ""])
    lines.append("- 该摘要来自静态 diff 分析和路径/文件特征分类，不等于人工 Review 结论。")
    lines.append("- 如未额外运行编译、测试、EXPLAIN、浏览器或生产只读核验，不能声称业务正确。")
    if source.get("dirty_status"):
        lines.append("- 生成时工作区存在未提交改动，请确认它们是否属于审查范围。")

    return "\n".join(lines) + "\n"


def render_routing(payload: dict[str, Any]) -> str:
    lines = [
        "# 人工 Review 分诊表",
        "",
        "| 严重度 | 是否阻断合并 | 推荐 reviewer | 卡片 | 建议耗时 | 人工只需要判断 |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for unit in payload["units"]:
        questions = "<br>".join(f"{idx + 1}. {md_escape(question)}" for idx, question in enumerate(unit["questions"][:3]))
        lines.append(
            f"| {unit['severity']} | {merge_gate(unit['severity'])} | {md_escape(unit['reviewer'])} | "
            f"[{md_escape(unit['title'])}]({unit['card_file']}) | "
            f"{unit['estimated_minutes']} 分钟 | {questions} |"
        )
    return "\n".join(lines) + "\n"


def render_card(unit: dict[str, Any]) -> str:
    lines = [
        f"# Review Card: {unit['title']}",
        "",
        f"- 严重度：{unit['severity']}",
        f"- 风险域：{unit['risk_domain']}",
        f"- 推荐 reviewer：{unit['reviewer']}",
        f"- 建议耗时：{unit['estimated_minutes']} 分钟",
        f"- 证据等级：{unit['evidence_level']}",
        "",
        "## 为什么要看",
        "",
        unit["why"],
        "",
        "## 人工只需要判断",
        "",
    ]
    for idx, question in enumerate(unit["questions"][:3], start=1):
        lines.append(f"{idx}. {question}")
    lines.extend(["", "## AI 已做检查", ""])
    lines.append("- 已收集 Git diff 的文件清单、增删行、提交范围和工作区状态。")
    lines.append("- 已按路径、文件名和常见风险关键词做初步分类。")
    lines.append("- 已把重复或相近风险合并为同一张 Review Card。")
    lines.extend(["", "## 建议补充验证", ""])
    for check in unit["checks"]:
        lines.append(f"- {check}")
    lines.extend(["", "## 涉及文件", ""])
    for item in unit["files"]:
        lines.append(file_line(item))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染 Review Pack。")
    parser.add_argument("--input", required=True, help="classify_review_units.py 输出的 JSON。")
    parser.add_argument("--output-dir", required=True, help="Review Pack 输出目录。")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    cards_dir = output_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    for old_card in cards_dir.glob("*.md"):
        old_card.unlink()

    (output_dir / "00-summary.md").write_text(render_summary(payload), encoding="utf-8")
    (output_dir / "01-human-routing.md").write_text(render_routing(payload), encoding="utf-8")
    for unit in payload["units"]:
        card_path = output_dir / unit["card_file"]
        card_path.parent.mkdir(parents=True, exist_ok=True)
        card_path.write_text(render_card(unit), encoding="utf-8")
    (output_dir / "review-pack.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    input_dir = output_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    source_input = Path(args.input)
    target_input = input_dir / source_input.name
    if source_input.resolve() != target_input.resolve():
        shutil.copyfile(source_input, target_input)

    print(f"已生成 Review Pack：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
