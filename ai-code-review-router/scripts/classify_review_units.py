#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把文件级 diff 粗分为 Review Unit。"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


RULES = [
    {
        "unit": "security-auth",
        "title": "鉴权/安全敏感变更",
        "severity": "P0",
        "patterns": r"auth|permission|session|cookie|token|jwt|sign|secret|password|cors|csrf|acl|role",
        "reviewer": "安全 reviewer 或权限 owner",
        "why": "这组变更触及鉴权、会话、签名、跨域或敏感凭据，错误可能导致越权、数据泄露或访问控制失效。",
        "questions": [
            "是否存在越权访问、权限绕过或 SESSION/Header 透传语义变化？",
            "token、签名、Cookie、密钥和错误日志是否存在泄露风险？",
            "跨域、CSRF、重定向或回调地址是否仍受白名单和同源约束保护？",
        ],
        "checks": ["检查权限判断链路", "检查敏感字段是否进入日志或响应", "必要时补安全用例"],
    },
    {
        "unit": "state-machine",
        "title": "状态机/任务生命周期变更",
        "severity": "P1",
        "patterns": r"status|state|transition|lifecycle|cancel|retry|terminal|workflow",
        "reviewer": "资深业务 reviewer",
        "why": "这组变更可能影响任务状态迁移、取消、失败、重试或终态保护，容易造成状态污染或重复处理。",
        "questions": [
            "非法状态迁移是否在持久化前被拦截？",
            "取消、失败、重试、超时路径是否会污染成功口径？",
            "重复请求、重复消费或恢复执行是否保持幂等？",
        ],
        "checks": ["补状态迁移组合样例", "核对终态保护", "检查事件/文件/消息是否零写入"],
    },
    {
        "unit": "data-sql",
        "title": "数据/SQL/统计口径变更",
        "severity": "P1",
        "patterns": r"mapper|dao|repository|sql|\.xml$|\.sql$|select|update|delete|insert|count|page|index",
        "reviewer": "数据/性能 reviewer",
        "why": "这组变更可能影响 SQL 口径、分页、统计、批量更新或查询性能，错误会误导业务判断或放大线上压力。",
        "questions": [
            "统计对象、状态过滤、取消/失败/重试口径是否符合业务定义？",
            "查询是否可能扫大表、破坏索引或引入 N+1？",
            "批量 update/delete 是否有安全条件、事务边界和回滚方案？",
        ],
        "checks": ["必要时执行 EXPLAIN", "构造成功/失败/取消样例", "做只读 SQL 对账"],
    },
    {
        "unit": "api-compatibility",
        "title": "接口兼容性变更",
        "severity": "P1",
        "patterns": r"controller|api|client|dto|request|response|dubbo|openapi|swagger|proto|graphql|route",
        "reviewer": "接口 owner 和调用方代表",
        "why": "这组变更可能影响入参、出参、错误码、默认值或调用方兼容性。",
        "questions": [
            "新增/删除/重命名字段是否保持向前和向后兼容？",
            "错误码、空值、默认值和分页语义是否变化？",
            "调用方、网关、文档和测试是否同步更新？",
        ],
        "checks": ["跑契约或接口测试", "核对序列化兼容性", "检查调用方编译或引用"],
    },
    {
        "unit": "concurrency-async",
        "title": "并发/MQ/异步执行变更",
        "severity": "P1",
        "patterns": r"mq|queue|consumer|producer|async|thread|executor|schedule|cron|lock|transaction|idempot",
        "reviewer": "后端资深 reviewer",
        "why": "这组变更涉及异步执行、消息、锁、事务或调度，容易产生重复消费、乱序、积压或并发写冲突。",
        "questions": [
            "重复执行、重试和失败恢复是否幂等？",
            "事务边界和消息发送顺序是否会造成不一致？",
            "限流、降级、积压和异常日志是否足够支撑排障？",
        ],
        "checks": ["检查 MQ 重试策略", "检查事务和锁范围", "补重复消费样例"],
    },
    {
        "unit": "config-release",
        "title": "配置/发布/构建变更",
        "severity": "P2",
        "patterns": r"application\.(yml|yaml|properties)|bootstrap|dockerfile|pom\.xml|package\.json|vite|webpack|gradle|maven|helm|k8s|deploy|config|feature",
        "reviewer": "发布 owner 或 SRE",
        "why": "这组变更影响构建、配置、依赖、灰度或部署行为，风险常出现在环境差异和默认值。",
        "questions": [
            "默认配置是否安全，灰度和回滚是否明确？",
            "依赖版本变化是否带来运行时兼容风险？",
            "本地、测试、预发、生产环境是否存在配置差异？",
        ],
        "checks": ["跑构建命令", "核对配置 key", "检查依赖树或锁文件"],
    },
    {
        "unit": "frontend-interaction",
        "title": "前端交互/页面状态变更",
        "severity": "P2",
        "patterns": r"\.(tsx|ts|jsx|js|vue|css|scss|less)$|component|page|view|store|router|form",
        "reviewer": "前端 owner",
        "why": "这组变更可能影响页面流程、表单、路由、状态管理、错误态或响应式布局。",
        "questions": [
            "关键流程、错误态、空态和加载态是否仍可用？",
            "表单校验、权限态和路由跳转是否符合业务预期？",
            "移动端和窄屏是否存在遮挡、溢出或不可点击问题？",
        ],
        "checks": ["跑前端测试或构建", "用浏览器 smoke 关键路径", "检查控制台错误"],
    },
    {
        "unit": "tests",
        "title": "测试和验证变更",
        "severity": "P3",
        "patterns": r"test|spec|fixture|mock|snapshot|__tests__",
        "reviewer": "原作者和模块 owner",
        "why": "这组变更主要影响测试、fixture 或快照，需要确认测试是否对应真实行为变化。",
        "questions": [
            "测试变更是否覆盖了生产代码的关键风险？",
            "快照或 fixture 更新是否有明确行为原因？",
            "是否删除了原本能阻止回归的断言？",
        ],
        "checks": ["运行相关测试", "抽查断言是否仍有意义", "核对 fixture 来源"],
    },
    {
        "unit": "generated-boilerplate",
        "title": "生成代码/样板/低风险批量变更",
        "severity": "P3",
        "patterns": r"generated|gen/|target/|dist/|build/|vendor|lock$|\.lock$|snapshot",
        "reviewer": "原作者抽样 + 轻量复核",
        "why": "这组变更看起来更接近生成、样板或批量输出，适合抽样确认生成模式，避免人工逐行读重复内容。",
        "questions": [
            "生成器或输入 schema 是否也发生变化？",
            "抽样文件的 diff 模式是否一致且符合预期？",
            "是否混入了手写业务逻辑修改？",
        ],
        "checks": ["抽样 3-5 个代表文件", "核对生成命令或来源", "确认未混入手写逻辑"],
    },
]


