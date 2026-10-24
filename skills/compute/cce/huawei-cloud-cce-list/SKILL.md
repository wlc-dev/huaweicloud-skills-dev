---
name: huawei-cloud-cce-list
description: |
  1. List Huawei Cloud Cloud Container Engine (CCE) clusters in a tenant region
     through KooCLI (hcloud CCE ListClusters — read-only GET
     /api/v3/projects/{project_id}/clusters), with an automatic fallback to the
     official huaweicloudsdkcce v3 SDK when hcloud is not installed.
  2. Three output modes: full-field table (default, every returned field including
     名称/UID/别名/状态/类型/规格/版本/类别/计费模式), --json (raw response array),
     and --names-only (compact cluster-name list).
  3. Supports --name / --id filtering (applied client-side, because the v3
     ListClusters API exposes no name/id query parameters), and a region override.
  4. Explicit error hints for empty cluster lists (「当前区域无云容器引擎（CCE）集群」),
     403 / insufficient IAM permission (「无权限访问云容器引擎（CCE）」), missing or
     invalid AK/SK credentials, and hcloud not installed.
  5. Built-in write-intent guard: any mutating intent (create / delete / update /
     upgrade / resize / hibernate / wakeup / add-node / remove-node / ...) or any
     operation other than ListClusters is rejected before execution — this skill is
     strictly read-only.
  6. Triggers include: "list CCE clusters", "cce cluster list", "云容器引擎集群列表",
     "查询CCE集群", "CCE 集群清单", "list clusters", "cloud container engine
     inventory", "华为云CCE".
  7. Offline unit tests (mocked hcloud subprocess) cover output modes, filters,
     error scenarios, SDK fallback, and the write-intent guard.
tags: [huawei-cloud, cce, compute, readonly, koo-cli]
---

# Huawei Cloud CCE (Cloud Container Engine) Cluster List

## Overview

Query the Cloud Container Engine (CCE) cluster list of a tenant through KooCLI
`hcloud CCE ListClusters` (official read-only GET
`/api/v3/projects/{project_id}/clusters`, verified in the `huaweicloudsdkcce` v3
client `_list_clusters_http_info` metadata). The skill is aimed at CCE inventory
inspection, daily operations patrol, and as a pre-query step for other CCE skills
that need a cluster `id` (metadata.uid).

Architecture:

```text
agent → python3 scripts/list_cce.py → hcloud CCE ListClusters --cli-region=<region>
      → Huawei Cloud CCE OpenAPI (project-scoped endpoint) → parsed JSON → table / --json / --names-only

(hcloud binary missing) → fallback: huaweicloudsdkcce v3 CceClient.list_clusters
```

Key properties:

- **Read-only by design** — the only API ever invoked is `ListClusters` (GET). A
  write-intent guard scans user arguments and validates the operation name;
  mutating intents (create / delete / update / upgrade / resize / hibernate /
  wakeup / add-node / remove-node ...) are rejected with an explicit message
  before any command runs.
- **CLI first, SDK fallback** — KooCLI is the primary execution path; when the
  KooCLI binary is absent, the script falls back to the official
  `huaweicloudsdkcce` v3 SDK (`list_clusters`). Credentials are always read by
  the CLI profile / SDK environment — never handled by the script.
- **Full-field table output** — the default table renders the union of the
  flattened cluster fields (name / uid / alias / phase / type / flavor / version
  / category / billing mode / description / creation time / labels).
- **Offline-testable** — every code path (filters, error classification, guard,
  SDK fallback) is covered by unit tests that mock the hcloud subprocess.

Out of scope: every mutating CCE action (create / update / delete a cluster,
node-pool resize, cluster upgrade, hibernation/wakeup, add-on management). Those
require a dedicated write-capable skill and explicit user confirmation.

## Prerequisites

1. **KooCLI (`hcloud`) installed** — see
   [references/cli-installation-guide.md](references/cli-installation-guide.md).
   Alternative: `pip install huaweicloudsdkcce` to enable the SDK fallback path.
2. **Active credential profile** — configure credentials out-of-band
   (run the KooCLI configure command in your terminal, or set credential
   environment variables).
   Never paste AK/SK into chat; the script never reads, echoes, or stores
   secrets itself — authentication is delegated entirely to the hcloud profile
   / SDK environment.
3. **IAM permission** — read-only `cce:cluster:list`; least-privilege policy in
   [references/iam-policies.md](references/iam-policies.md).
4. **Python 3.8+** (standard library only — argparse / json / subprocess).
5. **Outbound HTTPS** access to the region CCE endpoint
   (`cce.<region>.myhuaweicloud.com`).

## Workflow

1. **Confirm the target region** (default `cn-north-4`); the CCE cluster list is
   project-scoped and region-scoped.
2. **Confirm KooCLI readiness** (optional, read-only) by listing the active
   credential profile.
3. **Run the list script** with the desired output mode and filters.
4. **Read the result** — table for humans, `--json` for downstream tooling,
   `--names-only` for a compact inventory.
5. **Handle the empty / error cases** per the Edge Cases table below (the
   script prints an explicit hint for empty region, 403, and missing AK/SK).

## Core Commands

> **⚠️ Mandatory: every hcloud command in this skill MUST be wrapped with `skill-quality-cli run --skill-name huawei-cloud-cce-list -- ` — bare hcloud calls are strictly forbidden.**

```bash
# Full-field table (default)
python3 scripts/list_cce.py --region cn-north-4

# Raw JSON of every returned field
python3 scripts/list_cce.py --json

# Compact cluster-name list only
python3 scripts/list_cce.py --names-only

# Filter by cluster name / id (client-side)
python3 scripts/list_cce.py --name demo
python3 scripts/list_cce.py --id uid-0001

# Combine filters
python3 scripts/list_cce.py --region cn-north-4 --name demo --names-only

# Equivalent direct KooCLI command (the script wraps exactly this call)
skill-quality-cli run --skill-name huawei-cloud-cce-list -- hcloud CCE ListClusters --cli-region=cn-north-4
```

