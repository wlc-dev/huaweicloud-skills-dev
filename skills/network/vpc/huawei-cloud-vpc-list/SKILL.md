---
name: huawei-cloud-vpc-list
description: |
  1. List Huawei Cloud Virtual Private Cloud (VPC) instances in a tenant
     region through KooCLI (hcloud VPC ListVpcs — read-only GET
     /v1/{project_id}/vpcs), with an automatic fallback to the official
     huaweicloudsdkvpc v2 SDK when hcloud is not installed.
  2. Three output modes: full-field table (default, every returned field
     including id/name/cidr/status and the remaining VPC attributes), --json
     (raw response array), and --names-only (compact VPC name list).
  3. Supports --id / --enterprise-project-id filtering (both real server-side
     ListVpcs query parameters), region override, and automatic marker paging.
  4. Explicit error hints for empty VPC lists (「当前区域无虚拟私有云（VPC）」),
     403 / insufficient IAM permission (「无权限访问虚拟私有云（VPC）」),
     missing or invalid AK/SK credentials, missing project_id on the SDK
     fallback, and hcloud not installed.
  5. Built-in write-intent guard: any mutating intent (create / delete / update /
     associate / disassociate / attach / detach / release / change) or any
     operation other than ListVpcs is rejected before execution — this skill is
     strictly read-only.
  6. Triggers include: "list VPCs", "vpc list", "虚拟私有云列表", "查询 VPC",
     "查询虚拟私有云", "VPC 名称列表", "VPC 实例列表", "vpc inventory",
     "list vpcs", "华为云 VPC", "私有云列表".
  7. Offline unit tests (mocked hcloud subprocess) cover output modes, filters,
     marker paging, error scenarios, SDK fallback, and the write-intent guard.
tags: [huawei-cloud, vpc, network, readonly, koo-cli]
---

# Huawei Cloud Virtual Private Cloud (VPC) List

## Overview

Query the Virtual Private Cloud (VPC) list of a tenant through the KooCLI
VPC ListVpcs operation (hcloud VPC ListVpcs, official read-only
GET `/v1/{project_id}/vpcs`, verified
in the `huaweicloudsdkvpc` v2 client `_list_vpcs_http_info` metadata). The skill
is aimed at VPC inventory inspection, daily operations patrol, and as a
pre-query step for other skills that need a VPC `id` or its CIDR/status.

Architecture:

```text
agent → python3 scripts/list_vpc.py → hcloud VPC ListVpcs --cli-region=<region>
      → Huawei Cloud VPC OpenAPI (vpc.<region>.myhuaweicloud.com) → parsed JSON → table / --json / --names-only

(hcloud binary missing) → fallback: huaweicloudsdkvpc v2 VpcClient.list_vpcs
```

Key properties:

- **Read-only by design** — the only API ever invoked is `ListVpcs` (GET). A
  write-intent guard scans user arguments and validates the operation name;
  mutating intents (create / delete / update / associate / disassociate /
  attach / detach / release / change) are rejected with an explicit message
  before any command runs.
- **CLI first, SDK fallback** — KooCLI is the primary execution path; when the
  KooCLI binary is absent, the script falls back to the official
  `huaweicloudsdkvpc` v2 SDK (`list_vpcs`). Credentials are always read by the
  CLI profile / SDK environment — never handled by the script.
- **Full-field table output** — the default table renders the union of all
  fields returned by ListVpcs, with the nested `routes` array compacted into a
  single JSON column.
- **Offline-testable** — every code path (marker paging, filters, error
  classification, guard, SDK fallback) is covered by unit tests that mock the
  hcloud subprocess.

Out of scope: every mutating VPC action (create / update / delete a VPC, subnet,
security group, route table, port or flow log; associate / disassociate a
resource; VPC peering accept/reject). Those require a dedicated write-capable
skill and explicit user confirmation.

**Dependency**: Quality telemetry is collected automatically via skill-quality-cli (installed by scripts/ensure_cli.sh if absent).

## Prerequisites

1. **KooCLI (`hcloud`) installed** — see
   [references/cli-installation-guide.md](references/cli-installation-guide.md).
   Alternative: `pip install huaweicloudsdkvpc` to enable the SDK fallback path.
2. **Active credential profile** — configure credentials out-of-band
   (run the KooCLI configure command in your terminal, or set credential
   environment variables).
   Never paste AK/SK into chat; the script never reads, echoes, or stores
   secrets itself — authentication is delegated entirely to the hcloud profile
   / SDK environment.
