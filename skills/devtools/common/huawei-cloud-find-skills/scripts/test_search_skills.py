#!/usr/bin/env python3
"""Offline regression tests for search-skills.py (Issue #186).

The tests import the search script directly and inject a fixture index/cn-en-map,
so no network access is required. Only the Python standard library is used.

Run with:
    python3 -m unittest scripts/test_search_skills.py -v
"""

import contextlib
import copy
import importlib.util
import io
import pathlib
import re
import sys
import unittest
from unittest import mock

SCRIPT_PATH = pathlib.Path(__file__).with_name("search-skills.py")
_spec = importlib.util.spec_from_file_location("find_skills_search", str(SCRIPT_PATH))
search = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(search)


FIXTURE_INDEX = {
    "categories": ["computing", "container"],
    "skills": [
        {
            "name": "huawei-cloud-computing-query",
            "category": "computing/computing",
            "service": "computing",
            "services": ["ECS", "BMS", "IMS", "AS", "CCE", "EVS"],
            "type": "query",
            "description": "统一查询华为云计算类资源：ECS、BMS、IMS、AS、CCE、EVS。",
            "triggers": [
                "查询 CCE 集群",
                "CCE 集群查询",
                "ECS 弹性云服务器查询",
                "BMS 裸金属服务器查询",
                "EVS 云硬盘查询",
            ],
        },
        {
            "name": "huawei-cloud-cce-node-manage",
            "category": "container/cce",
            "service": "cce",
            "services": ["CCE"],
            "type": "manage",
            "description": "管理 CCE 节点生命周期，支持扩容与缩容。",
            "triggers": ["CCE 节点管理", "CCE 集群运维"],
        },
        {
            # services/type intentionally omitted: must fall back to name inference.
            "name": "huawei-cloud-ecs-list",
            "category": "computing/ecs",
            "service": "ecs",
            "description": "查询 ECS 云服务器列表。",
            "triggers": ["ECS 列表"],
        },
        {
            # both service and services omitted: name inference only.
            "name": "huawei-cloud-obs-statistics",
            "category": "storage/obs",
            "description": "统计 OBS 桶容量。",
            "triggers": ["OBS 统计"],
        },
    ],
}

FIXTURE_CN_EN_MAP = {
    "弹性云服务器": "ecs",
    "云服务器": "ecs",
    "云容器引擎": "cce",
}


class SearchScriptTestCase(unittest.TestCase):
    def run_cli(self, argv, index=None, cn_en_map=None):
        index = FIXTURE_INDEX if index is None else index
        cn_en_map = FIXTURE_CN_EN_MAP if cn_en_map is None else cn_en_map

        def fake_loader(filename, label):
            if filename == "index.json":
                return copy.deepcopy(index), "fixture"
            if filename == "cn-en-map.json":
                return copy.deepcopy(cn_en_map), "fixture"
            raise AssertionError(f"unexpected fixture file: {filename} ({label})")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(search, "load_json_dual_source", side_effect=fake_loader), \
                mock.patch.object(search, "report_search_results_impressions", return_value=0), \
                mock.patch.object(sys, "argv", ["search-skills.py"] + list(argv)), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            rc = search.main()
        return rc, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def first_result_line(output):
        for line in output.splitlines():
            if re.match(r"^  \[\d+pts\] ", line):
                return line
        return ""

    @staticmethod
    def coverage_section(output):
        marker = "Other skills covering 'CCE'"
        if marker not in output:
            return ""
        return output.split(marker, 1)[1]


class KeywordCceTest(SearchScriptTestCase):
    def test_computing_query_shows_coverage_type_and_group(self):
        rc, output, _ = self.run_cli(["-k", "CCE"])
        self.assertEqual(rc, 0)

        row = next(
            (line for line in output.splitlines()
             if "huawei-cloud-computing-query" in line and line.lstrip().startswith("[")),
            "",
        )
        self.assertIn("覆盖: ECS+BMS+IMS+AS+CCE+EVS", row)
        self.assertIn("[只读查询]", row)

        section = self.coverage_section(output)
        self.assertIn("huawei-cloud-computing-query", section)
        self.assertIn("覆盖: ECS+BMS+IMS+AS+CCE+EVS", section)

    def test_cce_specific_manage_skill_outranks_but_does_not_hide_coverage(self):
        _, output, _ = self.run_cli(["-k", "CCE"])
        main_part = output.split("Other skills covering 'CCE'", 1)[0]
        lines = [line for line in main_part.splitlines() if line.startswith("  [")]
        self.assertTrue(lines)
        self.assertIn("huawei-cloud-cce-node-manage", lines[0])
        self.assertTrue(any("huawei-cloud-computing-query" in line for line in lines[1:]))

    def test_query_cce_cluster_keeps_computing_query_first(self):
        rc, output, _ = self.run_cli(["-k", "查询 CCE 集群"])
        self.assertEqual(rc, 0)
        first = self.first_result_line(output)
        self.assertIn("huawei-cloud-computing-query", first)
        self.assertIn("matched: CCE,查询,集群", first)


