# 方案设计（plan）：Issue #120 — huawei-cloud-nat-list

## 1. 任务类型与复杂度

- 类型：feature（新增 skill）。
- 复杂度：中等（新目录 + 脚本 + 测试 + 5 份 references 文档，复用仓库既有 eip-list 模式）。

## 2. 总体方案

沿用仓库 `skills/network/eip/huawei-cloud-eip-list` 已验证的「CLI 优先 + SDK 兜底 + 只读守卫 + 离线单测」模式：

```text
agent → python3 scripts/list_nat_gateways.py
      → hcloud NAT ListNatGateways --cli-region=<region> [--limit --marker --name --spec --status --router_id]
      → Huawei Cloud NAT OpenAPI (nat.<region>.myhuaweicloud.com) → parsed JSON → table / --json / --names-only

(hcloud binary missing) → fallback: huaweicloudsdknat v2 NatClient.list_nat_gateways
```

## 3. 已核实的 API 事实（不猜测）

| 事实 | 来源 |
|------|------|
| KooCLI 服务名 `NAT`、操作名 `ListNatGateways` | 官方 CLI 命令参考 https://support.huaweicloud.com/clir-natgateway/nat-cli.html 「查询公网NAT网关列表 hcloud NAT ListNatGateways」 |
| REST：GET /v2/{project_id}/nat_gateways | 本地安装的官方 `huaweicloudsdknat` v2 `NatClient._list_nat_gateways_http_info`（method=GET, resource_path=/v2/{project_id}/nat_gateways） |
| 请求参数 | `ListNatGatewaysRequest`：id/name/status(spec, csv)/spec(csv)/router_id/internal_network_id/description/created_at/enterprise_project_id/admin_state_up/limit/marker/sort_key/sort_dir/tenant_id |
| 响应结构 | `ListNatGatewaysResponse.nat_gateways`（`NatGatewayResponseBody`：id/tenant_id/name/description/spec/status/admin_state_up/created_at/router_id/internal_network_id/enterprise_project_id/session_conf/ngport_ip_address/billing_info/dnat_rules_limit/snat_rule_public_ip_limit/pps_max/bps_max） |
| 分页 | `limit` + `marker`（marker=上一页最后一条网关 id；响应只有 `nat_gateways`，短页即止；默认 2000） |
| SDK region 目录 | `huaweicloudsdknat.v2.region.nat_region.NatRegion`（value_of 已验证 cn-north-4） |
| spec 取值 | "1" 小型 / "2" 中型 / "3" 大型 / "4" 超大型 / "5" 企业型（官方 API 文档 nat_api_0002/0062） |
| IAM 动作 | `nat:natGateways:list`（官方权限与授权项表 nat_api_0029） |

环境无 hcloud 二进制（与 eip-list 开发时一致）：KooCLI 路径以官方 CLI 命令参考 + SDK 请求模型为准，
离线单测 mock 子进程；SDK 路径以本地安装的 `huaweicloudsdknat` 做导入级验证。

## 4. 模块设计

- `scripts/list_nat_gateways.py`（stdlib only）：
  - 错误体系：`NatListError` → `GuardError` / `ConfigError` / `AuthError` / `ApiError`。
  - `guard_write_intent()` / `guard_scan_text()`：NAT 变更关键词（CreateNatGateway/DeleteNatGateway/UpdateNatGateway + create/delete/update/... 通用词），仅扫描操作/命令位（不扫描 --name/--status 等用户过滤值），命令执行前拦截。
  - `guard_operation()`：仅允许 `ListNatGateways`。
  - `build_command()`：`NAT ListNatGateways --cli-region --limit [--marker --name --spec --status --router_id]`。
  - `run_hcloud()`：subprocess 执行（120s 超时），FileNotFoundError 触发一次性 SDK 回退。
  - `classify_hcloud_failure()`：`[USE_ERROR]`（rc=0 也算失败）/ 缺 AK/SK / 401-403 / 其他。
  - `extract_json()` / `extract_gateways()`（nat_gateways / natGateways / natGateWays 键容错）/ `_last_gateway_id()`（NAT v2 以最后一条网关 id 作为下一页 marker）。
  - `list_nat_gateways_via_sdk()`：BasicCredentials（白名单 AK/SK 环境变量）+ project_id（--project-id 或白名单环境变量）+ NatRegion / Region 兜底；datetime 字段 JSON 安全化。
  - `render_table()`：PREFERRED_COLUMNS 优先 + 其余字段并集自动补列，缺值 `-`。
  - 输出模式：默认表格 / `--json` / `--names-only`；空列表 exit 0 带过滤条件提示。
- `tests/test_list_nat_gateways.py`：FakeRunner mock subprocess；SDK 回退用 `list_nat_gateways_via_sdk` mock + 真实 SDK 安装时的导入回归（未装则 skip）。
- `SKILL.md`：front-matter（name/description/tags）+ Overview/Prerequisites/Workflow/Core Commands/Parameter Table/Write-Intent Guard/KooCLI Format/Error Handling/Edge Cases/Testing/References。
- `references/`：iam-policies.md、cli-installation-guide.md、verification-method.md、dataflow-diagram.md、acceptance-criteria.md。
- `templates/test-vars.json`：验收用只读命令清单。

## 5. 测试策略（TDD）

1. RED：先写测试（守卫/构建命令/解析/分类/分页/渲染/main 输出/SDK 回退）。
2. GREEN：实现脚本使测试通过。
3. REFACTOR：对齐仓库风格，无重复逻辑。
4. 回归：`skills/network/eip/huawei-cloud-eip-list` 等相邻 skill 现有测试保持通过。

时间类断言只用固定样例字符串（created_at 为 API 返回字符串），不引入时序耦合。

## 6. 提交与交付

- 原子提交：① 文档方案 ② skill 本体（脚本+SKILL.md+references+templates+tests）。
- PR：head=feat/issue-120，base=origin/master（master），关联 issue 120。
- A2A 通知 QA 审查。
