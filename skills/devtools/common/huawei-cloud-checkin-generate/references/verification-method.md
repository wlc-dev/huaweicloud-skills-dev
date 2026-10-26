# Verification Method

## Scope

This skill is a pure local Python generator. Verification is fully offline and does not
contact Huawei Cloud, the Huawei Cloud CLI (KooCLI), any SDK, or any REST API.

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

   - The built-in pools (`types` / `locations` / `devices` / `notes`) are non-empty, and
     every type carries a non-empty `name`, `start` and `end`.
   - A default record contains all required fields, none empty, and dates to today.
   - `--date` overrides the date and yields the matching weekday.
   - Different seeds produce different records; the same seed reproduces the exact same
     record (Markdown / text / JSON).
   - The status is derived correctly from the type and the check-in time.
   - The Markdown renderer emits the table header and every field label; the JSON renderer
     round-trips.
   - A custom data-pool file is honored; a missing/unusable pool exits with code 2.
   - CLI smoke: `--help`, a default run, a JSON run (parseable), `--output` file writing.

3. Reproducibility spot check:

   ```bash
   python3 scripts/generate_checkin.py --seed 20240501
   python3 scripts/generate_checkin.py --seed 20240501   # identical
   ```

## Manual checks

- Confirm the printed record is readable and contains a time, a location and a note.
- Confirm that when `--seed` is omitted, a concrete seed is printed so the run can be
  reproduced.

## Acceptance criteria

See [acceptance-criteria.md](acceptance-criteria.md).