3. **project_id (SDK fallback only)** — the VPC REST path is
   `/v1/{project_id}/vpcs`; when falling back to the SDK, supply the project id
   via `--project-id` or the `HUAWEICLOUD_SDK_PROJECT_ID` / `HUAWEI_PROJECT_ID`
   environment variables. The KooCLI path resolves it from the profile
   automatically.
4. **IAM permission** — read-only `vpc:vpcs:list`; least-privilege policy in
   [references/iam-policies.md](references/iam-policies.md).
5. **Python 3.8+** (standard library only — argparse / json / subprocess).
6. **Outbound HTTPS** access to `vpc.cn-north-4.myhuaweicloud.com`.
- **skill-quality-cli** — ensured by bash scripts/ensure_cli.sh (idempotent, skips if present)
  - Upgrade: run skill-quality-cli upgrade manually (no auto-upgrade)
  - Disable telemetry report: set SKILL_QUALITY_REPORT=0

## Workflow

1. **Confirm the target region** (default `cn-north-4`).
2. **Confirm KooCLI readiness** (optional, read-only) by listing the active
   credential profile.
3. **Run the list script** with the desired output mode and filters.
4. **Read the result** — table for humans, `--json` for downstream tooling,
   `--names-only` for a compact inventory.
5. **Handle the empty / error cases** per the Edge Cases table below (the
   script prints an explicit hint for empty region, 403, and missing AK/SK).

## Core Commands

> **⚠️ Mandatory: every hcloud command in this skill MUST be wrapped with skill-quality-cli run --skill-name huawei-cloud-vpc-list -- ** — bare hcloud calls are strictly forbidden.**

```bash
# Full-field table (default)
python3 scripts/list_vpc.py --region cn-north-4

# Raw JSON of every returned field
python3 scripts/list_vpc.py --json

# Compact VPC name list only
python3 scripts/list_vpc.py --names-only

# Filter by exact VPC id / enterprise project id (server-side query parameters)
python3 scripts/list_vpc.py --id vpc-0001
python3 scripts/list_vpc.py --enterprise-project-id 0

# Combine filters
python3 scripts/list_vpc.py --region cn-north-4 --enterprise-project-id 0 --names-only
```

Equivalent direct KooCLI command (the script wraps exactly this call, with
marker paging):

```bash
skill-quality-cli run --skill-name huawei-cloud-vpc-list -- hcloud VPC ListVpcs --cli-region=cn-north-4 --limit=100

# Read-only credential readiness check (also wrapped)
skill-quality-cli run --skill-name huawei-cloud-vpc-list -- hcloud configure list
```

## Parameter Confirmation

| Parameter | Required | Description | Example |
| ----------- | ---------- | ------------- | --------- |
| `--region` / `-r` | No | Huawei Cloud region (default `cn-north-4`) | `cn-south-1` |
| `--json` | No | Output the raw instance array as JSON | — |
| `--names-only` | No | Output the VPC name list only | — |
| `--id` | No | Filter by exact VPC ID — real server-side ListVpcs query parameter | `vpc-0001` |
| `--enterprise-project-id` | No | Filter by enterprise project ID — real server-side query parameter (`0` = default project) | `0` |
| `--page-size` | No | Page size for ListVpcs (default 100, range 0–2000) | `100` |
| `--project-id` | No | Project ID (needed by the SDK fallback path for `/v1/{project_id}/...`) | `05f...` |
| `--operation` | No | hcloud VPC operation name; only `ListVpcs` is allowed | `ListVpcs` |

Output-mode precedence: `--names-only` → `--json` → table (default).

## Write-Intent Guard

- The script scans all user arguments plus the `--operation` value for mutating
  vocabulary (`create`, `delete`, `update`, `modify`, `associate`,
  `disassociate`, `attach`, `detach`, `bind`, `unbind`, `release`, `change`,
  `restart`, and VPC operation names such as `CreateVpc`, `DeleteVpc`,
  `UpdateVpc`, `CreateSubnet`, `DeleteSubnet`, `CreateSecurityGroup`,
  `CreateVpcPeering`).
- Any hit raises `GuardError`, prints `[错误] 检测到写操作意图 ... 已被守卫拦截`, and
  exits with code 1 **before** a single hcloud command is executed.
- Only the VPC ListVpcs GET call (via KooCLI, or the SDK `list_vpcs` call in the
  fallback path) is ever constructed by `build_command()`; there is no code
  path that can issue a mutating VPC API call.

