# Issue #125 Spec — 新增 skill huawei-cloud-dds-list（DDS 实例列表，只读）

## 背景与定位

生产仓已有复合 skill `huawei-cloud-dds-dcs-instance-management`。本开发仓需要新增
**独立轻量只读** skill：查询华为云账号/区域下 DDS（文档数据库服务）实例列表，
定位已由需求方 2026-10-30 确认，无重复风险。

## 目标（Objective）

- 新增 `skills/database/dds/huawei-cloud-dds-list/`（仅新增，不改动现有文件）。
- 展示实例名称、类型（集群 Sharding / 副本集 ReplicaSet / 单节点 Single）、
  状态、版本（DB Engine Version，datastore.version）等信息。
- 默认输出简洁列表（名称清单）；`--table` 全字段表格；`--json` 原始输出。

## 实测 API 事实（KooCLI 7.2.12 + 官方 IAM schema 实测，非臆造）

- KooCLI 服务名 `DDS`，操作名 `ListInstances`：
  `hcloud DDS ListInstances --cli-region=<region> --limit=1` 实测返回
  `{"instances": [], "total_count": 0}`（Method: GET）。
- 服务端查询参数（`hcloud DDS ListInstances --help` 实测）：
  `--project_id`(path)、`--datastore_type`(DDS-Community|DDS-Enhanced)、`--id`、
  `--limit`(1~100)、`--mode`(Sharding|ReplicaSet|Single)、`--name`
  （前缀 `*` 为模糊，否则精确）、`--offset`、`--subnet_id`、`--tags`、`--vpc_id`。
  ⚠️ **无 status 服务端参数**——状态过滤以客户端过滤实现并在文档中注明。
- IAM 只读 action（`hcloud IAM GetAuthorizationSchemaV5 --service_code=dds` 实测）：
  `dds:instance:listAll`（access_level=list，alias `dds:instance:list`，
  「授予查询数据库实例列表的权限」）。
- 实例字段（官方 API ListInstances 响应，hcloud 与 huaweicloudsdkdds v3
  `QueryInstanceResponse` 模型一致）：`id`/`name`/`status`/`mode`/
  `datastore{type,version,storage_engine}`/`created`/`updated`/`vpc_id`/
  `subnet_id`/`security_group_id`/`groups[]`（规格在
  `groups[].nodes[].spec_code`）/`actions[]` 等。
  ⚠️ 无顶层 `type`（实例类型即 `mode`）、无 `created_at`/`updated_at`
  （创建/更新时间为 `created`/`updated`）、无顶层 `flavor[]`。

## Scope

In：
- SKILL.md（触发词：DDS/文档数据库/DDS实例/查询DDS实例列表/DDS实例列表等）
- scripts/list_dds.py（纯标准库；hcloud 优先，缺 hcloud 回退官方
  huaweicloudsdkdds v3 SDK `DdsClient.list_instances`）
- scripts/ensure_cli.sh、scripts/install_cli.sh（skill-quality-cli 注入脚本）
- references/（iam-policies.md、cli-installation-guide.md、verification-method.md、
  dataflow-diagram.md、acceptance-criteria.md）
- templates/test-vars.json
- tests/test_list_dds.py（离线单测，mock hcloud 子进程与 fake SDK）

功能点：
- 默认简洁名称列表（`--names-only` 同义）；`--table` 含 实例ID/名称/类型/状态/
  版本/规格/创建时间/VPC/子网（缺失值渲染 `-`；类型列显示 集群/副本集/单节点）；
  `--json` 原始实例数组。
- 服务端过滤：`--name`（`--fuzzy` 加 `*` 前缀转模糊）、`--instance-id`、
  `--mode`、`--datastore-type`、`--vpc-id`、`--subnet-id`；客户端过滤 `--status`。
- 自动分页：limit 1~100（默认 100），offset 起始，按 total_count 自动翻页，
  `--max-pages` 防死循环，`--single-page` 单页模式。
- `--region`（默认 cn-north-4）、`--project-id` 覆盖。
- 错误提示：空列表/403/缺 AK·SK/缺 hcloud/`[USE_ERROR]`/翻页越界，退出码明确。
- 只读守卫：任何写意图（create/delete/restart/resize/backup/update/modify/
  scale 等）或非 ListInstances 操作在执行前拒绝，退出码 1。
- 凭据仅经 KooCLI profile 或 AK·SK 环境变量离线注入，脚本不读/不存/不回显密钥。

Out：一切 DDS 变更操作（创建/删除/重启/扩缩容/备份/恢复/改规格等）、按标签
查询（ListInstancesByTags 独立 API，不做）、跨区域聚合。

## 验收（摘要）

- 仅新增上述目录文件；离线单测全绿；bash validate 语法检查无 FAIL；
  只读性（仅 GET ListInstances）由守卫 + 代码路径双保证。
