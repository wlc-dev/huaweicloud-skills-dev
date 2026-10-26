#!/usr/bin/env python3
"""Generate one random check-in record.

Assembles a single "打卡记录" (check-in record) by combining one entry from each
built-in pool: a check-in type (with its own plausible time window), a location,
a check-in device and a note. The record is rendered as readable Markdown (the
default), plain text or JSON. A ``--seed`` value makes any run reproducible; when
omitted a random seed is chosen and printed so the run can be reproduced.

This module is pure Python 3 standard library. It does not call the Huawei Cloud
CLI, any Huawei Cloud SDK, or any REST API, and it touches no cloud resource.

Public API:
    load_data(path=None) -> dict
    build_record(seed=None, date=None, data=None) -> dict
    render_markdown(record) -> str
    render_text(record) -> str
    render_json(record) -> str
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import sys
from typing import Dict, Optional

WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

# Status derived from the check-in time, overriding the plain type label when the
# time falls outside the "normal" band of a commute check-in.
ON_DUTY_LATE_AFTER = "09:00"
OFF_DUTY_EARLY_BEFORE = "18:00"


def _default_data_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkin_data.json")


def load_data(path: Optional[str] = None) -> Dict[str, object]:
    """Load the built-in data pool.

    Accepts either the shipped ``checkin_data.json`` shape or a custom file with
    the same keys (``types`` / ``locations`` / ``devices`` / ``notes``). Raises
    ``OSError`` / ``ValueError`` on unusable input.
    """
    path = path or _default_data_path()
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("data pool must be a JSON object")

    types = []
    for item in data.get("types", []) or []:
        if isinstance(item, str):
            types.append({"name": item, "start": "08:00", "end": "09:00"})
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        types.append(
            {
                "name": name,
                "start": str(item.get("start", "08:00")).strip() or "08:00",
                "end": str(item.get("end", "09:00")).strip() or "09:00",
            }
        )

    def _clean_list(key: str):
        raw = data.get(key, []) or []
        if not isinstance(raw, list):
            raise ValueError("%s must be an array" % key)
        return [str(item).strip() for item in raw if str(item).strip()]

    locations = _clean_list("locations")
    devices = _clean_list("devices")
    notes = _clean_list("notes")

    if not types or not locations:
        raise ValueError("data pool needs at least one type and one location")

    return {"types": types, "locations": locations, "devices": devices, "notes": notes}


def _to_minutes(value: str) -> int:
    hh, mm = (int(part) for part in value.split(":"))
    return hh * 60 + mm


def _from_minutes(value: int) -> str:
    value %= 24 * 60
    return "%02d:%02d" % (value // 60, value % 60)


def _random_time(rng: random.Random, start: str, end: str) -> str:
    lo = _to_minutes(start)
    hi = _to_minutes(end)
    if hi < lo:
        lo, hi = hi, lo
    return _from_minutes(rng.randint(lo, hi))


def _derive_status(type_name: str, time_str: str) -> str:
    """Derive a realistic status from the type and the check-in time."""
    if "上班" in type_name and time_str > ON_DUTY_LATE_AFTER:
        return "迟到"
    if "下班" in type_name and time_str < OFF_DUTY_EARLY_BEFORE:
        return "早退"
    for marker, label in (("外勤", "外勤"), ("会议", "会议"), ("弹性", "弹性"), ("加班", "加班")):
        if marker in type_name:
            return label
    return "正常"


def _resolve_date(date) -> _dt.date:
    if date is None:
        return _dt.date.today()
    if isinstance(date, _dt.date):
        return date
    return _dt.date.fromisoformat(str(date))


def build_record(
    seed: Optional[int] = None,
    date=None,
    data: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Assemble one check-in record.

    Returns ``{"seed", "explicit_seed", "record"}`` where ``record`` holds the
    generated fields (record_id / date / weekday / type / time / location /
    device / status / note). ``seed`` is always concrete (a generated one is used
    when none is given) so the run can be reproduced with ``--seed``.
    """
    if data is None:
        data = load_data()

    types = data.get("types") or []
    if not types:
        raise ValueError("data pool contains no check-in types")

    explicit_seed = seed is not None
    if seed is None:
        seed = random.SystemRandom().randint(0, 2**31 - 1)
    rng = random.Random(seed)

    day = _resolve_date(date)
    chosen = rng.choice(types)

    time_str = _random_time(rng, chosen.get("start", "08:00"), chosen.get("end", "09:00"))
    location = rng.choice(list(data.get("locations") or []))
    device = rng.choice(list(data.get("devices") or [])) if data.get("devices") else "手机 App 定位打卡"
    note = rng.choice(list(data.get("notes") or [])) if data.get("notes") else "正常打卡"
    status = _derive_status(str(chosen.get("name", "")), time_str)
    record_id = "CK-%s-%04X" % (day.strftime("%Y%m%d"), rng.randint(0, 0xFFFF))

    record = {
        "record_id": record_id,
        "date": day.isoformat(),
        "weekday": WEEKDAY_NAMES[day.weekday()],
        "type": str(chosen.get("name", "")),
        "time": time_str,
        "location": location,
        "device": device,
        "status": status,
        "note": note,
    }
    return {"seed": seed, "explicit_seed": explicit_seed, "record": record}


