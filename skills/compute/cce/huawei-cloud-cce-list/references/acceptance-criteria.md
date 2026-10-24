# Acceptance Criteria

| # | Criterion | Status |
| - | ---------- | ------ |
| 1 | Skill structure complete: SKILL.md + scripts/ + tests/ + references/ | ✅ |
| 2 | SKILL.md passes specification validation (`validate-skill.sh`) | ✅ |
| 3 | ListClusters full-field table output incl. 名称/UID/别名/状态/类型/规格/版本/类别/计费模式 | ✅ `render_table` + `normalize_cluster` |
| 4 | `--json` raw output mode | ✅ |
| 5 | `--names-only` output mode | ✅ |
| 6 | `--name` / `--id` filters working (client-side, documented) | ✅ `filter_clusters` |
| 7 | Empty-list explicit hint 「当前区域无云容器引擎（CCE）集群」(exit 0) | ✅ |
| 8 | 403 explicit hint 「无权限访问云容器引擎（CCE），请检查 IAM 权限」(exit 1) | ✅ `AuthError` |
| 9 | Missing AK/SK explicit hint (exit 1) | ✅ `ConfigError` |
| 10 | No write API call exists in code; write intents blocked by guard before execution | ✅ `guard_write_intent` / `guard_operation` |
| 11 | SDK fallback (`huaweicloudsdkcce`) when hcloud is missing | ✅ `list_clusters_via_sdk` |
| 12 | Offline unit tests with mocked hcloud, all passing | ✅ |
| 13 | Read-only REST path provenance documented | ✅ verification-method.md |
| 14 | SKILL.md ≤ 500 lines, files ≤ 30, size ≤ 40 MB, extension allowlist | ✅ |
| 15 | `compute/cce` provides the new Compute/CCE category path | ✅ |