def severity_min(left: str, right: str) -> str:
    return left if SEVERITY_ORDER[left] <= SEVERITY_ORDER[right] else right


def extract_diff_chunks(diff_text: str) -> dict[str, str]:
    chunks: dict[str, list[str]] = {}
    current_path = ""
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            current_path = ""
            if len(parts) >= 4 and parts[3].startswith("b/"):
                current_path = parts[3][2:]
                chunks.setdefault(current_path, [])
            continue
        if current_path:
            chunks[current_path].append(line)
    return {path: "\n".join(lines) for path, lines in chunks.items()}


def classify_file(path: str, diff_chunk: str, additions: int | None, deletions: int | None) -> list[dict[str, Any]]:
    haystack = f"{path}\n{diff_chunk}".lower()
    matched = [rule for rule in RULES if re.search(rule["patterns"], haystack)]
    if not matched:
        matched = [
            {
                "unit": "general-business",
                "title": "一般业务代码变更",
                "severity": "P2",
                "reviewer": "模块 owner",
                "why": "这组变更不属于特定高风险域，但仍需要模块 owner 判断业务语义和异常路径。",
                "questions": [
                    "核心业务语义是否符合需求？",
                    "异常、空值、边界输入是否有处理？",
                    "是否有足够测试或人工 smoke 证据？",
                ],
                "checks": ["阅读调用链", "运行相关测试", "抽查异常路径"],
            }
        ]

    churn = (additions or 0) + (deletions or 0)
    if churn > 500:
        for rule in matched:
            if rule["severity"] == "P3":
                rule = dict(rule)
                rule["severity"] = "P2"
    return matched


def normalize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_units(payload: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    diff_chunks = extract_diff_chunks(payload.get("diff", ""))
    for file_item in payload.get("files", []):
        path = file_item.get("path", "")
        additions = file_item.get("additions")
        deletions = file_item.get("deletions")
        for rule in classify_file(path, diff_chunks.get(path, ""), additions, deletions):
            unit_id = rule["unit"]
            unit = grouped.setdefault(
                unit_id,
                {
                    "id": unit_id,
                    "title": rule["title"],
                    "severity": rule["severity"],
                    "risk_domain": rule["title"],
                    "reviewer": rule["reviewer"],
                    "why": rule["why"],
                    "questions": rule["questions"],
                    "checks": rule["checks"],
                    "evidence_level": "静态代码证据 + 需要人工确认",
                    "estimated_minutes": 10,
                    "files": [],
                },
            )
            unit["severity"] = severity_min(unit["severity"], rule["severity"])
            unit["files"].append(file_item)

    units = list(grouped.values())
    for unit in units:
        churn = sum((item.get("additions") or 0) + (item.get("deletions") or 0) for item in unit["files"])
        if unit["severity"] == "P0":
            unit["estimated_minutes"] = 30
        elif unit["severity"] == "P1":
            unit["estimated_minutes"] = 15 if churn < 300 else 30
        elif unit["severity"] == "P2":
            unit["estimated_minutes"] = 10 if churn < 300 else 20
        else:
            unit["estimated_minutes"] = 5 if len(unit["files"]) <= 8 else 10
        unit["card_file"] = f"cards/{unit['severity']}-{normalize_slug(unit['id'])}.md"

    units.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["id"]))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repo": payload.get("repo"),
            "base": payload.get("base"),
            "head": payload.get("head"),
            "base_sha": payload.get("base_sha"),
            "head_sha": payload.get("head_sha"),
            "range": payload.get("range"),
            "dirty_status": payload.get("dirty_status", []),
            "totals": payload.get("totals", {}),
            "diff_truncated": payload.get("diff_truncated", False),
            "commits": payload.get("commits", []),
        },
        "units": units,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="把 diff 上下文分类为 Review Unit。")
    parser.add_argument("--input", required=True, help="collect_git_diff.py 输出的 JSON。")
    parser.add_argument("--output", required=True, help="输出 review-units JSON。")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = build_units(payload)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
