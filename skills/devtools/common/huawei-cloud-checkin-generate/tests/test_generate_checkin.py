#!/usr/bin/env python3
"""Unit tests for scripts/generate_checkin.py.

Run from the skill directory:
    python3 -m unittest discover -s tests -v
or:
    python3 tests/test_generate_checkin.py
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
SCRIPT_PATH = os.path.join(SCRIPTS_DIR, "generate_checkin.py")

REQUIRED_FIELDS = (
    "record_id",
    "date",
    "weekday",
    "type",
    "time",
    "location",
    "device",
    "status",
    "note",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_checkin", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gc = _load_module()


class LoadDataTests(unittest.TestCase):
    def test_builtin_pools_non_empty(self):
        data = gc.load_data()
        self.assertTrue(data["types"])
        self.assertTrue(data["locations"])
        self.assertTrue(data["devices"])
        self.assertTrue(data["notes"])
        for entry in data["types"]:
            self.assertTrue(entry["name"])
            self.assertTrue(entry["start"])
            self.assertTrue(entry["end"])

    def test_missing_file_raises(self):
        with self.assertRaises(OSError):
            gc.load_data(os.path.join(HERE, "does-not-exist.json"))

    def test_custom_pool_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pool.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "types": [{"name": "测试打卡", "start": "09:00", "end": "10:00"}],
                        "locations": ["测试地点"],
                        "devices": ["测试设备"],
                        "notes": ["测试备注"],
                    },
                    handle,
                )
            data = gc.load_data(path)
            record = gc.build_record(seed=1, data=data)["record"]
            self.assertEqual(record["type"], "测试打卡")
            self.assertEqual(record["location"], "测试地点")

    def test_empty_types_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"types": [], "locations": []}, handle)
            with self.assertRaises(ValueError):
                gc.load_data(path)


class BuildRecordTests(unittest.TestCase):
    def test_default_record_shape(self):
        payload = gc.build_record(seed=1234)
        self.assertIn("seed", payload)
        record = payload["record"]
        for field in REQUIRED_FIELDS:
            self.assertIn(field, record)
            self.assertTrue(str(record[field]).strip(), "%s must be non-empty" % field)

    def test_record_date_defaults_to_today(self):
        payload = gc.build_record(seed=1)
        self.assertEqual(payload["record"]["date"], gc._dt.date.today().isoformat())

    def test_record_date_override(self):
        payload = gc.build_record(seed=1, date="2026-01-02")
        self.assertEqual(payload["record"]["date"], "2026-01-02")
        self.assertEqual(payload["record"]["weekday"], "周五")

    def test_same_seed_is_reproducible(self):
        first = gc.build_record(seed=20240501)
        second = gc.build_record(seed=20240501)
        self.assertEqual(first["record"], second["record"])
        self.assertEqual(gc.render_markdown(first), gc.render_markdown(second))

    def test_different_seeds_differ(self):
        rendered = {gc.render_json(gc.build_record(seed=s)) for s in range(1, 12)}
        self.assertGreater(len(rendered), 1, "different seeds should produce different records")

    def test_no_seed_generates_concrete_seed(self):
        payload = gc.build_record()
        self.assertIsInstance(payload["seed"], int)
        self.assertFalse(payload["explicit_seed"])

    def test_status_derivation(self):
        self.assertEqual(gc._derive_status("上班打卡", "09:30"), "迟到")
        self.assertEqual(gc._derive_status("上班打卡", "08:30"), "正常")
        self.assertEqual(gc._derive_status("下班打卡", "17:40"), "早退")
        self.assertEqual(gc._derive_status("外勤打卡", "12:00"), "外勤")


class RenderTests(unittest.TestCase):
    def test_markdown_has_table_and_fields(self):
        payload = gc.build_record(seed=42)
        md = gc.render_markdown(payload)
        self.assertIn("# 打卡记录", md)
        self.assertIn("| 字段 | 内容 |", md)
        for label in ("记录编号", "打卡日期", "打卡类型", "打卡时间", "打卡地点", "打卡方式", "打卡状态", "备注"):
            self.assertIn(label, md)

    def test_text_render(self):
        payload = gc.build_record(seed=42)
        text = gc.render_text(payload)
        self.assertIn("打卡记录", text)
        self.assertIn(payload["record"]["location"], text)

    def test_json_render_round_trips(self):
        payload = gc.build_record(seed=42)
        parsed = json.loads(gc.render_json(payload))
        self.assertEqual(parsed["record"]["record_id"], payload["record"]["record_id"])
        self.assertEqual(parsed["seed"], 42)

    def test_render_dispatches_formats(self):
        payload = gc.build_record(seed=42)
        self.assertEqual(gc.render(payload, "json"), gc.render_json(payload))
        self.assertEqual(gc.render(payload, "text"), gc.render_text(payload))
        self.assertEqual(gc.render(payload, "markdown"), gc.render_markdown(payload))


class CliTests(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT_PATH, *args],
            capture_output=True,
            text=True,
            cwd=SKILL_DIR,
        )

    def test_cli_default_run_ok(self):
        result = self._run("--seed", "555")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("打卡记录", result.stdout)

    def test_cli_seed_reproducible(self):
        first = self._run("--seed", "555", "--format", "markdown")
        second = self._run("--seed", "555", "--format", "markdown")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_cli_json_is_parseable(self):
        result = self._run("--seed", "9", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertIn("record", parsed)
        self.assertEqual(parsed["record"]["date"], gc._dt.date.today().isoformat())

    def test_cli_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "record.md")
            result = self._run("--seed", "3", "--output", out)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.exists(out))
            with open(out, encoding="utf-8") as handle:
                self.assertIn("打卡记录", handle.read())

    def test_cli_help(self):
        result = self._run("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--seed", result.stdout)

    def test_cli_bad_data_exit_2(self):
        result = self._run("--seed", "1", "--data", os.path.join(HERE, "nope.json"))
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)