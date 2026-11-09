---
name: huawei-cloud-css-cluster-list
description: |
  1. Inventory Huawei Cloud CSS (Cloud Search Service, Elasticsearch & OpenSearch)
     clusters in a tenant region through KooCLI — read-only only.
  2. Three GET APIs: `hcloud CSS ListClustersDetails` (GET /v1.0/{project_id}/clusters,
     supports --limit / --offset / --datastoreType), `hcloud CSS ShowClusterDetail`
     (GET /v1.0/{project_id}/clusters/{cluster_id}) and `hcloud CSS
     ShowClusterVolumeUsage` (GET /v1.0/{project_id}/clusters/{cluster_id}/volume).
  3. Output modes: compact cluster list (default: name / id / status), `--table`
     cluster view (id / name / status / engine / version / node spec / node count /
     storage GB / disk usage / VPC / subnet / security group / created / region),
     `--table --cluster-id <id>` node view (node id / name / type / spec / status /
     IP / AZ / disk usage / capacity / used), and `--json` raw response.
  4. Abnormal cluster status (anything other than `200`), disk usage >= 80% and
     abnormal nodes are highlighted in a separate section, never mixed with normal
     rows; `--status abnormal` lists only abnormal clusters.
  5. Filters: `--name` (`--fuzzy` for substring), `--cluster-id` drill-down,
     `--status` (client-side), `--datastore-type` (elasticsearch / opensearch),
     `--region` (default cn-north-4). `--limit` 1..100 with automatic paging.
  6. SDK fallback: when hcloud is missing, the script uses the official
     `huaweicloudsdkcss` v1 SDK with the same read-only semantics.
  7. Strict write-intent guard: create / delete / restart / reboot / update / scale /
     shrink / snapshot intents are rejected before execution (exit 1).
  8. Explicit, actionable errors for empty results, 403 / IAM denial, missing
     credentials, `[USE_ERROR]` parameter problems and non-existent clusters.
  9. Triggers include: "list CSS clusters", "CSS cluster list", "CSS 集群列表",
     "查询云搜索服务集群", "Elasticsearch cluster inventory", "OpenSearch cluster list",
     "CSS 容量巡检", "CSS 节点异常排查", "huawei-cloud-css-cluster-list",
     "list cloud search service clusters".
tags: [huawei-cloud, css, elasticsearch, opensearch, readonly]
---

# Huawei Cloud CSS Cluster List

## Overview

Query the CSS (Cloud Search Service) clusters of a tenant region through KooCLI
`hcloud CSS ListClustersDetails` and drill into one cluster with
`ShowClusterDetail` + `ShowClusterVolumeUsage`. The skill is aimed at inventory
inspection, daily patrol, capacity alerts and node troubleshooting, and as a
pre-query step for downstream skills that need a `cluster_id`.

Architecture:

```text
agent → python3 scripts/list_css_clusters.py
      → hcloud CSS ListClustersDetails --cli-region=<region> --limit --offset [--datastoreType]
      → (drill-down) hcloud CSS ShowClusterDetail / ShowClusterVolumeUsage --cli-region=<region> --cluster_id=<id>
      → Huawei Cloud CSS OpenAPI (regional endpoint) → parsed JSON → table / --json
```

Key properties:

- **Read-only by design** — only three GET operations are ever constructed:
  `ListClustersDetails`, `ShowClusterDetail`, `ShowClusterVolumeUsage`. A
  write-intent guard scans arguments and the operation/action name; mutating
  intent (create / delete / restart / reboot / update / scale / shrink /
  snapshot ...) is rejected with an explicit message before any command runs.
- **Abnormal-first reporting** — clusters whose status is not `200`, clusters
  whose disk usage is at least 80%, and nodes whose status is not `200` are
  listed in dedicated highlighted sections instead of being mixed with normal
  rows.
- **Offline-testable** — paging, filtering, error classification, rendering and
  the write-intent guard are covered by unit tests that mock the hcloud
  subprocess and inject a fake SDK module.

Out of scope: every mutating CSS action (create / delete / restart / reboot /
scale / shrink / snapshot / config change). Those require a write-capable skill
and explicit user confirmation.

## Prerequisites

1. **KooCLI (`hcloud`) installed** — see
   [references/cli-installation-guide.md](references/cli-installation-guide.md).
2. **Active credential profile** — configure credentials out-of-band
   (`hcloud configure` in your terminal, or credential environment variables).
   Never paste AK/SK into chat; the script never reads, echoes or stores secrets
   itself — authentication is delegated to the hcloud profile (or, on the SDK
   fallback path, to whitelisted AK/SK environment variables).
