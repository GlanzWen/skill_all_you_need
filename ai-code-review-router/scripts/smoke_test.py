#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 smoke test：创建临时仓库并验证 Review Pack 生成链路。"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout.strip()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ai-review-router-test."))
    try:
        source_dir = tmp / "src/main/java/com/acme"
        source_dir.mkdir(parents=True)
        controller = source_dir / "UserController.java"
        controller.write_text("public class UserController {\n}\n", encoding="utf-8")

        run(["git", "init", "-q", str(tmp)])
        run(["git", "-C", str(tmp), "add", "."])
        run(["git", "-C", str(tmp), "-c", "user.name=Codex", "-c", "user.email=codex@example.invalid", "commit", "-qm", "init"])
        base = run(["git", "-C", str(tmp), "rev-parse", "HEAD"])

        controller.write_text("public class UserController {\n  private String token;\n}\n", encoding="utf-8")
        mapper_dir = tmp / "src/main/resources/mapper"
        mapper_dir.mkdir(parents=True)
        (mapper_dir / "TaskMapper.xml").write_text(
            '<select id="countTask">select count(*) from task where status != "cancel"</select>\n',
            encoding="utf-8",
        )

        review_pack = tmp / "review-pack"
        run(
            [
                "python3",
                str(ROOT / "scripts/run_review_router.py"),
                "--repo",
                str(tmp),
                "--base",
                base,
                "--head",
                "HEAD",
                "--output-dir",
                str(review_pack),
            ]
        )

        payload = json.loads((review_pack / "review-pack.json").read_text(encoding="utf-8"))
        unit_ids = {unit["id"] for unit in payload["units"]}
        required = {"security-auth", "api-compatibility", "data-sql"}
        missing = sorted(required - unit_ids)
        if missing:
            raise AssertionError(f"缺少期望 Review Unit：{missing}")
        for relative in ["00-summary.md", "01-human-routing.md", "cards/P0-security-auth.md", "cards/P1-api-compatibility.md", "cards/P1-data-sql.md"]:
            if not (review_pack / relative).exists():
                raise AssertionError(f"缺少输出文件：{relative}")
        print("smoke test passed")
        return 0
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    raise SystemExit(main())
