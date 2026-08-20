---
name: ai-code-review-router
description: 当用户需要审查大批量 AI 生成代码、PR diff、分支差异或提交范围，并希望先由 AI 做只读初审、风险分类、证据标注、人工 reviewer 分诊和 Review Card 生成时使用。适用于生成本地 review-pack、按严重度和风险域拆分人工审核任务、降低人工 Code Review 的无聊重复劳动；默认不修改被审查代码、不自动评论 PR、不替代人工最终结论。
---

# AI Code Review Router

## 定位

把大批量代码差异先拆成可处理的人工审核卡片。该 skill 的输出不是“AI 已经审完”，而是一个 `review-pack/`：包含摘要、分诊表、风险卡片和结构化 JSON，帮助人工 reviewer 只看真正需要判断的部分。

## 默认边界

- 只读分析被审查仓库；除非用户明确要求，不修改业务代码、不清理工作区、不提交、不推送。
- 先确认审查范围：当前目录、base、head、提交列表、变更文件、工作区是否有未提交改动。
- 描述系统当前行为时，优先依据代码、测试、配置和运行结果；设计文档只能作为低置信背景。
- 所有风险结论必须带证据等级：`已验证`、`静态代码证据`、`代码推断`、`需要人工确认`、`低置信怀疑`。
- 不把编译通过、无测试可跑、静态检查通过外推为业务正确。
- 人工分诊建议必须说明“为什么给这个人看”和“人工只需要判断什么”。

## 工作流

1. 锁定审查范围。
   - 如果用户给出 base/head，使用用户指定范围。
   - 如果用户只说“审查当前改动”，先查看 Git 状态和提交历史，必要时询问 base。
   - 如果仓库不是 Git 仓库，退化为用户给定文件列表或当前目录只读扫描。

2. 收集差异上下文。
   - 优先运行 `scripts/run_review_router.py` 一键生成完整 `review-pack/`。
   - 需要调试中间数据时，再分别运行 `scripts/collect_git_diff.py`、`scripts/classify_review_units.py` 和 `scripts/render_review_pack.py`。
   - 对大型 diff，保留文件清单、提交清单、numstat 和截断 diff；不要把截断后的 diff 当作完整证据。

3. 分类 Review Unit。
   - 运行 `scripts/classify_review_units.py` 生成 `review-pack/input/review-units.json`。
   - 结合 `references/review-taxonomy.md` 和 `references/routing-rules.md` 校正自动分类。
   - 合并重复样板、生成代码、纯格式化文件，避免给人工制造噪音。

4. 生成 Review Pack。
   - 运行 `scripts/render_review_pack.py` 输出：
     - `review-pack/00-summary.md`
     - `review-pack/01-human-routing.md`
     - `review-pack/cards/*.md`
     - `review-pack/review-pack.json`

5. 人工前复核。
   - 重新看 P0/P1 卡片，删除没有代码锚点或证据支撑的强结论。
   - 对无法证明的问题改写为“需要人工确认”。
   - 最终回复用户时列出产物路径、审查范围、已验证命令和未验证边界。

## 推荐命令

在被审查仓库中运行，假设该 skill 位于 `/Users/zcy/Desktop/skill/ai-code-review-router`。默认会纳入当前工作区和未跟踪文件，适合 AI 一次性生成但尚未提交的代码：

```bash
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/run_review_router.py \
  --repo . \
  --base main \
  --head HEAD \
  --output-dir review-pack
```

如果只审查已提交分支差异，增加 `--committed-only`。如果 `main` 不是正确基线，不要猜；改用用户指定的目标分支、共同祖先或提交范围。

## 人工 Review Card 要求

每张卡片必须回答：

- 分配给谁：不是人名，而是 reviewer 类型或领域角色。
- 为什么要看：说明业务/技术风险，不写空泛描述。
- 人工只需要判断什么：最多 3 个判断题。
- AI 已做什么：列出已完成的静态或运行验证。
- 还缺什么证据：明确需要人工、测试、DB、日志或生产只读验证的部分。
- 涉及文件：列出相对路径，必要时补充函数、类名、SQL id 或配置 key。

## 参考资料

- 使用说明：读取 `references/usage.md`。
- 分类和严重度：读取 `references/review-taxonomy.md`。
- 人工分诊规则：读取 `references/routing-rules.md`。
- 输出格式：读取 `references/output-templates.md`。
