#!/usr/bin/env python3
"""Unit tests for scripts/generate_weekly_menu.py.

Run from the skill directory:
    python3 -m unittest discover -s tests -v
or:
    python3 tests/test_generate_weekly_menu.py
"""

import importlib.util
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
SCRIPT_PATH = os.path.join(SCRIPTS_DIR, "generate_weekly_menu.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_weekly_menu", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gwm = _load_module()


class LoadDishesTests(unittest.TestCase):
    def test_min_pool_size(self):
        dishes = gwm.load_dishes()
        for meal in ("breakfast", "lunch", "dinner"):
            self.assertIn(meal, dishes)
            self.assertGreaterEqual(
                len(dishes[meal]), 7, "%s needs at least 7 dishes for a duplicate-free week" % meal
            )

    def test_missing_file_raises(self):
        with self.assertRaises(OSError):
            gwm.load_dishes(os.path.join(HERE, "does-not-exist.json"))


class PickWeekTests(unittest.TestCase):
    def test_default_week_shape(self):
        week = gwm.pick_week(seed=1234)
        self.assertEqual(week["days"], 7)
        self.assertEqual(list(week["meals"]), ["breakfast", "lunch", "dinner"])
        self.assertEqual(len(week["week"]), 7)
        for day in week["week"]:
            self.assertEqual(set(day["meals"]), {"breakfast", "lunch", "dinner"})
            for meal in ("breakfast", "lunch", "dinner"):
                self.assertTrue(day["meals"][meal])

    def test_same_meal_no_duplicates_within_week(self):
        week = gwm.pick_week(seed=99)
        for meal in ("breakfast", "lunch", "dinner"):
            picked = [day["meals"][meal] for day in week["week"]]
            self.assertEqual(len(picked), len(set(picked)), "duplicate %s dish: %s" % (meal, picked))
        self.assertEqual(week["degraded"], [])

    def test_same_seed_is_reproducible(self):
        first = gwm.pick_week(seed=20240501)
        second = gwm.pick_week(seed=20240501)
        self.assertEqual(gwm.render_markdown(first), gwm.render_markdown(second))
        self.assertEqual(first["week"], second["week"])

    def test_no_seed_generates_concrete_seed(self):
        week = gwm.pick_week()
        self.assertIsInstance(week["seed"], int)
        self.assertFalse(week["explicit_seed"])

    def test_custom_days_and_meals(self):
        week = gwm.pick_week(seed=7, days=3, meals=["brunch", "supper"], dishes={
            "brunch": ["a", "b", "c"],
            "supper": ["x", "y", "z"],
        })
        self.assertEqual(week["days"], 3)
        self.assertEqual(list(week["meals"]), ["brunch", "supper"])
        picked = [day["meals"]["brunch"] for day in week["week"]]
        self.assertEqual(len(picked), len(set(picked)))

    def test_small_pool_degrades_gracefully(self):
        week = gwm.pick_week(seed=3, days=5, meals=["lunch"], dishes={"lunch": ["only"]})
        self.assertEqual(len(week["week"]), 5)
        self.assertIn("lunch", week["degraded"])
        self.assertTrue(all(day["meals"]["lunch"] == "only" for day in week["week"]))

    def test_invalid_days_rejected(self):
        with self.assertRaises(ValueError):
            gwm.pick_week(seed=1, days=0)


class RenderTests(unittest.TestCase):
    def test_markdown_contains_days_and_meals(self):
        week = gwm.pick_week(seed=42)
        md = gwm.render_markdown(week)
        self.assertIn("# Weekly Menu", md)
        for day in range(1, 8):
            self.assertIn("Day %d" % day, md)
        for label in ("Breakfast", "Lunch", "Dinner"):
            self.assertIn(label, md)

    def test_text_render(self):
        week = gwm.pick_week(seed=42, days=2)
        text = gwm.render_text(week)
        self.assertIn("Weekly Menu", text)
        self.assertIn("Day 1", text)
        self.assertIn("Day 2", text)

    def test_json_render_round_trips(self):
        week = gwm.pick_week(seed=42)
        parsed = json.loads(gwm.render(week, "json"))
        self.assertEqual(parsed["days"], 7)
        self.assertEqual(len(parsed["week"]), 7)


class CliTests(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT_PATH, *args],
            capture_output=True,
            text=True,
            cwd=SKILL_DIR,
        )

    def test_cli_markdown_seed_reproducible(self):
        first = self._run("--seed", "555", "--format", "markdown")
        second = self._run("--seed", "555", "--format", "markdown")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_cli_text_default_days(self):
        result = self._run("--seed", "1", "--format", "text")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Day 7", result.stdout)

    def test_cli_custom_days_and_meals(self):
        result = self._run("--seed", "2", "--days", "2", "--meals", "breakfast,dinner", "--format", "text")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Day 2", result.stdout)
        self.assertNotIn("Lunch", result.stdout)
        self.assertNotIn("Day 3", result.stdout)

    def test_cli_help(self):
        result = self._run("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--seed", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)