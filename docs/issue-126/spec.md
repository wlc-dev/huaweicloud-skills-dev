# 需求文档（PRD）：Issue #126 — huawei-cloud-rds-export-markdown 新增 --sort-by 排序

> Issue: https://gitcode.com/hd-skills-pre/huaweicloud-skills-dev/issues/126
> Spec 来源：Issue Agent 已发布 Spec（评论 id 201303333，spec-ready），本文档为 coding 实现对齐版。

## 1. 背景与目标

`skills/database/rds/huawei-cloud-rds-export-markdown` 已能通过 `hcloud RDS ListInstances`
（只读 `GET /v3/{project_id}/instances`）查询 RDS 实例并导出 Markdown 表格，当前仅支持
`--name`（服务端过滤）与 `--status`（客户端过滤），导出行的顺序完全取决于 API 返回顺序。

RDS 巡检、资产盘点与交接报告需要在跨区域 / 跨批次比对实例清单时快速定位差异，无序表格难以核对。

**目标**：新增 `--sort-by name|created`，在拉取到实例列表后在客户端排序，再渲染 Markdown。

**成功标准**：

- `--sort-by name` 输出按实例名升序（大小写不敏感，等值保持原相对顺序）。
- `--sort-by created` 输出按创建时间升序（旧 → 新），不可解析 / 缺失值排末尾。
- 不传 `--sort-by` 时输出与改动前完全一致（无回归）。
- 非法取值明确报错、退出码 1、不生成文件。
- `--sort-by created` 不触发写意图守卫的误判。

## 2. 用户与场景

| 用户 | 场景 | 命令 |
| ---- | ---- | ---- |
| 运维工程师 | 按实例名对齐交接清单 | `--sort-by name` |
| 值班人员 | 按创建时间梳理最老 / 最新实例 | `--sort-by created` |
| 资产盘点 | 先按状态过滤再按名称排序 | `--status ACTIVE --sort-by name` |

## 3. 功能范围

### 3.1 In Scope

- `scripts/list_rds_export_markdown.py`：新增 `--sort-by`、`sort_instances()`、`SortError`，
  写意图守卫白名单补 `--sort-by`。
- `SKILL.md`：参数表、Core Commands 示例、description/key properties、Testing 覆盖清单同步。
- `tests/test_list_rds_export_markdown.py`：两种取值、无参不回归、非法取值、守卫回归。
- `docs/issue-126/`：本 PRD + 方案 + 任务拆解。

### 3.2 Out of Scope

- 不向 `hcloud RDS ListInstances` 传排序参数（该 API 无排序 / 顺序参数，`build_command()` 保持不变）。
- 不改变 `--name` / `--status` 过滤语义，不改变分页、渲染列与写文件逻辑。
- 不新增技能、不新增长期分支；不引入降序 / 多字段排序参数。

## 4. 行为规格

| 输入 | 行为 |
| ---- | ---- |
| 不传 `--sort-by` | API 原序渲染，输出与改动前逐字节一致（除既有 `Generated at` 时间戳） |
| `--sort-by name` | 取 `name`（缺失回退 `id`）大小写不敏感升序；两者都缺失排末尾 |
| `--sort-by created` | 解析 `created` 时间升序；ISO8601 / 空格分隔 / 带时区均支持；不可解析回退字符串比较；缺失排末尾 |
| `--sort-by <其他>` | `[错误] --sort-by 仅支持 name 或 created（收到: xxx）`，退出码 1，不生成文件 |
| `--status X --sort-by name` | 先客户端过滤，再排序 |

## 5. 风险与缓解

| 风险 | 影响 | 缓解 |
| ---- | ---- | ---- |
| 写意图守卫分隔符归一化后做子串匹配，`created` 命中关键词 `create` | `--sort-by created` 被误判为写操作并退出 1 | `READ_ONLY_VALUE_FLAGS` 加入 `--sort-by`，并新增守卫回归测试（含 `--sort-by=created` 形式） |
| 时区混用（`Z` / `+0800` / 无时区）导致 `TypeError` | 排序崩溃 | 统一转换为 UTC aware datetime 后以 epoch 比较 |
| 新增参数改变空结果提示 | 输出回归 | 仅在传参时追加 `sort-by=` 描述，不传时保持原文案 |