3. **IAM permission** — read-only `css:cluster:list` and `css:cluster:get`;
   least-privilege policy in [references/iam-policies.md](references/iam-policies.md).
4. **Python 3.8+** (standard library only for the CLI path; the SDK fallback
   needs `huaweicloudsdkcore` + `huaweicloudsdkcss`, installed via
   `python3 scripts/ensure_env.py` if missing).
5. **Outbound HTTPS** access to `*.myhuaweicloud.com`.

## Workflow

1. **Confirm the target region** (default `cn-north-4`); every CSS call is
   region-scoped.
2. **Confirm hcloud readiness** (optional, read-only): `hcloud configure list`.
3. **Run the inventory** — default compact list, or `--table` for the full
   cluster view, or `--table --cluster-id <id>` for the node view.
4. **Read the result** — normal rows first, then the highlighted abnormal
   sections; `--json` for downstream tooling.
5. **Handle empty / error cases** per the Edge Cases table (empty region, 403,
   missing AK/SK, unknown parameter, non-existent cluster).

## Core Commands

```bash
# Compact cluster list (default: name / id / status)
python3 scripts/list_css_clusters.py --region cn-north-4

# Full cluster view (all inventory fields + highlighted abnormal/capacity)
python3 scripts/list_css_clusters.py --region cn-north-4 --table

# Node view for one cluster (drill-down)
python3 scripts/list_css_clusters.py --region cn-north-4 --table --cluster-id <cluster-id>

# Raw JSON of the clusters / node response
python3 scripts/list_css_clusters.py --region cn-north-4 --json
python3 scripts/list_css_clusters.py --cluster-id <cluster-id> --json

# Filters
python3 scripts/list_css_clusters.py --name css-prod --fuzzy
python3 scripts/list_css_clusters.py --status abnormal
python3 scripts/list_css_clusters.py --datastore-type opensearch
```

Equivalent direct KooCLI calls (the script wraps exactly these, with paging):

```bash
hcloud CSS ListClustersDetails --cli-region=cn-north-4 --limit=10 --offset=1
hcloud CSS ShowClusterDetail --cli-region=cn-north-4 --cluster_id=<cluster-id>
hcloud CSS ShowClusterVolumeUsage --cli-region=cn-north-4 --cluster_id=<cluster-id>
```

## Parameter Confirmation

| Parameter | Required | Description | Example |
| ----------- | ---------- | ------------- | --------- |
| `--region` / `-r` | No | Huawei Cloud region (default `cn-north-4`) | `cn-south-1` |
| `--json` | No | Output the raw cluster array / node response as JSON | — |
| `--table` | No | Full-field cluster view (node view with `--cluster-id`) | — |
| `--name` | No | Filter by cluster name (exact by default) | `css-prod-01` |
| `--fuzzy` | No | Use substring (case-insensitive) matching for `--name` | — |
| `--cluster-id` | No | Drill into one cluster: detail + node list | `<cluster-id>` |
| `--status` | No | Client-side status filter (`200` / `100` / `303` / `abnormal` / `normal`, comma-separated) | `abnormal` |
| `--datastore-type` | No | Server-side engine filter (`elasticsearch` / `opensearch`) | `elasticsearch` |
| `--limit` | No | Page size, clamped to 1..100 (default 10); paging fetches everything | `50` |
| `--max-pages` | No | Defensive paging ceiling (default 200) | `50` |
| `--action` | No | Explicit read-only intent; only `list` / `detail` / `volume` are allowed | `list` |

Output-mode precedence: `--cluster-id` (node view) → `--json` → `--table` →
compact list.

Status semantics (from the official CSS v1 API reference / SDK models):
`100` creating, `200` available, `303` unavailable (for example a failed
creation). Every status other than `200` is treated as abnormal.

## Write-Intent Guard

- The script scans all user arguments (minus the values of read-only filter
  flags such as `--status`, so `--status creating` stays valid) plus the
  `--action` value for mutating vocabulary (`create`, `delete`, `update`,
  `restart`, `reboot`, `scale`, `shrink`, `extend`, `snapshot`, and CSS
  operation names such as `CreateCluster`, `DeleteCluster`, `RebootCluster`).
- Any hit raises `GuardError`, prints `[错误] 检测到写操作意图 ... 已被守卫拦截`,
  and exits with code 1 **before** a single hcloud command is executed.
