# Verification Method

## Scope

This skill is a pure local Python generator. Verification is fully offline and
does not contact Huawei Cloud, the Huawei Cloud CLI (KooCLI), any SDK, or any REST
API.

## Automated checks

1. Structural / specification validation:

   ```bash
   bash scripts/validate-skill.sh -s <skill-dir>
   ```

2. Unit tests bundled with the skill:

   ```bash
   python3 -m unittest discover -s tests -v
   ```

   Covered assertions:

   - The built-in library has at least 7 dishes for each of breakfast/lunch/dinner.
   - A default week has 7 days and exactly breakfast, lunch, dinner per day.
   - Within one week, a meal slot never repeats a dish (when the pool is large enough).
   - The same `--seed` always produces identical output (Markdown/text/JSON).
   - Custom `--days` / `--meals` and graceful degradation on a small pool.
   - CLI smoke via `--help` and end-to-end runs in each output format.

3. Reproducibility spot check:

   ```bash
   python3 scripts/generate_weekly_menu.py --seed 20240501 --format markdown
   python3 scripts/generate_weekly_menu.py --seed 20240501 --format markdown   # identical
   ```

## Manual checks

- Confirm the printed menu is readable and contains one dish per meal slot per day.
- Confirm that when `--seed` is omitted, a concrete seed is printed so the run can
  be reproduced.

## Acceptance criteria

See [acceptance-criteria.md](acceptance-criteria.md).