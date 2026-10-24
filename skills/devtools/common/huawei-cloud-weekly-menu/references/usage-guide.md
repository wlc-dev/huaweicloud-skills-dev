# Usage Guide

## Quick start

```bash
python3 scripts/generate_weekly_menu.py --seed 20240501
```

Prints a 7-day Markdown menu (breakfast/lunch/dinner per day) to stdout.

## Common variations

```bash
# Plain text
python3 scripts/generate_weekly_menu.py --seed 42 --format text

# JSON (machine-readable, for piping into other tools)
python3 scripts/generate_weekly_menu.py --seed 42 --format json

# Two days, only breakfast and dinner
python3 scripts/generate_weekly_menu.py --days 2 --meals breakfast,dinner

# Different number of days
python3 scripts/generate_weekly_menu.py --days 5

# Allow repeats (disable in-week de-duplication)
python3 scripts/generate_weekly_menu.py --no-dedup

# Write to a file
python3 scripts/generate_weekly_menu.py --seed 7 --output menu.md
```

## Reproducibility

- Passing `--seed <int>` makes the output deterministic: the same seed always
  produces the same menu.
- Omitting `--seed` still works; the generator picks a random seed and prints it
  (`Seed: <n>`), so the run can be reproduced later with `--seed <n>`.

## Extending the dish library

`scripts/dishes.json` holds the library. Add dishes to the `breakfast` / `lunch` /
`dinner` arrays (each array should keep at least 7 entries so a duplicate-free week
is possible). No code change is required. A completely different library can be
supplied with `--dishes /path/to/library.json`, which uses the same shape.

## Degradation behaviour

If a meal pool holds fewer dishes than the requested number of days, the generator
keeps producing days but reuses dishes for the affected meal and reports it under
`degraded` (Markdown/text print a short note).