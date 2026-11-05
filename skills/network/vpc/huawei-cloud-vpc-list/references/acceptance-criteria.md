# Acceptance Criteria

| # | Criterion | Status |
| - | --------- | ------ |
| 1 | Skill structure complete: SKILL.md + scripts/ + tests/ + references/ | ✅ |
| 2 | SKILL.md passes specification validation (`validate-skill.sh`) | ✅ |
| 3 | ListVpcs full-field table output incl. 名称/ID/cidr/status 及其余字段 | ✅ `render_table` + `normalize_vpc` |
| 4 | `--json` raw output mode | ✅ |
| 5 | `--names-only` output mode | ✅ |
| 6 | `--id` / `--enterprise-project-id` filters working (real server-side query params; `--id` emitted as v3 array form `--id.1=<vpc-id>`) | ✅ 已修复并实测可用 `build_command` |
| 7 | Empty-list explicit hint 「当前区域无虚拟私有云（VPC）」(exit 0) | ✅ |
| 8 | 403 explicit hint 「无权限访问虚拟私有云（VPC），请检查 IAM 权限」(exit 1) | ✅ `AuthError` |
| 9 | Missing AK/SK explicit hint (exit 1) | ✅ `ConfigError` |
| 10 | Missing project_id (SDK fallback) explicit hint (exit 1) | ✅ `resolve_project_id` |
| 11 | No write API call exists in code; write intents blocked by guard before execution | ✅ `guard_write_intent` / `guard_operation` |
| 12 | SDK fallback (`huaweicloudsdkvpc`) when hcloud is missing | ✅ `list_vpcs_via_sdk` |
| 13 | Offline unit tests with mocked hcloud, all passing | ✅ 92 tests |
| 14 | Read-only REST path provenance documented | ✅ verification-method.md |
| 15 | SKILL.md ≤ 500 lines, files ≤ 30, size ≤ 40 MB, extension allowlist | ✅ |
| 16 | `network/vpc` provides the new VPC category path | ✅ |
| 17 | `--format {table,json,names,md}` (default `table`), legacy `--json` / `--names-only` kept | ✅ `main` |
| 18 | `--format md` writes a valid 8-column Markdown table, VPC 名称 first | ✅ `render_markdown` / `normalized_row` |
| 19 | Empty / filtered-empty list still writes a header-only `.md` and exits 0 | ✅ |
| 20 | Default name `vpc_list_<region>_<timestamp>.md`, parent dir auto-created, temp file + atomic rename | ✅ `default_output_path` / `export_markdown` |
| 21 | `--output` / `--format` values excluded from the write-intent guard; write intents still blocked | ✅ `guard_text_from_argv` |
| 22 | Markdown contract identical to huawei-cloud-vpc-export-markdown (locked by test) | ✅ `test_contract_matches_export_markdown` |