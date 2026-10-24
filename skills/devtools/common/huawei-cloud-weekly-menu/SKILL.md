---
name: huawei-cloud-weekly-menu
description: |
  Randomly generate a one-week menu (7 days by default, with breakfast / lunch / dinner
  every day) from a self-contained dish library. Picks dishes at random, avoids repeating
  the same dish within the same meal slot across the week when the pool allows, prints a
  readable Markdown or plain-text menu, and is reproducible through a --seed flag.
  Implemented with the Python 3 standard library only; it does not call the Huawei Cloud
  CLI, any Huawei Cloud SDK, or any REST API, and it touches no cloud resource.
  Triggers include: "生成一周菜单", "随机生成菜单", "一周食谱", "规划一周饮食",
  "帮我排一周菜谱", "weekly menu", "random menu", "meal plan", "weekly meal planner".
tags: [devtools, menu, generator, python, utility]
---

# Weekly Menu Generator

## Overview

This skill produces a random menu for a week. By default it covers **7 days**, each
day with **three meals** (breakfast / lunch / dinner), drawn from a built-in dish
library (`scripts/dishes.json`). It focuses on everyday meal planning: the same dish
is not repeated within the same meal slot across a week whenever the pool is large
enough, output is human-readable, and a `--seed` value makes any run repeatable.

- **Generates** a complete week (day -> meal -> dish) in one call.
- **In-week de-duplication** is applied per meal slot (breakfast dishes only
  compete with breakfast dishes, and so on).
- **Reproducible** through `--seed`; when omitted, a random seed is chosen and
  printed so the run can be reproduced.
- **Self-contained**: pure Python 3 standard library, no network, no credentials.

## Prerequisites

- **Python 3.8+** available as `python3` (or `python`) on `PATH`.
- No Huawei Cloud credentials, CLI (KooCLI), SDK, or network access are needed;
  this skill is entirely local.
- `scripts/dishes.json` must be present (it ships with the skill) unless a custom
  library is supplied with `--dishes`.

## Workflow

1. **Load the dish library** — `load_dishes()` reads `scripts/dishes.json` and
   returns a mapping of meal slot to a list of dishes.
2. **Pick the week** — `pick_week(seed, days, meals, dedup)` walks each day and each
   meal slot, choosing a dish from the slot's pool with `random.Random(seed)`.
   When de-duplication is on, dishes already used in that slot this week are
   excluded; if the pool is too small, repeats are allowed and reported.
3. **Render** — `render_markdown()` / `render_text()` / JSON turn the week into
   readable output.
4. **Emit** — the result is written to standard output, or to a file when
   `--output` is given.

## Core Commands

```bash
# Default: a 7-day Markdown menu, reproducible with the given seed
python3 scripts/generate_weekly_menu.py --seed 20240501

# Plain text
python3 scripts/generate_weekly_menu.py --seed 42 --format text

# JSON (machine-readable)
python3 scripts/generate_weekly_menu.py --seed 42 --format json

# Custom number of days and meal slots
python3 scripts/generate_weekly_menu.py --seed 7 --days 2 --meals breakfast,dinner

# Allow repeats (disable in-week de-duplication)
python3 scripts/generate_weekly_menu.py --no-dedup

# Use a custom dish library and write the result to a file
python3 scripts/generate_weekly_menu.py --dishes /path/to/dishes.json --output menu.md

# Run the bundled unit tests
python3 -m unittest discover -s tests -v
```

The command-line entry point is `scripts/generate_weekly_menu.py`. The built-in
`scripts/dishes.json` is what the examples above read by default.

## Parameter Confirmation

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| `--days` | No | Number of days to generate | `7` |
| `--meals` | No | Comma-separated meal slots | `breakfast,lunch,dinner` |
| `--seed` | No | Integer seed for reproducible output | random (printed) |
| `--format` | No | Output format: `markdown`, `text`, or `json` | `markdown` |
| `--no-dedup` | No | Allow the same dish to repeat within the week | de-dup on |
| `--dishes` | No | Path to a custom dish library JSON | `scripts/dishes.json` |
| `--output` | No | Write the menu to a file instead of stdout | stdout |

## Reference Documents

| Document | Description |
|----------|-------------|
| [references/usage-guide.md](references/usage-guide.md) | Command recipes, reproducibility rules, extending the library |
| [references/verification-method.md](references/verification-method.md) | How the skill is verified (offline unit tests + spot checks) |
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Acceptance criteria and out-of-scope items |
| [references/dataflow-diagram.md](references/dataflow-diagram.md) | Mermaid data flow diagram |
| [references/iam-policies.md](references/iam-policies.md) | Permission notes (none required) |

## Notes

- The generator is read-only with respect to the cloud: it reads only its local
  dish library and writes only to standard output or a user-chosen `--output` file.
- Output ordering: days are labelled `Day 1` .. `Day N` with a weekday name cycling
  from Monday.
- To expand the menu, add dishes to the arrays in `scripts/dishes.json`; each meal
  array should keep at least 7 entries so a duplicate-free week remains possible.