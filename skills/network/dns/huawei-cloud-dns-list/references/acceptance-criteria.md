# Acceptance Criteria

| # | Criterion | Status |
| - | ---------- | ------ |
| 1 | Skill structure complete: SKILL.md + scripts/ + tests/ + references/ | ✅ |
| 2 | SKILL.md passes specification validation (`validate-skill.sh`) | ✅ |
| 3 | List zones (public/private) and record sets full-field table output incl. 域名/ID/类型/状态/记录集数/邮箱/TTL | ✅ `render_table` |
| 4 | `--json` raw output mode | ✅ |
| 5 | `--names-only` output mode | ✅ |
| 6 | `--type public\|private` / `--recordsets` / `--id` / `--name` / `--record-type` filters working (real server-side query params) | ✅ `build_command` / `resolve_operation` |
| 7 | Empty-list explicit hint 「当前区域无 DNS 域名 / 记录集」(exit 0) | ✅ |
| 8 | 403 explicit hint 「无权限访问云解析服务（DNS），请检查 IAM 权限」(exit 1) | ✅ `AuthError` |
| 9 | Missing AK/SK explicit hint (exit 1) | ✅ `ConfigError` |
| 10 | Missing project_id (SDK fallback) explicit hint (exit 1) | ✅ `resolve_project_id` |
| 11 | No write API call exists in code; write intents blocked by guard before execution | ✅ `guard_write_intent` / `guard_operation` |
| 12 | SDK fallback (`huaweicloudsdkdns` v2) when hcloud is missing | ✅ `list_dns_via_sdk` |
| 13 | CLI / SDK / REST three-level fallback documented (KooCLI → SDK → documented REST paths) | ✅ SKILL.md / verification-method.md |
| 14 | Offline unit tests with mocked hcloud, all passing | ✅ `tests/test_list_dns.py` |
| 15 | Read-only REST path provenance documented | ✅ verification-method.md |
| 16 | SKILL.md ≤ 500 lines, files ≤ 30, size ≤ 40 MB, extension allowlist | ✅ |
| 17 | `network/dns` provides the new DNS service category path | ✅ |