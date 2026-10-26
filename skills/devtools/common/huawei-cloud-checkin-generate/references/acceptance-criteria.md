# Acceptance Criteria

| # | Criterion | How it is checked |
|---|-----------|-------------------|
| 1 | Skill directory follows the Huawei Cloud Skill layout (`SKILL.md` + `scripts/` + `tests/`) | `validate-skill.sh`; directory tree |
| 2 | One invocation reliably outputs one check-in record, exit code 0, no error | `python3 scripts/generate_checkin.py`; `test_cli_default_run_ok` |
| 3 | The record carries at least 打卡时间 / 打卡地点 / 备注 (plus type, device, status, record id, date) | `test_default_record_shape` |
| 4 | Output is clear and directly readable (Markdown table by default) | `render_markdown()`; `test_markdown_has_table_and_fields` |
| 5 | Different seeds (or repeated runs without a seed) produce different records | `test_different_seeds_differ` |
| 6 | The same `--seed` reproduces the exact same record | `test_same_seed_is_reproducible`; CLI round-trip |
| 7 | `--format json` emits parseable JSON | `test_cli_json_is_parseable`; `test_json_render_round_trips` |
| 8 | No Huawei Cloud API / resource / credential is required | No `hcloud`/SDK/curl in the skill; runs offline |

## Out of scope (not acceptance criteria)

- Connecting to a real attendance system (check-in upload / approval / correction)
- Batch or historical record management, persistence or reporting
- Identity / geolocation verification
- GUI / web interface