def _seed_note(payload: Dict[str, object]) -> str:
    seed = payload["seed"]
    if payload.get("explicit_seed"):
        return "随机种子（seed）：%s" % seed
    return "随机种子（seed）：%s（本次自动生成；用 --seed %s 可复现）" % (seed, seed)


def render_markdown(payload: Dict[str, object]) -> str:
    """Render a record payload as readable Markdown."""
    record = payload["record"]
    lines = ["# 打卡记录", ""]
    lines.append("> %s" % _seed_note(payload))
    lines.append("")
    lines.append("| 字段 | 内容 |")
    lines.append("|------|------|")
    rows = [
        ("记录编号", record["record_id"]),
        ("打卡日期", "%s（%s）" % (record["date"], record["weekday"])),
        ("打卡类型", record["type"]),
        ("打卡时间", record["time"]),
        ("打卡地点", record["location"]),
        ("打卡方式", record["device"]),
        ("打卡状态", record["status"]),
        ("备注", record["note"]),
    ]
    for label, value in rows:
        lines.append("| %s | %s |" % (label, value))
    return "\n".join(lines) + "\n"


def render_text(payload: Dict[str, object]) -> str:
    """Render a record payload as plain text."""
    record = payload["record"]
    lines = ["打卡记录", "========"]
    lines.append(_seed_note(payload))
    lines.append("")
    rows = [
        ("记录编号", record["record_id"]),
        ("打卡日期", "%s（%s）" % (record["date"], record["weekday"])),
        ("打卡类型", record["type"]),
        ("打卡时间", record["time"]),
        ("打卡地点", record["location"]),
        ("打卡方式", record["device"]),
        ("打卡状态", record["status"]),
        ("备注", record["note"]),
    ]
    for label, value in rows:
        lines.append("  %-8s %s" % (label + "：", value))
    return "\n".join(lines) + "\n"


def render_json(payload: Dict[str, object]) -> str:
    body = {
        "seed": payload["seed"],
        "explicit_seed": payload.get("explicit_seed", False),
        "record": payload["record"],
    }
    return json.dumps(body, ensure_ascii=False, indent=2) + "\n"


def render(payload: Dict[str, object], fmt: str = "markdown") -> str:
    if fmt == "text":
        return render_text(payload)
    if fmt == "json":
        return render_json(payload)
    return render_markdown(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="随机生成一条打卡记录（Markdown 表格 / 文本 / JSON）。",
        prog="generate_checkin.py",
    )
    parser.add_argument("--seed", type=int, default=None, help="随机种子；省略时随机取一个并打印，便于复现")
    parser.add_argument("--date", default=None, help="打卡日期 YYYY-MM-DD（默认今天）")
    parser.add_argument(
        "--format",
        choices=("markdown", "text", "json"),
        default="markdown",
        help="输出格式（默认 markdown）",
    )
    parser.add_argument("--data", default=None, help="自定义数据池 JSON 文件（默认内置 checkin_data.json）")
    parser.add_argument("--output", default=None, help="写入文件（默认输出到标准输出）")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        data = load_data(args.data)
        payload = build_record(seed=args.seed, date=args.date, data=data)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2

    out = render(payload, args.format)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(out)
        if args.format != "json":
            print("随机种子（seed）：%s" % payload["seed"])
            print("已写入打卡记录到 %s" % args.output)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())