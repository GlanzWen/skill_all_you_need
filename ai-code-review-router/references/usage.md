# AI Code Review Router 使用方式

## 适用场景

用于先把大批量 AI 生成代码、PR diff、分支差异或未提交工作区改动做一次只读初审，再拆成适合人工审核的 Review Pack。

这个工具不替代人工 Code Review。它的作用是把无聊重复的清点工作前置处理掉，让人工 reviewer 直接看风险卡片、分诊表和少量重点文件。

## 前置条件

- 被审查目录最好是 Git 仓库。
- 本机需要可运行 `python3` 和 `git`。
- 审查前先确认正确的 `base` 和 `head`。
- 如果要审查 AI 刚生成但尚未提交的代码，保留默认模式即可。

## 一键生成 Review Pack

在被审查仓库根目录执行：

```bash
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/run_review_router.py \
  --repo . \
  --base main \
  --head HEAD \
  --output-dir review-pack
```

默认会同时纳入：

- `base..HEAD` 的已提交差异。
- 当前工作区未提交改动。
- 未跟踪新增文件。

这适合 AI 一次性生成大量文件但还没提交的场景。

## 只审查已提交分支差异

如果只想看 `base..head`，不纳入当前工作区和未跟踪文件：

```bash
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/run_review_router.py \
  --repo . \
  --base main \
  --head HEAD \
  --output-dir review-pack \
  --committed-only
```

常见用法：

```bash
# 审查当前分支相对 main 的差异
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/run_review_router.py \
  --repo . \
  --base main \
  --head HEAD \
  --output-dir review-pack

# 审查某个提交范围
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/run_review_router.py \
  --repo . \
  --base 1a2b3c4 \
  --head 9d8e7f6 \
  --output-dir review-pack \
  --committed-only

# 输出到自定义目录，避免覆盖已有 review-pack
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/run_review_router.py \
  --repo . \
  --base origin/main \
  --head HEAD \
  --output-dir /tmp/my-review-pack
```

## 输出内容

运行成功后会生成：

```text
review-pack/
├── 00-summary.md
├── 01-human-routing.md
├── cards/
│   ├── P0-security-auth.md
│   ├── P1-api-compatibility.md
│   └── P1-data-sql.md
├── input/
│   ├── diff-context.json
│   └── review-units.json
└── review-pack.json
```

各文件用途：

| 文件 | 用途 |
| --- | --- |
| `00-summary.md` | 给负责人快速看审查范围、差异规模、风险总览和优先卡片 |
| `01-human-routing.md` | 给分配人看 reviewer 类型、是否阻断合并、建议耗时和人工判断题 |
| `cards/*.md` | 给具体 reviewer 看，每张卡聚焦一个风险域 |
| `review-pack.json` | 给后续平台、脚本或统计分析使用 |
| `input/*.json` | 保留中间数据，便于排查分类或渲染问题 |

## 如何阅读结果

建议顺序：

1. 先看 `00-summary.md`，确认审查范围、base/head、文件数和 diff 是否截断。
2. 再看 `01-human-routing.md`，按 P0、P1、P2、P3 分配人工 reviewer。
3. 让 reviewer 只打开分配给自己的 `cards/*.md`。
4. P0 默认阻断合并；P1 合并前必须确认；P2 建议确认；P3 可以抽查。
5. 对每张卡只回答“人工只需要判断”的 1-3 个问题，不要重新从零扫完整 diff。

## 严重度含义

| 等级 | 含义 | 处理建议 |
| --- | --- | --- |
| P0 | 可能涉及安全、资损、数据破坏、核心链路不可用或明显兼容性破坏 | 阻断合并，必须深审 |
| P1 | 可能导致业务结果错误、统计污染、状态污染、性能退化或调用方受影响 | 合并前必须确认 |
| P2 | 局部缺陷、边界条件、发布配置、可观测性或维护性风险 | 建议确认或补验证 |
| P3 | 生成代码、样板、纯格式化、低风险重复变更 | 抽样确认即可 |

## 常见参数

| 参数 | 说明 |
| --- | --- |
| `--repo` | 被审查仓库路径，默认当前目录 |
| `--base` | 审查基线，例如 `main`、`origin/main` 或提交 SHA |
| `--head` | 审查目标，默认 `HEAD` |
| `--output-dir` | Review Pack 输出目录，默认 `review-pack` |
| `--committed-only` | 只审查已提交差异，不纳入工作区和未跟踪文件 |
| `--max-diff-chars` | diff 文本最大字符数，超出会截断 |

## 选择 base/head 的建议

- 审查 PR：`--base origin/main --head HEAD`，或使用 PR 的目标分支作为 base。
- 审查本地 AI 生成改动：`--base main --head HEAD`，保持默认模式纳入工作区。
- 审查两个提交之间的差异：`--base <old_sha> --head <new_sha> --committed-only`。
- 如果不确定 base，不要猜；先确认目标分支或共同祖先。

## 常见问题

### 提示无法自动确定 base

显式传入 `--base`：

```bash
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/run_review_router.py \
  --repo . \
  --base main \
  --head HEAD \
  --output-dir review-pack
```

### 生成结果里显示 diff 已截断

说明差异很大，工具只保留了部分 diff 文本用于分类。此时不能把卡片当作完整证据，人工需要结合完整 diff 或扩大 `--max-diff-chars` 后重跑。

```bash
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/run_review_router.py \
  --repo . \
  --base main \
  --head HEAD \
  --output-dir review-pack \
  --max-diff-chars 800000
```

### Review Pack 里没有卡片

常见原因：

- base/head 没有差异。
- 使用了 `--committed-only`，但 AI 生成代码还在未提交工作区。
- 当前目录不是预期仓库。

先检查 Git 状态和目标范围，再重跑。

### 卡片分类不准

先查看：

- `review-pack/input/diff-context.json`
- `review-pack/input/review-units.json`

如果是规则问题，优先调整：

- `references/review-taxonomy.md`
- `references/routing-rules.md`
- `scripts/classify_review_units.py`

## 验证 skill 本身

修改脚本或规则后，运行本地烟测：

```bash
python3 /Users/zcy/Desktop/skill/ai-code-review-router/scripts/smoke_test.py
```

再运行 skill 结构校验：

```bash
python3 /Users/zcy/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/zcy/Desktop/skill/ai-code-review-router
```

## 边界说明

- Review Pack 是静态初审和人工分诊产物，不是人工 Review 通过结论。
- 工具不会自动修改业务代码、提交代码或评论 PR。
- 编译通过、测试通过、静态检查通过都不能自动证明业务正确。
- 没有真实运行、DB 对账、生产只读日志或领域 owner 确认时，只能写“需要人工确认”。
