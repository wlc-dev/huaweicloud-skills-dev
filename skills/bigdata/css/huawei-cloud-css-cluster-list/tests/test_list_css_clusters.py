# -*- coding: utf-8 -*-
"""Offline unit tests for huawei-cloud-css-cluster-list.

The hcloud subprocess is mocked; the SDK fallback is exercised with a fake
``huaweicloudsdkcss`` module injected into ``sys.modules``. No credentials, no
network and no real cloud call are used.
"""

import json
import os
import subprocess
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import list_css_clusters as css  # noqa: E402
from list_css_clusters import (  # noqa: E402
    ALLOWED_OPERATIONS,
    ApiError,
    AuthError,
    ConfigError,
    GuardError,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    build_detail_command,
    build_list_command,
    build_volume_command,
    clamp_limit,
    classify_hcloud_failure,
    extract_clusters,
    extract_disk_info,
    extract_json,
    extract_total,
    filter_clusters,
    guard_action,
    guard_operation,
    guard_write_intent,
    list_clusters,
    list_clusters_via_sdk,
    main,
    normalize_cluster,
    normalize_node,
    render_cluster_view,
    render_node_view,
    render_simple_view,
    render_table,
    scannable_argv,
    show_cluster,
    show_cluster_via_sdk,
    show_volume_usage,
    show_volume_usage_via_sdk,
)

CLUSTER_1 = {
    "id": "c-0001",
    "name": "css-prod-01",
    "status": "200",
    "datastore": {"type": "elasticsearch", "version": "7.10.2"},
    "instances": [
        {
            "id": "n-0001",
            "name": "css-prod-01-ess-1-1",
            "type": "ess",
            "status": "200",
            "specCode": "ess.spec-4u16g",
            "ip": "192.168.0.10",
            "azCode": "cn-north-4a",
            "volume": {"type": "COMMON", "size": 40},
        }
    ],
    "vpcId": "vpc-1",
    "subnetId": "subnet-1",
    "securityGroupId": "sg-1",
    "created": "2024-01-01T00:00:00",
}

CLUSTER_2 = {
    "id": "c-0002",
    "name": "css-test-02",
    "status": "303",
    "datastore": {"type": "opensearch", "version": "2.17.1"},
    "instances": [
        {
            "id": "n-0002",
            "name": "css-test-02-ess-1-1",
            "type": "ess",
            "status": "303",
            "specCode": "ess.spec-8u32g",
            "ip": "192.168.0.11",
            "azCode": "cn-north-4b",
            "volume": {"type": "COMMON", "size": 80},
        }
    ],
    "vpcId": "vpc-2",
    "subnetId": "subnet-2",
    "securityGroupId": "sg-2",
    "created": "2024-02-02T00:00:00",
}


