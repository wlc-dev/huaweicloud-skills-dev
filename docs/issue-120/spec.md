# 需求文档（PRD）：Issue #120 — 新增skill: 查询华为云NAT网关列表

> Issue: https://gitcode.com/hd-skills-pre/huaweicloud-skills-dev/issues/120
> Spec 来源：Issue Agent 已发布 Spec（spec-ready），本文档为 coding 实现对齐版。

## 1. 背景与目标

用户需要快速盘点账户下的**公网 NAT 网关**资源（名称、规格、关联 VPC、状态、创建时间等基础信息），
要求命令简洁、输出表格化、严格只读。需求方已确认与现有 `huawei-cloud-network-query` 的差异化：
新建独立的轻量 skill `huawei-cloud-nat-list`（只要列表+表格，不引入大而全查询技能）。

## 2. 用户与场景

- 用户：华为云租户运维 / 巡检人员。
- 场景：资源盘点、日常巡检、为其他技能预查 NAT 网关 `id` / `router_id`。

## 3. 功能需求

| # | 需求 | 说明 |
|---|------|------|
| F1 | 查询公网 NAT 网关列表 | KooCLI `hcloud NAT ListNatGateways`（GET /v2/{project_id}/nat_gateways，已核对官方 CLI 命令参考与 SDK 元数据） |
| F2 | 输出字段 | id / name / spec / status / router_id（关联VPC）/ internal_network_id / description / created_at + 其余返回字段 |
| F3 | 输出模式 | 默认表格；`--json` 原始数组；`--names-only` 名称清单 |
| F4 | 过滤参数 | `--name` / `--spec` / `--status` / `--vpc`（router_id，均真实服务端参数）；region 可覆盖 |
| F5 | SDK 兜底 | hcloud 未安装时回退 `huaweicloudsdknat` v2 `NatClient.list_nat_gateways` |
| F6 | 只读写意图守卫 | create/delete/update/... 变更意图直接拒绝，任何命令执行前拦截 |
| F7 | 明确错误提示 | 空列表 / 403 / 缺凭据 / hcloud 未装 / 参数错误 / 超时 各自给出中文提示与退出码 |

## 4. 范围

### In Scope
- `skills/network/nat/huawei-cloud-nat-list/`：SKILL.md、scripts/、tests/、references/、templates/。

### Out of Scope
- 私网 NAT（SNAT/DNAT 规则查询与增删改）。
- NAT 网关创建/删除/变更、EIP 绑定/解绑等任何写操作。
- 导出 md/excel（后续迭代）。

## 5. 验收标准

- [x] 列表查询与过滤（--name/--spec/--status/--vpc）生效（服务端参数透传）
- [x] hcloud 缺失时 SDK 回退可查询
- [x] 空列表 / 403 / 401 / 缺凭据有明确提示（退出码区分，KooCLI exit 0 错误信封按错误处理）
- [x] 写意图被守卫拒绝，全程只读
- [x] 现有测试通过 + 新增离线单测覆盖（79 项）
