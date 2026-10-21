---
name: huawei-cloud-dcs-list
description: |
  1. List Huawei Cloud DCS (Distributed Cache Service, Redis / Memcached)
     instances in a tenant region through KooCLI (hcloud DCS ListInstances —
     read-only GET /v2/{project_id}/instances), with an automatic fallback to
     the official huaweicloudsdkdcs v2 SDK when hcloud is not installed.
  2. Default output is the compact instance-name list (名称列表, also available
     via --names-only); --table renders the full-field table
     (名称/ID/引擎/版本/容量/规格/状态/连接地址/端口/可用区), and --json outputs the
     raw response array.
  3. Supports --name (server-side fuzzy query, plus --name-equal exact match),
     --instance-id / --ip / --status / --tags filtering (all real server-side
     ListInstances query parameters), region override, and automatic
     limit/offset paging.
  4. Explicit error hints for empty instance lists (「当前区域无 DCS 实例」),
     403 / insufficient IAM permission (「无权限访问分布式缓存服务（DCS）」), missing
     or invalid AK/SK credentials, missing project_id on the SDK fallback, and
     hcloud not installed.
  5. Built-in write-intent guard: any mutating intent (create / delete /
     update / resize / restart / flush / clear / restore / backup / freeze) or
     any operation other than ListInstances is rejected before execution —
     this skill is strictly read-only.
  6. Triggers include: "list DCS instances", "DCS instance list",
     "查询 DCS 实例列表", "DCS 实例列表", "Redis 实例列表", "缓存实例列表",
     "查询缓存实例", "DCS inventory", "list cache instances", "华为云 DCS 列表".
  7. Offline unit tests (mocked hcloud subprocess) cover output modes, filters,
     paging, error scenarios, SDK fallback, and the write-intent guard.
tags: [huawei-cloud, dcs, database, readonly, koo-cli]
---

# Huawei Cloud DCS Instance List

## Overview

Query the DCS (Distributed Cache Service, Redis / Memcached) instance list of
a tenant region through KooCLI `hcloud DCS ListInstances` (official read-only
`GET /v2/{project_id}/instances`, verified in the `huaweicloudsdkdcs` v2
client `_list_instances_http_info` metadata — `resource_path:
"/v2/{project_id}/instances"`, `method: "GET"`). The skill is aimed at DCS
inventory inspection, daily operations patrol, and as a pre-query step for
other DCS skills that need an `instance_id`.

Architecture:

```text
agent → python3 scripts/list_dcs.py → hcloud DCS ListInstances --cli-region=<region>
      → Huawei Cloud DCS OpenAPI (dcs.<region>.myhuaweicloud.com) → parsed JSON → names list / table / --json

(hcloud binary missing) → fallback: huaweicloudsdkdcs v2 DcsClient.list_instances
```

Key properties:

- **Read-only by design** — the only API ever invoked is `ListInstances`
  (GET). A write-intent guard scans user arguments and validates the
  operation name; mutating intents (create / delete / update / resize /
  restart / flush / clear / restore / backup / freeze ...) are rejected with
  an explicit message before any command runs.
- **CLI first, SDK fallback** — KooCLI is the primary execution path; when
  the hcloud binary is absent, the script falls back to the official
  `huaweicloudsdkdcs` v2 SDK (`DcsClient.list_instances`). Credentials are
  always read by the CLI profile / whitelisted SDK environment variables —
  never handled by the script.
- **Name list by default** — the default output mode is the compact
  instance-name list (「DCS 实例名称列表」); `--table` renders the full-field
  table and `--json` the raw response array.
- **Server-side filters & automatic paging** — `--name` / `--instance_id` /
  `--ip` / `--status` / `--tags` are real ListInstances query parameters
  (verified against `hcloud DCS ListInstances --help`); paging uses
  `--limit` (1~1000) + `--offset` and is fetched automatically until
  `instance_num` is reached.
- **Offline-testable** — every code path (filters, paging, error
  classification, guard, SDK fallback) is covered by unit tests that mock
  the hcloud subprocess.

Out of scope: every mutating DCS action (create / delete / resize / restart /
flush / clear data / restore backup / reset password / upgrade / IP exchange).
Those require a dedicated write-capable skill and explicit user confirmation.

## Prerequisites

1. **KooCLI (`hcloud`) installed** — see
   [references/cli-installation-guide.md](references/cli-installation-guide.md).
   Alternative: `pip install huaweicloudsdkdcs` to enable the SDK fallback path.
2. **Active credential profile** — configure credentials out-of-band
   (run the KooCLI configure command in your terminal, or set credential
   environment variables). Never paste AK/SK into chat; the script never
   reads, echoes, or stores secrets itself — authentication is delegated
   entirely to the hcloud profile / SDK environment.
3. **project_id (SDK fallback only)** — the DCS REST path is
   `/v2/{project_id}/instances`; when falling back to the SDK, supply the
   project id via `--project-id` or the `HUAWEICLOUD_SDK_PROJECT_ID` /
   `HUAWEI_PROJECT_ID` environment variables. The KooCLI path resolves it
   from the profile automatically.
