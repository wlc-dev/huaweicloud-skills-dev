# Usage Guide

## Quick start

```bash
python3 scripts/generate_checkin.py --seed 20240501
```

Prints one Markdown table with a single check-in record (记录编号 / 打卡日期 / 打卡类型 /
打卡时间 / 打卡地点 / 打卡方式 / 打卡状态 / 备注) to stdout.

## Common variations

```bash
# Plain text
python3 scripts/generate_checkin.py --seed 42 --format text

# JSON (machine-readable, for piping into other tools)
python3 scripts/generate_checkin.py --seed 42 --format json

# A specific check-in date
python3 scripts/generate_checkin.py --seed 7 --date 2026-01-02

# Use a custom data pool
python3 scripts/generate_checkin.py --data ./my-pool.json

# Write the result to a file
python3 scripts/generate_checkin.py --seed 7 --output checkin.md
```

## Reproducibility

- Passing `--seed <int>` makes the output deterministic: the same seed always produces the
  same record.
- Omitting `--seed` still works; the generator picks a random seed and prints it
  (`> 随机种子（seed）：<n>` in Markdown, `随机种子（seed）：<n>` in text, a `seed` field in
  JSON), so the run can be reproduced later with `--seed <n>`.

## Record fields

| Field | Meaning |
|-------|---------|
| `record_id` | A generated id, `CK-<YYYYMMDD>-<4 hex>` |
| `date` / `weekday` | Check-in date (default today, `--date` to override) and Chinese weekday |
| `type` | 打卡类型 (上班/下班/外勤/会议签到/弹性/加班 …) |
| `time` | 打卡时间 drawn from the type's own window |
| `location` | 打卡地点 |
| `device` | 打卡方式 (App 定位 / 人脸识别 / 工牌 / …) |
| `status` | 打卡状态, derived from the type and time (e.g. 迟到 / 早退 / 外勤 / 正常) |
| `note` | 备注 |

## Extending the data pool

`scripts/checkin_data.json` holds the default pools: `types` (each with `name` / `start` /
`end`), `locations`, `devices` and `notes`. Add entries to any array; `types` entries must
keep a `HH:MM` `start` and `end`. A completely different pool can be supplied with
`--data /path/to/pool.json`, which uses the same shape. No code change is required.

## Notes

- All generated content is **sample/demo data**, not a real attendance record.
- The skill is read-only with respect to the cloud: it reads only its local data pool and
  writes only to stdout or a user-chosen `--output` file.