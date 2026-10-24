# Acceptance Criteria

| # | Criterion | How it is checked |
|---|-----------|-------------------|
| 1 | Skill directory follows the Huawei Cloud Skill layout (`SKILL.md` + `scripts/` + `tests/`) | `validate-skill.sh`; directory tree |
| 2 | Triggering the generator reliably outputs a 7-day menu (breakfast/lunch/dinner by default) | `python3 scripts/generate_weekly_menu.py`; `test_default_week_shape` |
| 3 | Output is readable Markdown / plain text | `render_markdown()` / `render_text()`; `test_markdown_contains_days_and_meals` |
| 4 | Random logic is reproducible with the same `--seed` | `test_same_seed_is_reproducible`; CLI round-trip |
| 5 | Basic in-week de-duplication within the same meal slot | `test_same_meal_no_duplicates_within_week` |
| 6 | No Huawei Cloud API / resource / credential is required | No `hcloud`/SDK/curl in the skill; runs offline |

## Out of scope (not acceptance criteria)

- Nutrition / calorie calculation
- Shopping-list generation
- GUI
- Persistent storage