4. **IAM permission** — read-only `dcs:instance:list`; least-privilege
   policy in [references/iam-policies.md](references/iam-policies.md).
5. **Python 3.8+** (standard library only — argparse / json / subprocess).
6. **Outbound HTTPS** access to `dcs.cn-north-4.myhuaweicloud.com`.

## Workflow

1. **Confirm the target region** (default `cn-north-4`).
2. **Confirm KooCLI readiness** (optional, read-only) by listing the active
   credential profile.
3. **Run the list script** with the desired output mode and filters.
4. **Read the result** — name list (default) for a compact inventory, table
   for humans, `--json` for downstream tooling.
5. **Handle the empty / error cases** per the Edge Cases table below (the
   script prints an explicit hint for empty region, 403, and missing AK/SK).

## Core Commands

```bash
# Compact instance-name list (default — the core ask of this skill)
python3 scripts/list_dcs.py --region cn-north-4
python3 scripts/list_dcs.py --names-only

# Full-field table (名称/ID/引擎/容量/状态/连接地址/端口 etc.)
python3 scripts/list_dcs.py --table

# Raw JSON of every returned field
python3 scripts/list_dcs.py --json

# Filter by instance name (server-side fuzzy query parameter)
python3 scripts/list_dcs.py --name cache-demo
python3 scripts/list_dcs.py --name-equal --name cache-demo-01   # exact match

# Filter by exact instance ID / connection IP / status / tags
python3 scripts/list_dcs.py --instance-id 55f47f3d-...
python3 scripts/list_dcs.py --ip 192.168.0.10
python3 scripts/list_dcs.py --status RUNNING
python3 scripts/list_dcs.py --tags env=prod

# Automatic paging; page size is tunable (1~1000, default 100)
python3 scripts/list_dcs.py --page-size 500

# Combine filters
python3 scripts/list_dcs.py --region cn-south-1 --status RUNNING --names-only
```

Equivalent direct KooCLI command (the script wraps exactly this call, with
automatic offset paging):

```bash
hcloud DCS ListInstances --cli-region=cn-north-4 --limit=100 --offset=0
hcloud DCS ListInstances --cli-region=cn-north-4 --name=cache-demo --status=RUNNING
```

## Parameter Confirmation

| Parameter | Required | Description | Example |
| ----------- | ---------- | ------------- | --------- |
| `--region` / `-r` | No | Huawei Cloud region (default `cn-north-4`) | `cn-south-1` |
| `--names-only` | No | Output instance names only — **this is also the default mode** | — |
| `--table` | No | Output the full-field table (名称/ID/引擎/版本/容量/规格/状态/连接地址/端口) | — |
| `--json` | No | Output the raw instance array as JSON | — |
| `--name` | No | Filter by instance name — real server-side query parameter (fuzzy) | `cache-demo` |
| `--name-equal` | No | Exact-match switch: drops the fuzzy server param and filters locally, case-insensitive | used with `--name` |
| `--instance-id` | No | Filter by exact instance ID — real server-side query parameter | `55f47f3d-...` |
| `--ip` | No | Filter by connection IP address — real server-side query parameter | `192.168.0.10` |
| `--status` | No | Filter by instance state — real server-side query parameter (`RUNNING` / `ERROR` / ...) | `RUNNING` |
| `--tags` | No | Filter by instance tags — real server-side query parameter (`key1=value1,key2=value2`) | `env=prod` |
| `--page-size` | No | Page size for ListInstances (default 100, range 1–1000; pages are fetched automatically) | `500` |
| `--project-id` | No | Project ID (needed by the SDK fallback path for `/v2/{project_id}/instances`) | `05f...` |
| `--operation` | No | hcloud DCS operation name; only `ListInstances` is allowed | `ListInstances` |

Output-mode precedence: `--names-only` (default) → `--json` → `--table`.
Without any mode flag the script prints the instance-name list; `--json`
wins over the default, and `--table` is required for the full-field table.

## Write-Intent Guard

- The script scans all user arguments plus the `--operation` value for
  mutating vocabulary (`create`, `delete`, `update`, `modify`, `resize`,
  `restart`, `reboot`, `flush`, `clear`, `restore`, `backup`, `freeze`,
  `unfreeze`, `release`, and DCS operation names such as `CreateInstance`,
  `BatchDeleteInstances`, `DeleteSingleInstance`, `ResizeInstance`,
  `RestartOrFlushInstances`, `UpdateInstance`, `ResetInstancePassword`).
- Any hit raises `GuardError`, prints
  `[错误] 检测到写操作意图 ... 已被守卫拦截`, and exits with code 1 **before**
  a single hcloud command is executed.
- Only `hcloud DCS ListInstances` (GET) — or the SDK `list_instances` call
  in the fallback path — is ever constructed by `build_command()`; there is
  no code path that can issue a mutating DCS API call.

