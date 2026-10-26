---
name: huawei-cloud-checkin-generate
description: |
  Randomly generate one check-in record (打卡记录). A single call draws one entry from
  each built-in pool — a check-in type with its own plausible time window, a location,
  a check-in device and a note — assembles one record, derives a realistic status from
  the type and time, and prints it as a readable Markdown table (or plain text / JSON).
  A --seed flag makes any run reproducible; when omitted a random seed is chosen and
  printed. Implemented with the Python 3 standard library only; it does not call the
  Huawei Cloud CLI, any Huawei Cloud SDK, or any REST API, and it touches no cloud
  resource.
  Triggers include: "生成打卡记录", "随机打卡", "打卡生成", "生成一条打卡",
  "随机生成打卡记录", "打卡记录", "checkin generate", "check-in generator",
  "random checkin", "generate a check-in record".
tags: [devtools, checkin, generator, python, utility]
---

# Check-in Record Generator

## Overview

This skill produces **one random check-in record** per invocation. The record is
assembled by combining one entry from each built-in pool (`scripts/checkin_data.json`):

- **打卡类型** — e.g. 上班 / 下班 / 外勤 / 会议签到 / 弹性 / 加班, each with its own
  plausible time window so the generated time makes sense for the type.
- **打卡地点 / 打卡方式 / 备注** — a location, a check-in device and a note.

A **打卡状态** is derived from the type and the check-in time (e.g. 上班 after 09:00 →
迟到, 下班 before 18:00 → 早退). Output is a readable Markdown table by default, with
plain-text and JSON alternatives. The generator is deterministic under `--seed`.

- **One call → one record** — a single, self-contained 打卡记录.
- **Reproducible** — passing `--seed` makes a run deterministic; when omitted, a random
  seed is chosen and printed so the run can be reproduced later.
- **Self-contained** — pure Python 3 standard library, no network, no credentials.
- **Demo data only** — the output is generated sample content; it is not connected to any
  real attendance system.

## Prerequisites

- **Python 3.8+** available as `python3` (or `python`) on `PATH`.
- No Huawei Cloud credentials, CLI (KooCLI), SDK, or network access are needed; this skill
  is entirely local.
- `scripts/checkin_data.json` must be present (it ships with the skill) unless a custom
  pool is supplied with `--data`.

## Workflow

1. **Load the data pool** — `load_data()` reads `scripts/checkin_data.json` and returns the
   `types` / `locations` / `devices` / `notes` pools; `--data` may override it with a
   custom JSON file of the same shape.
2. **Pick a type and window** — `build_record(seed, date, data)` selects one check-in type
   with `random.Random(seed)` and draws the check-in time from that type's time window.
3. **Fill the record** — a location, a device and a note are chosen from their pools, and
   the status is derived from the type and time.
4. **Render** — `render_markdown()` / `render_text()` / `render_json()` turn the record
   into readable output (Markdown table by default).
5. **Emit** — the result goes to standard output, or to a file when `--output` is given.

## Core Commands

```bash
# Default: one Markdown check-in record, reproducible with the given seed
python3 scripts/generate_checkin.py --seed 20240501

# Plain text
python3 scripts/generate_checkin.py --seed 42 --format text

# JSON (machine-readable, for piping into other tools)
python3 scripts/generate_checkin.py --seed 42 --format json

# A specific check-in date
python3 scripts/generate_checkin.py --seed 7 --date 2026-01-02

# Use a custom data pool and write the result to a file
python3 scripts/generate_checkin.py --data /path/to/pool.json --output checkin.md

# Run the bundled unit tests
python3 -m unittest discover -s tests -v
```

The command-line entry point is `scripts/generate_checkin.py`; the built-in
`scripts/checkin_data.json` is what the examples above read by default.

## Parameter Confirmation

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| `--seed` | No | Integer seed for reproducible output | random (printed) |
| `--date` | No | Check-in date `YYYY-MM-DD` | today |
| `--format` | No | Output format: `markdown`, `text`, or `json` | `markdown` |
| `--data` | No | Path to a custom data-pool JSON file | `scripts/checkin_data.json` |
| `--output` | No | Write the record to a file instead of stdout | stdout |

## Reference Documents

| Document | Description |
|----------|-------------|
| [references/usage-guide.md](references/usage-guide.md) | Command recipes, reproducibility rules, extending the data pool |
| [references/verification-method.md](references/verification-method.md) | How the skill is verified (offline unit tests + spot checks) |
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Acceptance criteria and out-of-scope items |
| [references/dataflow-diagram.md](references/dataflow-diagram.md) | Mermaid data flow diagram |
| [references/iam-policies.md](references/iam-policies.md) | Permission notes (none required) |

## Notes

- The generator is read-only with respect to the cloud: it reads only its local data pool
  and writes only to standard output or a user-chosen `--output` file.
- The generated record is **sample/demo data**, not a real attendance record and not
  connected to any attendance/approval system.
- To expand the pool, add entries to the arrays in `scripts/checkin_data.json`; each
  `types` entry needs a `name`, `start` and `end` (`HH:MM`). No code change is required.