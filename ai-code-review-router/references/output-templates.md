# Review Pack 输出模板

## `00-summary.md`

必须包含：

- 审查范围：repo、base、head、生成时间。
- 差异规模：文件数、增删行、提交数。
- 风险总览：P0/P1/P2/P3 数量。
- 最需要人工先看的 3-5 张卡片。
- AI 已验证内容和未验证边界。

## `01-human-routing.md`

必须包含：

- reviewer 类型。
- 对应卡片。
- 建议耗时。
- 人工只需要判断的问题。
- 是否阻断合并。

## Card 文件

命名格式：

```text
cards/P1-data-sql.md
cards/P2-frontend-interaction.md
cards/P3-generated-boilerplate.md
```

正文模板：

```markdown
# Review Card: <标题>

- 严重度：P1
- 风险域：数据/SQL
- 推荐 reviewer：数据/性能 reviewer
- 建议耗时：10-15 分钟
- 证据等级：静态代码证据 + 需要人工确认

## 为什么要看

说明这组变更为什么值得人工看，重点写业务或技术影响。

## 人工只需要判断

1. 判断题一。
2. 判断题二。
3. 判断题三。

## AI 已做检查

- 已收集 diff、文件列表和提交范围。
- 已按路径和变更特征做初步分类。

## 还缺的证据

- 需要人工确认业务口径。
- 需要真实数据或测试样例验证。

## 涉及文件

- `path/to/File.java`
```

## 回复用户时的最小格式

```markdown
已生成 Review Pack：

- 摘要：`review-pack/00-summary.md`
- 分诊：`review-pack/01-human-routing.md`
- 卡片：`review-pack/cards/`
- 结构化数据：`review-pack/review-pack.json`

已验证：
- <命令和结果>

未验证边界：
- <不能外推的部分>
```