def hcloud_result(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["hcloud"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class FakeRunner:
    """subprocess.run fake returning canned hcloud outputs per call."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if not self.results:
            raise AssertionError("unexpected extra hcloud call: %s" % cmd)
        out = self.results.pop(0)
        if isinstance(out, Exception):
            raise out
        return hcloud_result(*out)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def to_json_object(self):
        return self._data


class FakeClient:
    def __init__(self, list_pages=None, detail=None, volume=None):
        self.list_pages = list(list_pages or [])
        self.detail = detail or {}
        self.volume = volume or {}
        self.requests = []

    def list_clusters_details(self, request):
        self.requests.append(request)
        return FakeResponse(self.list_pages.pop(0))

    def show_cluster_detail(self, request):
        self.requests.append(request)
        return FakeResponse(self.detail)

    def show_cluster_volume_usage(self, request):
        self.requests.append(request)
        return FakeResponse(self.volume)


def fake_css_modules():
    """Build fake ``huaweicloudsdkcss.v1`` modules for the SDK fallback tests."""
    pkg = types.ModuleType("huaweicloudsdkcss")
    v1 = types.ModuleType("huaweicloudsdkcss.v1")
    v1.ListClustersDetailsRequest = (
        lambda offset=None, limit=None, datastore_type=None: {
            "offset": offset, "limit": limit, "datastore_type": datastore_type})
    v1.ShowClusterDetailRequest = (
        lambda cluster_id=None: {"cluster_id": cluster_id})
    v1.ShowClusterVolumeUsageRequest = (
        lambda cluster_id=None: {"cluster_id": cluster_id})
    pkg.v1 = v1
    return {"huaweicloudsdkcss": pkg, "huaweicloudsdkcss.v1": v1}


class base_env(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"CSS_LIST_HCLOUD_BIN": "hcloud"})
        patcher.start()
        self.addCleanup(patcher.stop)


class TestWriteIntentGuard(unittest.TestCase):
    def test_read_intent_passes(self):
        self.assertFalse(guard_write_intent("--region cn-north-4 --table"))
        self.assertFalse(guard_write_intent("--status abnormal --json"))
        self.assertFalse(guard_write_intent("list clusters details"))

    def test_create_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("CreateCluster css-new")

    def test_delete_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("--operation DeleteCluster")

    def test_mutating_verbs_blocked(self):
        for text in ("restart css-01", "reboot css-01", "scale out",
                     "shrink cluster", "create snapshot", "delete snapshot",
                     "update name", "modify cluster"):
            with self.assertRaises(GuardError):
                guard_write_intent(text)

    def test_normalized_separators_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("--create-cluster")
        with self.assertRaises(GuardError):
            guard_write_intent("restart_cluster_name")

    def test_operation_guard(self):
        for op in ALLOWED_OPERATIONS:
            self.assertTrue(guard_operation(op))
        with self.assertRaises(GuardError):
            guard_operation("DeleteCluster")
        with self.assertRaises(GuardError):
            guard_operation("RebootCluster")

    def test_action_guard(self):
        self.assertTrue(guard_action(None))
        self.assertTrue(guard_action("list"))
        with self.assertRaises(GuardError):
            guard_action("delete")

    def test_status_value_not_scanned(self):
        argv = ["--status", "creating", "--name", "css-prod"]
        guard_write_intent(scannable_argv(argv))  # must not raise

    def test_name_value_scanned(self):
        argv = ["--name", "create-me"]
        with self.assertRaises(GuardError):
            guard_write_intent(scannable_argv(argv))

    def test_equals_form_status_stripped(self):
        guard_write_intent(scannable_argv(["--status=creating"]))
        with self.assertRaises(GuardError):
            guard_write_intent(scannable_argv(["--name=create-me"]))

    def test_action_value_scanned(self):
        with self.assertRaises(GuardError):
            guard_write_intent(scannable_argv(["--action", "delete"]))


class TestCommandConstruction(unittest.TestCase):
    def test_list_basic(self):
        argv = build_list_command("cn-north-4")
        self.assertEqual(argv[0], "CSS")
        self.assertEqual(argv[1], "ListClustersDetails")
        self.assertIn("--cli-region=cn-north-4", argv)
        self.assertIn("--limit=%d" % DEFAULT_LIMIT, argv)
        self.assertIn("--offset=1", argv)

    def test_list_filters(self):
        argv = build_list_command("cn-south-1", limit=50, offset=51,
                                  datastore_type="opensearch")
        self.assertIn("--cli-region=cn-south-1", argv)
        self.assertIn("--limit=50", argv)
        self.assertIn("--offset=51", argv)
        self.assertIn("--datastoreType=opensearch", argv)

    def test_detail(self):
        argv = build_detail_command("cn-north-4", "abc-123")
        self.assertEqual(argv[:2], ["CSS", "ShowClusterDetail"])
        self.assertIn("--cluster_id=abc-123", argv)

    def test_volume(self):
        argv = build_volume_command("cn-north-4", "abc-123")
        self.assertEqual(argv[:2], ["CSS", "ShowClusterVolumeUsage"])
        self.assertIn("--cluster_id=abc-123", argv)

    def test_detail_requires_cluster_id(self):
        with self.assertRaises(ConfigError):
            build_detail_command("cn-north-4", "")

    def test_volume_requires_cluster_id(self):
        with self.assertRaises(ConfigError):
            build_volume_command("cn-north-4", None)

    def test_only_read_operations_built(self):
        for argv in (build_list_command("cn-north-4"),
                     build_detail_command("cn-north-4", "x"),
                     build_volume_command("cn-north-4", "x")):
            self.assertIn(argv[1], ALLOWED_OPERATIONS)


class TestClampLimit(unittest.TestCase):
    def test_default(self):
        self.assertEqual(clamp_limit(10), (10, False))

    def test_low(self):
        self.assertEqual(clamp_limit(0), (1, True))
        self.assertEqual(clamp_limit(-5), (1, True))

    def test_high(self):
        self.assertEqual(clamp_limit(500), (MAX_LIMIT, True))

    def test_bad_value(self):
        self.assertEqual(clamp_limit("abc"), (DEFAULT_LIMIT, False))


class TestExtract(unittest.TestCase):
    def test_json_plain(self):
        self.assertEqual(extract_json('{"clusters": []}'), {"clusters": []})

    def test_json_noise(self):
        self.assertEqual(extract_json('WARNING noise\n{"a": 1}\n'), {"a": 1})

    def test_json_invalid(self):
        with self.assertRaises(ApiError):
            extract_json("<html>not json</html>")

    def test_clusters(self):
        self.assertEqual(extract_clusters({"clusters": [CLUSTER_1]}), [CLUSTER_1])
        self.assertEqual(extract_clusters([CLUSTER_1]), [CLUSTER_1])
        self.assertEqual(extract_clusters({"totalSize": 0}), [])

    def test_total(self):
        self.assertEqual(extract_total({"totalSize": 3}), 3)
        self.assertEqual(extract_total({"totalSize": "3"}), 3)
        self.assertIsNone(extract_total({"clusters": []}))

    def test_disk_info_direct(self):
        infos = [{"id": "n-1", "percentage": "5.16"}]
        self.assertEqual(extract_disk_info({"diskInfoList": infos}), infos)
        self.assertEqual(extract_disk_info(infos), infos)

    def test_disk_info_unwrap_body(self):
        infos = [{"id": "n-1"}]
        self.assertEqual(extract_disk_info({"body": {"diskInfoList": infos}}), infos)


class TestPayloadError(unittest.TestCase):
    def test_css_err_envelope(self):
        text = css._payload_error(
            {"errCode": "CSS.0051", "externalMessage": "not allowed"})
        self.assertIn("CSS.0051", text)

    def test_snake_error(self):
        text = css._payload_error(
            {"error_code": "CSS.0045", "error_msg": "not found"})
        self.assertIn("CSS.0045", text)

    def test_nested_error(self):
        text = css._payload_error({"error": {"code": "403", "message": "denied"}})
        self.assertIn("403", text)

    def test_no_error(self):
        self.assertIsNone(css._payload_error({"clusters": []}))


class TestClassifyFailure(unittest.TestCase):
    def test_missing_credentials(self):
        err = classify_hcloud_failure(
            "", "ERROR: cli-ak is empty, please run hcloud configure", 1)
        self.assertIsInstance(err, ConfigError)
        self.assertIn("AK/SK", str(err))

    def test_auth_403(self):
        err = classify_hcloud_failure("", "403 Forbidden", 1)
        self.assertIsInstance(err, AuthError)
        self.assertIn("403", str(err))

    def test_css_policy_denied(self):
        err = classify_hcloud_failure(
            "", "CSS.0051 : The current policy does not allow the "
                "css:cluster:list operation.", 0)
        self.assertIsInstance(err, AuthError)
        self.assertIn("css:cluster:list", str(err))

    def test_use_error(self):
        err = classify_hcloud_failure("[USE_ERROR]unknown param", "", 1)
        self.assertIsInstance(err, ApiError)
        self.assertIn("参数", str(err))

    def test_generic(self):
        err = classify_hcloud_failure("", "boom", 2)
        self.assertIsInstance(err, ApiError)


class TestListClusters(base_env):
    def test_single_page(self):
        fake = FakeRunner([(
            json.dumps({"clusters": [CLUSTER_1], "totalSize": 1}), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            clusters = list_clusters("cn-north-4")
        self.assertEqual(clusters, [CLUSTER_1])
        self.assertEqual(len(fake.calls), 1)

    def test_pagination_via_total(self):
        page1 = {"clusters": [CLUSTER_1], "totalSize": 2}
        page2 = {"clusters": [CLUSTER_2], "totalSize": 2}
        fake = FakeRunner([(json.dumps(page1), "", 0),
                           (json.dumps(page2), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            clusters = list_clusters("cn-north-4", limit=1)
        self.assertEqual(clusters, [CLUSTER_1, CLUSTER_2])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("--offset=2", fake.calls[1])

    def test_pagination_full_page_without_total(self):
        page1 = {"clusters": [CLUSTER_1]}
        page2 = {"clusters": []}
        fake = FakeRunner([(json.dumps(page1), "", 0),
                           (json.dumps(page2), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            clusters = list_clusters("cn-north-4", limit=1)
        self.assertEqual(clusters, [CLUSTER_1])

    def test_dedupe(self):
        page1 = {"clusters": [CLUSTER_1], "totalSize": 2}
        page2 = {"clusters": [CLUSTER_1, CLUSTER_2], "totalSize": 2}
        fake = FakeRunner([(json.dumps(page1), "", 0),
                           (json.dumps(page2), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            clusters = list_clusters("cn-north-4", limit=1)
        self.assertEqual([c["id"] for c in clusters], ["c-0001", "c-0002"])

    def test_datastore_type_forwarded(self):
        fake = FakeRunner([(
            json.dumps({"clusters": [CLUSTER_1], "totalSize": 1}), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            list_clusters("cn-north-4", datastore_type="elasticsearch")
        self.assertIn("--datastoreType=elasticsearch", fake.calls[0])

    def test_error_envelope_rc0_raises(self):
        fake = FakeRunner([(
            json.dumps({"errCode": "CSS.0051",
                        "externalMessage": "policy denied"}), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            with self.assertRaises(AuthError):
                list_clusters("cn-north-4")

    def test_nonzero_403(self):
        fake = FakeRunner([("", "403 Forbidden", 1)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            with self.assertRaises(AuthError):
                list_clusters("cn-north-4")

    def test_hcloud_missing_falls_back(self):
        with mock.patch("list_css_clusters.run_hcloud",
                        side_effect=ConfigError("hcloud missing")), \
                mock.patch("list_css_clusters.list_clusters_via_sdk",
                           return_value=[CLUSTER_1]) as sdk:
            clusters = list_clusters("cn-north-4")
        self.assertEqual(clusters, [CLUSTER_1])
        sdk.assert_called_once()


class TestSdkFallback(unittest.TestCase):
    def test_list_via_fake_sdk(self):
        client = FakeClient(list_pages=[
            {"clusters": [CLUSTER_1], "totalSize": 2},
            {"clusters": [CLUSTER_2], "totalSize": 2},
        ])
        with mock.patch.dict(sys.modules, fake_css_modules()), \
                mock.patch("list_css_clusters._sdk_client", return_value=client), \
                mock.patch("list_css_clusters._sdk_call",
                           side_effect=lambda fn, req: fn(req)):
            clusters = list_clusters_via_sdk("cn-north-4", limit=1)
        self.assertEqual([c["id"] for c in clusters], ["c-0001", "c-0002"])
        self.assertEqual(client.requests[0]["offset"], 1)
        self.assertEqual(client.requests[1]["offset"], 2)

    def test_detail_via_fake_sdk(self):
        client = FakeClient(detail=CLUSTER_1)
        with mock.patch.dict(sys.modules, fake_css_modules()), \
                mock.patch("list_css_clusters._sdk_client", return_value=client), \
                mock.patch("list_css_clusters._sdk_call",
                           side_effect=lambda fn, req: fn(req)):
            detail = show_cluster_via_sdk("cn-north-4", "c-0001")
        self.assertEqual(detail, CLUSTER_1)

    def test_volume_via_fake_sdk(self):
        infos = [{"id": "n-0001", "percentage": "81.5"}]
        client = FakeClient(volume={"diskInfoList": infos})
        with mock.patch.dict(sys.modules, fake_css_modules()), \
                mock.patch("list_css_clusters._sdk_client", return_value=client), \
                mock.patch("list_css_clusters._sdk_call",
                           side_effect=lambda fn, req: fn(req)):
            result = show_volume_usage_via_sdk("cn-north-4", "c-0001")
        self.assertEqual(result, infos)


class TestShowDetail(base_env):
    def test_cli_detail(self):
        fake = FakeRunner([(json.dumps(CLUSTER_1), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            detail = show_cluster("cn-north-4", "c-0001")
        self.assertEqual(detail["id"], "c-0001")

    def test_empty_payload_not_found(self):
        fake = FakeRunner([(json.dumps({}), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            with self.assertRaises(ApiError) as ctx:
                show_cluster("cn-north-4", "missing")
        self.assertIn("不存在", str(ctx.exception))

    def test_sdk_fallback_detail(self):
        with mock.patch("list_css_clusters.run_hcloud",
                        side_effect=ConfigError("no hcloud")), \
                mock.patch("list_css_clusters.show_cluster_via_sdk",
                           return_value=CLUSTER_1):
            detail = show_cluster("cn-north-4", "c-0001")
        self.assertEqual(detail["id"], "c-0001")

    def test_volume_usage_cli(self):
        infos = [{"id": "n-0001", "percentage": "5.16",
                  "diskCapacity": "97.86", "diskUsed": "5.05"}]
        fake = FakeRunner([(json.dumps({"diskInfoList": infos}), "", 0)])
        with mock.patch("list_css_clusters.subprocess.run", fake):
            result = show_volume_usage("cn-north-4", "c-0001")
        self.assertEqual(result, infos)


class TestNormalizeAndFilter(unittest.TestCase):
    def test_normalize_cluster_normal(self):
        cluster = normalize_cluster(CLUSTER_1, region="cn-north-4")
        self.assertFalse(cluster["abnormal"])
        self.assertEqual(cluster["datastore_type"], "elasticsearch")
        self.assertEqual(cluster["node_spec"], "ess.spec-4u16g")
        self.assertEqual(cluster["node_count"], 1)
        self.assertEqual(cluster["storage_gb"], 40)
        self.assertFalse(cluster["capacity_alert"])

    def test_normalize_cluster_abnormal_and_capacity(self):
        cluster = normalize_cluster(CLUSTER_2, region="cn-north-4",
                                    usage_percent=85.0)
        self.assertTrue(cluster["abnormal"])
        self.assertTrue(cluster["capacity_alert"])
        self.assertEqual(cluster["status_meaning"], "不可用（如创建失败）")

    def test_normalize_node_usage(self):
        node = normalize_node(
            CLUSTER_2["instances"][0], region="cn-north-4",
            usage={"percentage": "81.5", "diskCapacity": "100",
                   "diskUsed": "81.5"})
        self.assertTrue(node["abnormal"])
        self.assertEqual(node["usage_percent"], 81.5)
        self.assertEqual(node["disk_capacity"], "100")

    def test_filter_name_exact(self):
        result = filter_clusters([CLUSTER_1, CLUSTER_2], name="css-prod-01")
        self.assertEqual([c["id"] for c in result], ["c-0001"])

    def test_filter_name_fuzzy(self):
        result = filter_clusters([CLUSTER_1, CLUSTER_2], name="TEST", fuzzy=True)
        self.assertEqual([c["id"] for c in result], ["c-0002"])

    def test_filter_status_abnormal(self):
        result = filter_clusters([CLUSTER_1, CLUSTER_2], status="abnormal")
        self.assertEqual([c["id"] for c in result], ["c-0002"])

    def test_filter_status_numeric(self):
        result = filter_clusters([CLUSTER_1, CLUSTER_2], status="200")
        self.assertEqual([c["id"] for c in result], ["c-0001"])

    def test_filter_status_multi(self):
        result = filter_clusters([CLUSTER_1, CLUSTER_2], status="200,303")
        self.assertEqual(len(result), 2)


class TestRendering(unittest.TestCase):
    def test_render_table(self):
        table = render_table(["A", "B"], [["x", "y"], ["1", "2"]])
        self.assertIn("A  B", table)
        self.assertIn("x  y", table)

    def test_cluster_view_separates_abnormal(self):
        text = render_cluster_view("cn-north-4", [CLUSTER_1, CLUSTER_2],
                                   usage_lookup={"c-0002": 85.0})
        self.assertIn("css-prod-01", text)
        self.assertIn("⚠ 异常状态集群", text)
        self.assertIn("css-test-02", text)
        self.assertIn("容量使用率 ≥80%", text)
        self.assertIn("85.00%", text)

    def test_cluster_view_normal_only(self):
        text = render_cluster_view("cn-north-4", [CLUSTER_1])
        self.assertIn("共 1 个", text)
        self.assertNotIn("⚠ 异常状态集群", text)

    def test_node_view(self):
        infos = [{"id": "n-0002", "percentage": "81.5",
                  "diskCapacity": "100", "diskUsed": "81.5"}]
        text = render_node_view("cn-north-4", CLUSTER_2, infos)
        self.assertIn("节点列表", text)
        self.assertIn("⚠ 异常节点", text)
        self.assertIn("81.50%", text)

    def test_node_view_normal(self):
        text = render_node_view("cn-north-4", CLUSTER_1, [])
        self.assertIn("css-prod-01", text)
        self.assertNotIn("⚠ 异常节点", text)

    def test_simple_view_abnormal_section(self):
        text = render_simple_view("cn-north-4", [CLUSTER_1, CLUSTER_2])
        self.assertIn("css-prod-01", text)
        self.assertIn("⚠ 异常状态集群", text)


class TestMain(base_env):
    def _run(self, argv, results, extra_env=None):
        fake = FakeRunner(results)
        env = {"CSS_LIST_HCLOUD_BIN": "hcloud"}
        if extra_env:
            env.update(extra_env)
        with mock.patch.dict(os.environ, env), \
                mock.patch("list_css_clusters.subprocess.run", fake), \
                mock.patch("sys.stdout") as stdout, \
                mock.patch("sys.stderr") as stderr:
            rc = main(argv)
        out = "".join(c[0][0] for c in stdout.write.call_args_list)
        err = "".join(c[0][0] for c in stderr.write.call_args_list)
        return rc, out, err

    def test_default_output(self):
        rc, out, err = self._run(
            ["--region", "cn-north-4"],
            [(json.dumps({"clusters": [CLUSTER_1], "totalSize": 1}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("CSS 集群列表", out)
        self.assertIn("css-prod-01", out)
        self.assertEqual(err, "")

    def test_table_output_with_abnormal(self):
        # list call, then volume usage calls for each cluster
        rc, out, err = self._run(
            ["--table"],
            [
                (json.dumps({"clusters": [CLUSTER_1, CLUSTER_2],
                             "totalSize": 2}), "", 0),
                (json.dumps({"diskInfoList": [
                    {"id": "n-0001", "percentage": "5.16"}]}), "", 0),
                (json.dumps({"diskInfoList": [
                    {"id": "n-0002", "percentage": "85.0"}]}), "", 0),
            ])
        self.assertEqual(rc, 0)
        self.assertIn("磁盘使用率", out)
        self.assertIn("⚠ 异常状态集群", out)
        self.assertIn("85.00%", out)

    def test_table_usage_forbidden_degrades(self):
        auth = json.dumps({"errCode": "CSS.0051",
                           "externalMessage": "policy denied"})
        rc, out, err = self._run(
            ["--table"],
            [
                (json.dumps({"clusters": [CLUSTER_1, CLUSTER_2],
                             "totalSize": 2}), "", 0),
                (auth, "", 0),
            ])
        self.assertEqual(rc, 0)
        self.assertIn("css-prod-01", out)

    def test_json_output(self):
        rc, out, err = self._run(
            ["--json"],
            [(json.dumps({"clusters": [CLUSTER_1], "totalSize": 1}), "", 0)])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload, [CLUSTER_1])

    def test_node_view(self):
        rc, out, err = self._run(
            ["--table", "--cluster-id", "c-0002"],
            [
                (json.dumps(CLUSTER_2), "", 0),
                (json.dumps({"diskInfoList": [
                    {"id": "n-0002", "percentage": "81.5"}]}), "", 0),
            ])
        self.assertEqual(rc, 0)
        self.assertIn("节点列表", out)
        self.assertIn("⚠ 异常节点", out)

    def test_node_view_json(self):
        rc, out, err = self._run(
            ["--json", "--cluster-id", "c-0001"],
            [
                (json.dumps(CLUSTER_1), "", 0),
                (json.dumps({"diskInfoList": []}), "", 0),
            ])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload["cluster"]["id"], "c-0001")
        self.assertEqual(payload["volumeUsage"], [])

    def test_empty_clusters_message(self):
        rc, out, err = self._run(
            ["--region", "cn-south-1"],
            [(json.dumps({"clusters": [], "totalSize": 0}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("暂无 CSS 集群", out)
        self.assertIn("cn-south-1", out)

    def test_empty_with_status_filter(self):
        rc, out, err = self._run(
            ["--status", "abnormal"],
            [(json.dumps({"clusters": [], "totalSize": 0}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("status=abnormal", out)

    def test_auth_error_message(self):
        rc, out, err = self._run(
            [],
            [(json.dumps({"errCode": "CSS.0051",
                          "externalMessage": "policy denied"}), "", 0)])
        self.assertEqual(rc, 1)
        self.assertIn("[错误]", err)
        self.assertIn("CSS", err)

    def test_missing_ak_error_message(self):
        rc, out, err = self._run([], [("", "ERROR: cli-ak empty", 1)])
        self.assertEqual(rc, 1)
        self.assertIn("AK/SK", err)

    def test_hcloud_not_installed(self):
        rc, out, err = self._run([], [FileNotFoundError()])
        self.assertEqual(rc, 1)
        # hcloud missing triggers the SDK fallback; with no SDK credentials the
        # error points at AK/SK, otherwise at installing KooCLI.
        self.assertTrue("hcloud" in err or "AK/SK" in err)

    def test_write_intent_action_blocked(self):
        rc, out, err = self._run(["--action", "delete"], [])
        self.assertEqual(rc, 1)
        self.assertIn("写操作意图", err)

    def test_write_intent_name_blocked(self):
        rc, out, err = self._run(["--name", "create-me"], [])
        self.assertEqual(rc, 1)
        self.assertIn("写操作意图", err)

    def test_status_creating_allowed(self):
        rc, out, err = self._run(
            ["--status", "creating"],
            [(json.dumps({"clusters": [], "totalSize": 0}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("暂无 CSS 集群", out)

    def test_cluster_not_found(self):
        rc, out, err = self._run(
            ["--cluster-id", "missing-id"],
            [(json.dumps({}), "", 0)])
        self.assertEqual(rc, 1)
        self.assertIn("不存在", err)

    def test_datastore_type_forwarded(self):
        fake = FakeRunner([(
            json.dumps({"clusters": [CLUSTER_1], "totalSize": 1}), "", 0)])
        with mock.patch.dict(os.environ, {"CSS_LIST_HCLOUD_BIN": "hcloud"}), \
                mock.patch("list_css_clusters.subprocess.run", fake), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            rc = main(["--datastore-type", "elasticsearch"])
        self.assertEqual(rc, 0)
        self.assertIn("--datastoreType=elasticsearch", fake.calls[0])

    def test_limit_clamped(self):
        fake = FakeRunner([(
            json.dumps({"clusters": [CLUSTER_1], "totalSize": 1}), "", 0)])
        with mock.patch.dict(os.environ, {"CSS_LIST_HCLOUD_BIN": "hcloud"}), \
                mock.patch("list_css_clusters.subprocess.run", fake), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            rc = main(["--limit", "500"])
        self.assertEqual(rc, 0)
        self.assertIn("--limit=%d" % MAX_LIMIT, fake.calls[0])


class TestErrorHierarchy(unittest.TestCase):
    def test_subclasses(self):
        for exc in (GuardError, ConfigError, AuthError, ApiError):
            self.assertTrue(issubclass(exc, css.CssListError))


if __name__ == "__main__":
    unittest.main()