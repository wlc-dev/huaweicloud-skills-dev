# Acceptance Criteria

| # | Criterion | Status |
| - | ---------- | ------ |
| 1 | Skill structure complete: SKILL.md + scripts/ + tests/ + references/ | ✅ |
| 2 | SKILL.md passes specification validation (`validate-skill.sh`) | ✅ |
| 3 | ListServersDetails full-field table output incl. 名称/ID/状态/规格/可用区/私网IP/公网IP | ✅ `render_table` + `normalize_server` |
| 4 | `--json` raw output mode | ✅ |
| 5 | `--names-only` compact 名称+ID 清单 output mode | ✅ `server_summary_lines` |
| 6 | `--status` / `--name` filters forwarded as real server-side ECS params | ✅ `build_command` |
| 7 | Empty-list explicit hint 「当前区域无 ECS 实例」(exit 0) | ✅ |
| 8 | 403 explicit hint 「无权限访问 ECS，请检查 IAM 权限」(exit 1) | ✅ `AuthError` |
| 9 | Missing AK/SK explicit hint (exit 1) | ✅ `ConfigError` |
| 10 | No write API call exists in code; write intents blocked by guard before execution | ✅ `guard_write_intent` / `guard_operation` |
| 11 | SDK fallback (`huaweicloudsdkecs`) when hcloud is missing | ✅ `list_servers_via_sdk` |
| 12 | Offline unit tests with mocked hcloud, all passing | ✅ 119 tests |
| 13 | Read-only REST path provenance documented | ✅ verification-method.md |
| 14 | SKILL.md ≤ 500 lines, files ≤ 30, size ≤ 40 MB, extension allowlist | ✅ |
| 15 | `--md-file <PATH>` / `--output-md <PATH>` writes a valid Markdown report with Region, 查询时间, 实例总数 and a `实例名称 \| 实例 ID` table | ✅ `render_markdown` / `write_markdown_file` |
| 16 | `--md-file` without a value writes the default `ecs-list-<region>-<YYYYMMDD>.md` | ✅ `default_markdown_name` |
| 17 | Markdown export is additive — default table / `--json` / `--names-only` stdout behaviour is unchanged | ✅ `main()` output branches |
| 18 | Empty list → report contains 「共 0 个实例」 (+ active filters) and exits 0 | ✅ |
| 19 | Successful write prints the report's absolute path on stdout | ✅ `已生成 Markdown 文件：<abs path>` |
| 20 | Write failure (missing directory / unwritable target) → explicit 「无法写入 Markdown 文件」 hint, exit 1, no half file and no temp sibling left behind | ✅ `OutputError` + temp-file-then-rename |
| 21 | Report path containing `delete` / `start` / `stop` is not blocked by the write-intent guard (single-value flags are exempt, a following flag is still scanned) | ✅ `_VALUE_STRIPPED_FLAGS` + guard regression tests |
| 22 | `--txt-file <PATH>` / `--output-txt <PATH>` writes a UTF-8 plain-text report with Region, 查询时间, 实例总数 and the 名称·ID·状态·规格·vCPU·内存·可用区·私网IP·公网IP inventory | ✅ `render_txt` / `write_txt_file` |
| 23 | `--txt-file` without a value writes the default `ecs-list-<region>-<YYYYMMDD>.txt` | ✅ `default_txt_name` |
| 24 | TXT export is additive — stdout (table / `--json` / `--names-only`) is unchanged; may be stacked with `--md-file` | ✅ `main()` output branches |
| 25 | Empty list → TXT contains 「共 0 个实例」 (+ active filters) and exits 0 | ✅ |
| 26 | Successful TXT write prints the report's absolute path on stdout | ✅ `已生成 TXT 文件：<abs path>` |
| 27 | TXT write failure (missing directory / unwritable target) → explicit 「无法写入 TXT 文件」 hint, exit 1, no half file and no temp sibling left behind | ✅ `OutputError` + temp-file-then-rename |
| 28 | TXT path containing `delete` / `start` / `stop` is not blocked by the write-intent guard | ✅ `_VALUE_STRIPPED_FLAGS` + guard regression tests |