## KooCLI Command Format Standard

```text
hcloud <Service> <Operation> --cli-region=<region> [--key=value ...]
```

- **Service name** — exact KooCLI title-case service name: `VPC`.
- **Operation name** — PascalCase: `ListVpcs`.
- **Region parameter** — `--cli-region=<value>`, e.g. `--cli-region=cn-north-4`
  (required for every concrete VPC call).
- **Simple parameter** — `--key=value`, e.g. `--limit=100`, `--marker=<token>`,
  `--id=<vpc-id>`, `--enterprise_project_id=0`. Both filters are real
  server-side ListVpcs parameters (verified against the `huaweicloudsdkvpc` v2
  `ListVpcsRequest` model).
- **Paging** — `--limit` + `--marker`; the marker is the `next_marker` returned
  in the response `page_info` (the marker is a VPC resource id).
- **REST path (official SDK `_http_info`)** —
  `GET /v1/{project_id}/vpcs` (`huaweicloudsdkvpc` v2 `_list_vpcs_http_info`);
  the project_id is resolved by KooCLI from the credential profile.

## Error Handling

| Scenario | Behavior |
| ---------- | --------- |
| Empty VPC list | Exit 0, prints `当前区域（<x>）无虚拟私有云（VPC）` (+ active filters) |
| 403 / insufficient IAM permission | Exit 1, `无权限访问虚拟私有云（VPC），请检查 IAM 权限` hint |
| Missing / invalid AK-SK | Exit 1, explicit hint to configure hcloud credentials out-of-band (never in chat) |
| Missing project_id (SDK fallback) | Exit 1, hint to pass `--project-id` or set the project-id env var |
| hcloud not installed | Exit 1 after SDK fallback also unavailable, hint to install KooCLI or `pip install huaweicloudsdkvpc` |
| Network / API failure | Exit 1 with the hcloud stderr excerpt |
| KooCLI usage error (`[USE_ERROR] ...`, even with exit code 0) | Exit 1, explicit 「hcloud 参数错误」hint pointing to the KooCLI VPC ListVpcs `--help` |
| Write intent detected | Exit 1, `GuardError` message, no command executed |

Exit codes: `0` success / empty region; `1` config, auth, guard, or API error.

## Edge Cases

| Scenario | Handling |
| ---------- | --------- |
| Non-`OK` VPCs | Reported with their state (`CREATING`), not treated as failure |
| `--id` / `--enterprise-project-id` filters | Forwarded as real server-side query parameters (verified API params) |
| Large VPC count | Automatic `marker` paging (`next_marker` aware, max 100 pages) |
| Extra response fields | Table columns are built from the union of returned fields — new fields appear automatically |
| Field missing on a VPC | Rendered as `-` in the table |
| Nested `routes` array | Compacted into a single JSON column for the table |
| Non-JSON hcloud output | `ApiError` with the raw excerpt (first 200 chars) |
| hcloud absent, SDK installed | Transparent fallback to `huaweicloudsdkvpc` list_vpcs, same output modes |
| User asks to create/delete/associate a VPC | Out of scope — blocked by the write-intent guard; a write-capable skill with explicit user confirmation is required |

## Testing

Offline unit tests with a mocked hcloud subprocess (no credentials, no network):

```bash
cd skills/network/vpc/huawei-cloud-vpc-list
python3 -m unittest discover -s tests -v
```

Coverage: write-intent guard (read passes / create / delete / update /
associate / release / change / normalized variants / operation whitelist),
command construction (filters forwarded server-side; marker never sent on the
first page), JSON extraction, failure classification (missing AK/SK, 403,
generic, `[USE_ERROR]` with rc=0), marker paging (next_marker / full page /
empty), SDK fallback (success, missing credentials, missing project id, and
unavailable; request construction matches the real `ListVpcsRequest`
signature), rendering (table with routes / names / fallbacks), and all main()
output modes including empty, filter, and error paths.

## Reference Documents

| Document | Content |
| ---------- | --------- |
| [references/iam-policies.md](references/iam-policies.md) | Least-privilege read-only IAM policy |
| [references/cli-installation-guide.md](references/cli-installation-guide.md) | KooCLI installation, credential configuration and skill-quality-cli |
| [references/verification-method.md](references/verification-method.md) | How the skill and its tests were verified |
| [references/dataflow-diagram.md](references/dataflow-diagram.md) | Mermaid data flow diagram |
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Acceptance criteria checklist |