## KooCLI Command Format Standard

```text
hcloud <Service> <Operation> --cli-region=<region> [--key=value ...]
```

- **Service name** — exact KooCLI title-case service name: `DCS`.
- **Operation name** — PascalCase: `ListInstances`.
- **Region parameter** — `--cli-region=<value>`, e.g. `--cli-region=cn-north-4`
  (required for every concrete DCS call).
- **Simple parameter** — `--key=value`, e.g. `--name=cache-demo`,
  `--instance_id=<id>`, `--ip=192.168.0.10`, `--status=RUNNING`,
  `--tags=env=prod`. All of these are real server-side ListInstances query
  parameters (verified against the `huaweicloudsdkdcs` v2
  `ListInstancesRequest` model).
- **Paging** — `--limit` (integer, 1~1000; KooCLI defaults to 10 per page
  when unset) + `--offset` (integer, ≥ 0); the script fetches pages
  automatically until the response `instance_num` total is reached.
- **REST path (official SDK `_http_info`)** —
  `GET /v2/{project_id}/instances` (`huaweicloudsdkdcs` v2
  `_list_instances_http_info`); the project_id is resolved by KooCLI from
  the credential profile.

## Error Handling

| Scenario | Behavior |
| ---------- | --------- |
| Empty instance list | Exit 0, prints `当前区域（<x>）无 DCS 实例` (+ active filters) |
| 403 / insufficient IAM permission | Exit 1, `无权限访问分布式缓存服务（DCS），请检查 IAM 权限` hint |
| Missing / invalid AK-SK | Exit 1, explicit hint to configure hcloud credentials out-of-band (never in chat) |
| Missing project_id (SDK fallback) | Exit 1, hint to pass `--project-id` or set the project-id env var |
| hcloud not installed | Exit 1 after SDK fallback also unavailable, hint to install KooCLI or `pip install huaweicloudsdkdcs` |
| Network / API failure | Exit 1 with the hcloud stderr excerpt |
| KooCLI usage error (`[USE_ERROR] ...`, even with exit code 0) | Exit 1, explicit `hcloud 参数错误` hint pointing to `hcloud DCS ListInstances --help` |
| `--page-size` out of range (not 1~1000) | Exit 1, explicit range error before any call |
| Write intent detected | Exit 1, `GuardError` message, no command executed |

Exit codes: `0` success / empty region; `1` config, auth, guard, or API error.

## Edge Cases

| Scenario | Handling |
| ---------- | --------- |
| Non-`RUNNING` instances (ERROR / FROZEN / ...) | Reported with their state, not treated as failure |
| `--name` | Forwarded as the real fuzzy server-side query parameter; `--name-equal` switches to exact local matching (case-insensitive) |
| `--instance-id` / `--ip` / `--status` / `--tags` filters | Forwarded as real server-side query parameters (verified API params) |
| Large instance count | Automatic `limit`/`offset` paging driven by `instance_num` (max 100 pages) |
| Extra response fields | Table columns are built from the union of returned fields — new fields appear automatically |
| Field missing on an instance | Rendered as `-` in the table |
| `az_codes` / `tags` lists | Flattened into comma-joined cells for the table |
| Instance without a name | The name list falls back to `instance_id` |
| Non-JSON hcloud output | `ApiError` with the raw excerpt (first 200 chars) |
| hcloud absent, SDK installed | Transparent fallback to `huaweicloudsdkdcs` list_instances, same output modes |
| User asks to create/delete/resize/flush | Out of scope — blocked by the write-intent guard; a write-capable skill with explicit user confirmation is required |

## Testing

Offline unit tests with a mocked hcloud subprocess (no credentials, no
network):

```bash
python3 -m unittest discover -s tests -v
```

Coverage: write-intent guard (read passes / create / batch delete / resize /
restart / flush / clear / restore / backup / freeze / normalized variants /
operation whitelist), command construction (real server-side filters
forwarded; paging params; no write flags ever), JSON extraction, failure
classification (missing AK/SK, 403, generic, `[USE_ERROR]` with rc=0),
offset paging (instance_num-driven / full-page fallback / empty), SDK
fallback (env credentials, alternative prefixes, missing credentials,
missing project id, pagination, filters; request construction matches the
real `ListInstancesRequest` signature), rendering (table with
engine/capacity/status/ip/port/az fields / names / fallbacks), and all
main() output modes including default names list, empty, filter, exact-name
and error paths.

## Reference Documents

| Document | Content |
| ---------- | --------- |
| [references/iam-policies.md](references/iam-policies.md) | Least-privilege read-only IAM policy |
| [references/cli-installation-guide.md](references/cli-installation-guide.md) | KooCLI installation and credential configuration |
| [references/verification-method.md](references/verification-method.md) | How the skill and its tests were verified |
| [references/dataflow-diagram.md](references/dataflow-diagram.md) | Mermaid data flow diagram |
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Acceptance criteria checklist |