## Parameter Confirmation

| Parameter | Required | Description | Example |
| ----------- | ---------- | ------------- | --------- |
| `--region` / `-r` | No | Huawei Cloud region (default `cn-north-4`) | `cn-south-1` |
| `--json` | No | Output the raw cluster array as JSON | — |
| `--names-only` | No | Output cluster names only | — |
| `--name` | No | Filter by cluster name (client-side, case-insensitive substring; the v3 API has no name query parameter) | `cce-demo-01` |
| `--id` | No | Filter by exact cluster UID (client-side, case-insensitive exact; `metadata.uid`) | `uid-0001` |
| `--project-id` | No | Project id, only needed for the SDK fallback when AK/SK cannot resolve it via IAM | `06a3...` |
| `--operation` | No | hcloud CCE operation name; only `ListClusters` is allowed | `ListClusters` |

Output-mode precedence: `--names-only` → `--json` → table (default).

## Write-Intent Guard

- The script scans all user arguments plus the `--operation` value for mutating
  vocabulary (`create`, `delete`, `update`, `modify`, `upgrade`, `resize`,
  `hibernate`, `wakeup`, `scale`, `add`, `remove`, `rollback`, `reset`,
  `restart`, and CCE operation names such as `CreateCluster`,
  `DeleteCluster`, `UpdateCluster`, `UpgradeCluster`).
- Any hit raises `GuardError`, prints `[错误] 检测到写操作意图 ... 已被守卫拦截`, and
  exits with code 1 **before** a single hcloud command is executed.
- Only `hcloud CCE ListClusters` (GET) — or the SDK `list_clusters` call in the
  fallback path — is ever constructed by `build_command()`; there is no code path
  that can issue a mutating CCE API call.

## KooCLI Command Format Standard

```text
hcloud <Service> <Operation> --cli-region=<region> [--key=value ...]
```

- **Service name** — exact KooCLI title-case service name: `CCE`.
- **Operation name** — PascalCase: `ListClusters`.
- **Region parameter** — `--cli-region=<value>`, e.g. `--cli-region=cn-north-4`
  (required for every concrete CCE call).
- **REST path (official SDK `_http_info`)** —
  `GET /api/v3/projects/{project_id}/clusters` (`huaweicloudsdkcce` v3
  `_list_clusters_http_info`); the project_id is resolved by KooCLI from the
  credential profile.
- **No name/id/paging parameters** — the v3 ListClusters request accepts only
  `detail` / `status` / `type` / `version`; `--name` / `--id` are applied
  client-side by the script.

## Error Handling

| Scenario | Behavior |
| ---------- | --------- |
| Empty cluster list | Exit 0, prints `当前区域（<x>）无云容器引擎（CCE）集群` (+ active filters) |
| 403 / insufficient IAM permission | Exit 1, `无权限访问云容器引擎（CCE），请检查 IAM 权限` hint |
| Missing / invalid AK-SK | Exit 1, explicit hint to configure hcloud credentials out-of-band (never in chat) |
| hcloud not installed | Exit 1 after SDK fallback also unavailable, hint to install KooCLI or `pip install huaweicloudsdkcce` |
| Network / API failure | Exit 1 with the hcloud stderr excerpt |
| KooCLI usage error (`[USE_ERROR] ...`, even with exit code 0) | Exit 1, explicit `hcloud 参数错误` hint pointing to `hcloud CCE ListClusters --help` |
| Write intent detected | Exit 1, `GuardError` message, no command executed |

Exit codes: `0` success / empty region; `1` config, auth, guard, or API error.

## Edge Cases

| Scenario | Handling |
| ---------- | --------- |
| Non-`Available` clusters | Reported with their phase (e.g. `Creating`), not treated as failure |
| `--name` / `--id` filters | Applied client-side (substring name / exact uid) — the v3 API has no such query parameters |
| Extra response fields | Table columns are built from the union of flattened fields — new fields appear automatically |
| Field missing on a cluster | Rendered as `-` in the table |
| Nested `labels` | Flattened into `key=value,...` for the table |
| Non-JSON hcloud output | `ApiError` with the raw excerpt (first 200 chars) |
| hcloud absent, SDK installed | Transparent fallback to `huaweicloudsdkcce` list_clusters, same output modes |
| User asks to create/delete/resize a cluster | Out of scope — blocked by the write-intent guard; a write-capable skill with explicit user confirmation is required |

## Testing

Offline unit tests with a mocked hcloud subprocess (no credentials, no network):

```bash
python3 -m unittest discover -s tests -v
```

Coverage: write-intent guard (read passes / create / delete / upgrade / resize /
hibernate / add-node / normalized variants / operation whitelist), command
construction, JSON extraction, failure classification (missing AK/SK, 403,
generic, `[USE_ERROR]` with rc=0), client-side name/id filtering, SDK fallback
(imports resolve, request signature, env-credential wiring, project id), and
rendering (table / names / fallbacks) across all main() output modes.

## Reference Documents

| Document | Content |
| ---------- | --------- |
| [references/iam-policies.md](references/iam-policies.md) | Least-privilege read-only IAM policy |
| [references/cli-installation-guide.md](references/cli-installation-guide.md) | KooCLI installation and credential configuration |
| [references/verification-method.md](references/verification-method.md) | How the skill and its tests were verified |
| [references/dataflow-diagram.md](references/dataflow-diagram.md) | Mermaid data flow diagram |
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Acceptance criteria checklist |