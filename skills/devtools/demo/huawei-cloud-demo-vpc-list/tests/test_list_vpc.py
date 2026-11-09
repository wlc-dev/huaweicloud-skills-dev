#!/usr/bin/env python3
"""离线单测：用假 hcloud 替身覆盖输出模式、翻页、守卫与错误分类。

不访问网络、不需要华为云凭据。
运行：python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import list_vpc  # noqa: E402

FAKE = str(SKILL_DIR / "tests" / "fake_hcloud.sh")


def run(argv, mode=None):
    """调用 main()，返回 (rc, stdout, stderr)。"""
    env_backup = os.environ.get("FAKE_MODE")
    if mode is not None:
        os.environ["FAKE_MODE"] = mode
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = list_vpc.main(list(argv) + ["--hcloud-bin", FAKE])
    finally:
        if mode is not None:
            if env_backup is None:
                os.environ.pop("FAKE_MODE", None)
            else:
                os.environ["FAKE_MODE"] = env_backup
    return rc, out.getvalue(), err.getvalue()


class TestCommandConstruction(unittest.TestCase):
    def test_only_listvpcs_can_be_built(self):
        cmd = list_vpc.build_command("/bin/hcloud", "cn-north-4", 100, None)
        self.assertEqual(cmd[:3], ["/bin/hcloud", "VPC", "ListVpcs"])
        self.assertIn("--cli-region=cn-north-4", cmd)
        self.assertNotIn("--marker", " ".join(cmd))

    def test_marker_appended_only_when_present(self):
        cmd = list_vpc.build_command("/bin/hcloud", "cn-south-1", 10, "vpc-0001")
        self.assertIn("--marker=vpc-0001", cmd)


class TestWriteGuard(unittest.TestCase):
    def assert_blocked(self, argv):
        rc, out, err = run(argv, "ok")
        self.assertEqual(rc, 1)
        self.assertIn("已被守卫拦截", err)
        self.assertEqual(out, "")  # 未执行任何查询、未产生输出

    def test_blocks_mutating_positional(self):
        for word in ("delete", "create", "update", "associate", "release", "change"):
            with self.subTest(word=word):
                self.assert_blocked(["--region", "cn-north-4", word])

    def test_blocks_mutating_flag(self):
        self.assert_blocked(["--region", "cn-north-4", "--delete-vpc"])

    def test_read_only_arguments_pass(self):
        rc, out, err = run(["--region", "cn-north-4", "--json"], "ok")
        self.assertEqual(rc, 0, err)
        self.assertIn("demo-vpc-a", out)


class TestOutputModes(unittest.TestCase):
    def test_table_default(self):
        rc, out, err = run([], "ok")
        self.assertEqual(rc, 0, err)
        self.assertIn("id", out)
        self.assertIn("demo-vpc-a", out)
        self.assertIn("192.168.0.0/16", out)
        self.assertIn("共 2 个 VPC", out)

    def test_names_only(self):
        rc, out, err = run(["--names-only"], "ok")
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip().splitlines(), ["demo-vpc-a", "demo-vpc-b"])

    def test_json(self):
        rc, out, err = run(["--json"], "ok")
        self.assertEqual(rc, 0, err)
        self.assertIn('"id": "vpc-0001"', out)

    def test_empty_list(self):
        rc, out, err = run([], "empty")
        self.assertEqual(rc, 0)
        self.assertIn("无虚拟私有云（VPC）", out)

    def test_missing_fields_render_dash(self):
        rc, out, err = run([], "paging")
        self.assertEqual(rc, 0, err)
        self.assertIn("-", out)


class TestPaging(unittest.TestCase):
    def test_marker_paging_collects_both_pages(self):
        rc, out, err = run(["--json"], "paging")
        self.assertEqual(rc, 0, err)
        self.assertIn("vpc-0001", out)
        self.assertIn("vpc-0002", out)

    def test_max_pages_stops_paging(self):
        rc, out, err = run(["--json", "--max-pages", "1"], "paging")
        self.assertEqual(rc, 0, err)
        self.assertIn("vpc-0001", out)
        self.assertNotIn("vpc-0002", out)


class TestErrorClassification(unittest.TestCase):
    def test_403_reports_iam_hint(self):
        rc, out, err = run([], "403")
        self.assertEqual(rc, 1)
        self.assertIn("vpc:vpcs:list", err)

    def test_use_error_reports_parameter_hint(self):
        rc, out, err = run([], "use_error")
        self.assertEqual(rc, 1)
        self.assertIn("hcloud 参数错误", err)

    def test_missing_cli_reports_install_hint(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = list_vpc.main(["--hcloud-bin", str(SKILL_DIR / "does-not-exist")])
        self.assertEqual(rc, 1)
        self.assertIn("KooCLI（hcloud）", err.getvalue())

    def test_broken_json_reports_api_error(self):
        rc, out, err = run([], "broken")
        self.assertEqual(rc, 1)
        self.assertIn("[错误]", err)

    def test_limit_out_of_range(self):
        rc, out, err = run(["--limit", "0"], "ok")
        self.assertEqual(rc, 1)
        self.assertIn("--limit", err)


class TestNoSecretsTouched(unittest.TestCase):
    def test_script_source_has_no_credential_literals(self):
        src = (SCRIPTS_DIR / "list_vpc.py").read_text(encoding="utf-8")
        needles = [
            "AK" + "IA",
            "SECRET" + "_KEY=",
            "access" + "_key=",
            "sk" + "=",
        ]
        for needle in needles:
            self.assertNotIn(needle, src)


if __name__ == "__main__":
    unittest.main()