class NameInferenceFallbackTest(unittest.TestCase):
    def test_missing_services_falls_back_to_single_service(self):
        fields = search.extract_skill_fields({
            "name": "huawei-cloud-ecs-list",
            "category": "computing/ecs",
            "service": "ecs",
            "description": "查询 ECS 云服务器列表。",
            "triggers": ["ECS 列表"],
        })
        self.assertEqual(fields["services"], ["ecs"])
        self.assertEqual(fields["type"], "")
        self.assertEqual(search.resolve_skill_type(fields), "query")

        rendered = search.format_services(fields)
        self.assertIn("[只读查询]", rendered)
        self.assertNotIn("覆盖:", rendered)

    def test_missing_type_infers_manage_from_name(self):
        fields = search.extract_skill_fields({
            "name": "huawei-cloud-cce-node-manage",
            "category": "container/cce",
            "service": "cce",
            "description": "管理 CCE 节点。",
        })
        self.assertEqual(search.resolve_skill_type(fields), "manage")
        self.assertIn("[管理]", search.format_services(fields))

    def test_index_type_takes_priority_over_name(self):
        fields = search.extract_skill_fields({
            "name": "huawei-cloud-ecs-list",
            "category": "computing/ecs",
            "service": "ecs",
            "type": "manage",
        })
        self.assertEqual(search.resolve_skill_type(fields), "manage")

    def test_unknown_name_gets_no_type_label(self):
        fields = search.extract_skill_fields({
            "name": "huawei-cloud-obs-statistics",
            "category": "storage/obs",
            "description": "统计 OBS 桶容量。",
        })
        self.assertEqual(fields["services"], [])
        self.assertEqual(search.resolve_skill_type(fields), "")
        self.assertEqual(search.format_services(fields), "")

    def test_multi_service_order_is_preserved(self):
        fields = search.extract_skill_fields({
            "name": "huawei-cloud-computing-query",
            "category": "computing/computing",
            "service": "computing",
            "services": ["ECS", "BMS", "IMS", "AS", "CCE", "EVS"],
            "type": "query",
        })
        self.assertEqual(
            search.format_services(fields),
            " 覆盖: ECS+BMS+IMS+AS+CCE+EVS [只读查询]",
        )


class NoResultFallbackTest(SearchScriptTestCase):
    def test_keyword_without_match_prints_fallback_suggestions(self):
        rc, output, _ = self.run_cli(["-k", "zzz-nonexistent"])
        self.assertEqual(rc, 0)
        self.assertIn("No results for keyword='zzz-nonexistent'", output)
        self.assertIn("Fallback suggestions:", output)

    def test_category_filter_does_not_fall_back(self):
        rc, output, _ = self.run_cli(["-k", "zzz-nonexistent", "-c", "container"])
        self.assertEqual(rc, 0)
        self.assertIn("Category 'container' exists", output)
        self.assertNotIn("Fallback suggestions:", output)

    def test_unknown_category_does_not_fall_back(self):
        rc, output, _ = self.run_cli(["-k", "zzz-nonexistent", "-c", "no-such-category"])
        self.assertEqual(rc, 0)
        self.assertIn("was not found in the index", output)
        self.assertNotIn("Fallback suggestions:", output)

    def test_top_level_category_prefix_matches_subcategories(self):
        rc, output, _ = self.run_cli(["-c", "container"])
        self.assertEqual(rc, 0)
        self.assertIn("huawei-cloud-cce-node-manage", output)
        self.assertNotIn("huawei-cloud-ecs-list", output)


if __name__ == "__main__":
    unittest.main()