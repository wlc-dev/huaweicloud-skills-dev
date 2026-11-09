# Acceptance Criteria

| # | Criterion | Status |
| - | --------- | ------ |
| 1 | Skill structure complete: SKILL.md + scripts/ + tests/ + references/ (path `skills/bigdata/css/huawei-cloud-css-cluster-list/`) | ✅ |
| 2 | SKILL.md passes specification validation (`validate-skill.sh`, FAIL=0) | ✅ |
| 3 | `ListClustersDetails` inventory with `--limit` 1..100, automatic `offset`/`limit` paging via `totalSize` | ✅ `list_clusters` |
| 4 | Compact list (name / id / status) and `--table` cluster view (id / name / status / engine / version / node spec / node count / storage GB / disk usage / VPC / subnet / security group / created / region) | ✅ `render_simple_view` / `render_cluster_view` |
| 5 | `--table --cluster-id` node view (node id / name / type / spec / status / IP / AZ / disk usage / capacity / used) via `ShowClusterDetail` + `ShowClusterVolumeUsage` | ✅ `render_node_view` |
| 6 | `--json` raw output (cluster array, or `{cluster, volumeUsage}` for drill-down) | ✅ |
| 7 | Filters: `--name` (`--fuzzy`), `--cluster-id`, `--status` (client-side, incl. `abnormal`), `--datastore-type` (server-side), `--region` (default cn-north-4) | ✅ `filter_clusters` |
| 8 | Abnormal clusters (status != 200), disk usage >= 80% and abnormal nodes are highlighted in separate sections, never mixed with normal rows; `--status abnormal` lists only abnormal clusters | ✅ `render_cluster_view` / `render_node_view` |
| 9 | Write-intent guard blocks create / delete / restart / reboot / update / scale / shrink / snapshot (including `--action delete`, `--name create-me`) with rc=1 before any command | ✅ `guard_write_intent` / `guard_operation` / `guard_action` |
| 10 | Explicit, actionable errors: empty list (rc=0) / 403 & CSS.0051 (rc=1) / missing AK-SK (rc=1) / `[USE_ERROR]` (rc=1) / non-existent cluster (rc=1) / network (rc=1) | ✅ `classify_hcloud_failure` / `_payload_error` / `_cluster_not_found` |
| 11 | SDK fallback to `huaweicloudsdkcss` v1 with the same read-only semantics | ✅ `list_clusters_via_sdk` / `show_cluster_via_sdk` / `show_volume_usage_via_sdk` |
| 12 | Offline unit tests with mocked hcloud + fake SDK, all passing | ✅ 85/85 |
| 13 | `python3 -m py_compile` / `bash -n` / `json.tool` syntax checks | ✅ |
| 14 | `references/` complete: iam-policies, cli-installation-guide, verification-method, dataflow-diagram, acceptance-criteria | ✅ |
| 15 | Existing repository tests unaffected (no existing file modified) | ✅ new directory only |

## Live smoke note

The coding session's real read-only call
`python3 scripts/list_css_clusters.py --region cn-north-4` was executed and
returned `CSS.0051 (The current policy does not allow the css:cluster:list
operation)`, so the live account does not currently carry the CSS read
permission. The 403/IAM error path was verified live (clear hint, rc=1). The
success path (cluster list / table / node drill-down / abnormal and capacity
highlighting / JSON) was verified offline with a fake hcloud returning
real-shaped responses. Granting `css:cluster:list` + `css:cluster:get` is
required before the rc=0 live smoke can pass; that live check belongs to the QA
stage.

## Non-existent cluster note

An invalid `--cluster-id` is reported with
`集群 <id> 不存在或当前账号无权访问 ...` and rc=1 (no traceback). When the
account lacks `css:cluster:get`, the API denial is surfaced through the same
auth-error path with the IAM hint instead of a crash.