- `guard_operation()` only accepts the three read-only GET operations, and
  `guard_action()` only accepts `list` / `detail` / `volume`.
- There is no code path that can issue a mutating CSS API call.

## KooCLI Command Format Standard

```text
hcloud <Service> <Operation> --cli-region=<region> [--key=value ...]
```

- **Service name** — exact KooCLI title-case service name: `CSS`.
- **Operation name** — PascalCase: `ListClustersDetails`, `ShowClusterDetail`,
  `ShowClusterVolumeUsage`.
- **Region parameter** — `--cli-region=<value>`, e.g. `--cli-region=cn-north-4`
  (required for every concrete CSS call).
- **Simple parameter** — `--key=value`, e.g. `--limit=10`, `--offset=1`,
  `--datastoreType=elasticsearch`, `--cluster_id=<id>` (the drilled-down cluster
  parameter keeps its official snake_case name).
- **REST paths (official SDK `_http_info`)** —
  `GET /v1.0/{project_id}/clusters`,
  `GET /v1.0/{project_id}/clusters/{cluster_id}`,
  `GET /v1.0/{project_id}/clusters/{cluster_id}/volume`;
  project_id is resolved by KooCLI from the credential profile.

## Error Handling

| Scenario | Behavior |
| ---------- | --------- |
| Empty cluster list | Exit 0, prints `Region <x> 下暂无 CSS 集群` (+ active filter) |
| 403 / IAM policy denies `css:cluster:list` | Exit 1, explicit hint to check credentials and grant `css:cluster:list` / `css:cluster:get` |
| Missing / invalid AK-SK | Exit 1, explicit hint to configure hcloud credentials out-of-band (never in chat) |
| hcloud not installed | SDK fallback; if the SDK is also unavailable, exit 1 with install hints |
| Unknown CLI parameter (`[USE_ERROR]`) | Exit 1, explicit hint to inspect `hcloud CSS <Operation> --help` |
| Non-existent / inaccessible cluster | Exit 1, explicit `集群 <id> 不存在或当前账号无权访问` hint |
| Network / API failure | Exit 1 with the hcloud stderr excerpt |
| Write intent detected | Exit 1, `GuardError` message, no command executed |

Exit codes: `0` success / empty region; `1` config, auth, guard or API error.

## Edge Cases

| Scenario | Handling |
| ---------- | --------- |
| `303` / `100` clusters | Still returned; reported in the abnormal section with their state |
| Disk usage >= 80% | Highlighted in the capacity section (cluster view and node view) |
| Abnormal node | Listed in a dedicated abnormal-node section |
| Volume usage forbidden (403) | Cluster view still renders; usage is `-` and a hint is printed to stderr |
| Large cluster count | Automatic `offset`/`limit` paging driven by `totalSize` (max 200 pages) |
| Extra response fields | `--json` returns the raw record untouched; table uses known fields |
| Field missing on a cluster / node | Rendered as `-` |
| Non-JSON hcloud output | `ApiError` with the raw excerpt (first 200 chars) |
| CSS error envelope with exit 0 | Detected (`errCode` / `externalMessage`) and surfaced as an error, never as an empty list |
| User asks to create / delete / restart | Out of scope — blocked by the write-intent guard; a write-capable skill with explicit confirmation is required |

## Testing

Offline unit tests with a mocked hcloud subprocess and a fake SDK module (no
credentials, no network):

```bash
python3 -m unittest discover -s tests -v
```

Coverage: write-intent guard (read passes / create / delete / restart / reboot /
scale / shrink / snapshot / normalized variants / operation and action
whitelists / status-value handling), command construction, JSON extraction, CSS
error-envelope detection, failure classification (missing AK/SK, 403 / CSS.0051,
`[USE_ERROR]`, generic), paging (totalSize / full-page / dedupe), SDK fallback
(list/detail/volume), filtering, normalization and all main() output modes
including empty, node view, JSON and error paths.

## Reference Documents

| Document | Content |
| ---------- | --------- |
| [references/iam-policies.md](references/iam-policies.md) | Least-privilege read-only IAM policy (`css:cluster:list`, `css:cluster:get`) |
| [references/cli-installation-guide.md](references/cli-installation-guide.md) | KooCLI installation and credential configuration |
| [references/verification-method.md](references/verification-method.md) | How the skill and its tests were verified |
| [references/dataflow-diagram.md](references/dataflow-diagram.md) | Mermaid data flow diagram |
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Acceptance criteria checklist |