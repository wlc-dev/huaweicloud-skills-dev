import json
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from list_cce import (  # noqa: E402
    ALLOWED_OPERATION,
    ApiError,
    AuthError,
    ConfigError,
    GuardError,
    CceListError,
    build_command,
    classify_hcloud_failure,
    cluster_names,
    extract_clusters,
    extract_json,
    filter_clusters,
    guard_operation,
    guard_write_intent,
    list_clusters,
    list_clusters_via_sdk,
    main,
    normalize_cluster,
    render_table,
)

CLUSTER_1 = {
    "kind": "Cluster",
    "apiVersion": "v3",
    "metadata": {
        "name": "cce-demo-01",
        "uid": "uid-0001",
        "alias": "demo-one",
        "creation_timestamp": "2024-01-01T00:00:00Z",
        "labels": {"env": "test"},
    },
    "spec": {
        "type": "VirtualMachine",
        "flavor": "cce.s1.small",
        "version": "v1.25",
        "category": "CCE",
        "billing_mode": 0,
        "description": "demo cluster",
    },
    "status": {"phase": "Available"},
}
CLUSTER_2 = {
    "kind": "Cluster",
    "apiVersion": "v3",
    "metadata": {"name": "cce-demo-02", "uid": "uid-0002"},
    "spec": {"type": "VirtualMachine", "flavor": "cce.s1.medium", "version": "v1.25"},
    "status": {"phase": "Creating"},
}

LIST_RESPONSE = {"kind": "List", "apiVersion": "v3", "items": [CLUSTER_1, CLUSTER_2]}


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


class TestWriteIntentGuard(unittest.TestCase):
    def test_read_intent_passes(self):
        self.assertFalse(guard_write_intent("--region cn-north-4 --json list cce clusters"))
        self.assertFalse(guard_write_intent("show cluster details"))

    def test_create_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("CreateCluster cce-new")

    def test_delete_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("--operation DeleteCluster")

    def test_mutating_verbs_blocked(self):
        for text in ("upgrade cluster", "resize node pool", "hibernate cluster",
                     "wakeup cluster", "add node", "remove node",
                     "update cluster name", "modify cluster"):
            with self.assertRaises(GuardError):
                guard_write_intent(text)

    def test_normalized_separators_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("--create-cluster")
        with self.assertRaises(GuardError):
            guard_write_intent("update_cluster_name")

    def test_read_filter_value_passes(self):
        self.assertFalse(guard_write_intent("--name cce-demo-01"))
        self.assertFalse(guard_write_intent("--names-only"))
        self.assertFalse(guard_write_intent("cn-north-4"))

    def test_operation_guard_rejects_non_list(self):
        with self.assertRaises(GuardError):
            guard_operation("ShowCluster")
        self.assertTrue(guard_operation(ALLOWED_OPERATION))


class TestBuildCommand(unittest.TestCase):
    def test_basic(self):
        argv = build_command("cn-north-4")
        self.assertEqual(argv[0], "CCE")
        self.assertEqual(argv[1], "ListClusters")
        self.assertIn("--cli-region=cn-north-4", argv)

    def test_no_write_flags_ever_added(self):
        argv = build_command("cn-north-4")
        for flag in argv:
            self.assertFalse(flag.lower().lstrip("-").startswith(
                ("create", "delete", "update", "resize", "upgrade")))


class TestExtract(unittest.TestCase):
    def test_extract_json_plain(self):
        data = extract_json(json.dumps({"items": []}))
        self.assertEqual(data, {"items": []})

    def test_extract_json_with_noise(self):
        data = extract_json("WARNING some noise\n{\"a\": 1}\n")
        self.assertEqual(data, {"a": 1})

    def test_extract_json_invalid(self):
        with self.assertRaises(ApiError):
            extract_json("<html>not json</html>")

    def test_extract_clusters_known_keys(self):
        for key in ("items", "clusters"):
            self.assertEqual(extract_clusters({key: [CLUSTER_1]}), [CLUSTER_1])
        self.assertEqual(extract_clusters([CLUSTER_1]), [CLUSTER_1])
        self.assertEqual(extract_clusters({"metadata": {}}), [])


class TestClassifyFailure(unittest.TestCase):
    def test_missing_credentials(self):
        err = classify_hcloud_failure(
            "", "ERROR: cli-ak is empty, please run hcloud configure", 1)
        self.assertIsInstance(err, ConfigError)
        self.assertIn("AK/SK", str(err))

    def test_auth_403(self):
        err = classify_hcloud_failure(
            "", '{"error_code":"ApiGW.0301","error_msg":"403 Forbidden"}', 1)
        self.assertIsInstance(err, AuthError)
        self.assertIn("IAM", str(err))

    def test_auth_unauthorized(self):
        err = classify_hcloud_failure("", "Unauthorized: invalid AK", 1)
        self.assertIsInstance(err, AuthError)

    def test_generic_api_error(self):
        err = classify_hcloud_failure("", "boom", 2)
        self.assertIsInstance(err, ApiError)

    def test_use_error_marker_with_zero_rc(self):
        err = classify_hcloud_failure(
            "[USE_ERROR]Invalid parameter: detail\n\n"
            "Run `hcloud CCE ListClusters --help` for details.", "", 0)
        self.assertIsInstance(err, ApiError)
        self.assertIn("参数错误", str(err))
        self.assertIn("--help", str(err))


class TestListClusters(unittest.TestCase):
    def test_single_call(self):
        fake = FakeRunner([(json.dumps(LIST_RESPONSE), "", 0)])
        with mock.patch("list_cce.subprocess.run", fake):
            clusters = list_clusters("cn-north-4")
        self.assertEqual(clusters, [CLUSTER_1, CLUSTER_2])
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("CCE", fake.calls[0])
        self.assertIn("ListClusters", fake.calls[0])

    def test_empty_region(self):
        fake = FakeRunner([(json.dumps({"kind": "List", "items": []}), "", 0)])
        with mock.patch("list_cce.subprocess.run", fake):
            clusters = list_clusters("cn-north-4")
        self.assertEqual(clusters, [])

    def test_use_error_rc0_raises_api_error(self):
        fake = FakeRunner([(
            "[USE_ERROR]Invalid parameter: x\n\n"
            "Run `hcloud CCE ListClusters --help` for details.", "", 0)])
        with mock.patch("list_cce.subprocess.run", fake):
            with self.assertRaises(ApiError) as ctx:
                list_clusters("cn-north-4")
        self.assertIn("参数错误", str(ctx.exception))

    def test_nonzero_exit_403(self):
        fake = FakeRunner([("", "403 Forbidden", 1)])
        with mock.patch("list_cce.subprocess.run", fake):
            with self.assertRaises(AuthError):
                list_clusters("cn-north-4")

    def test_nonzero_exit_credentials(self):
        fake = FakeRunner([("", "ERROR: no AK configured", 1)])
        with mock.patch("list_cce.subprocess.run", fake):
            with self.assertRaises(ConfigError):
                list_clusters("cn-north-4")

    def test_timeout(self):
        fake = FakeRunner([subprocess.TimeoutExpired(cmd="hcloud", timeout=120)])
        with mock.patch("list_cce.subprocess.run", fake):
            with self.assertRaises(ApiError):
                list_clusters("cn-north-4")

    def test_sdk_fallback_when_hcloud_missing(self):
        with mock.patch("list_cce.subprocess.run",
                        FakeRunner([FileNotFoundError()])), \
                mock.patch("list_cce.list_clusters_via_sdk",
                           return_value=[CLUSTER_1, CLUSTER_2]) as sdk_mock:
            clusters = list_clusters("cn-north-4", project_id="pid-1")
        self.assertEqual(clusters, [CLUSTER_1, CLUSTER_2])
        self.assertEqual(sdk_mock.call_args.kwargs.get("project_id"), "pid-1")

    def test_sdk_fallback_unavailable_raises_config(self):
        with mock.patch("list_cce.subprocess.run",
                        FakeRunner([FileNotFoundError()])), \
                mock.patch("list_cce.list_clusters_via_sdk",
                           side_effect=ConfigError("huaweicloudsdkcce 未安装")):
            with self.assertRaises(ConfigError):
                list_clusters("cn-north-4")


class TestFiltering(unittest.TestCase):
    def test_name_substring_case_insensitive(self):
        result = filter_clusters([CLUSTER_1, CLUSTER_2], name="DEMO-01")
        self.assertEqual(result, [CLUSTER_1])

    def test_id_exact(self):
        result = filter_clusters([CLUSTER_1, CLUSTER_2], cluster_id="uid-0002")
        self.assertEqual(result, [CLUSTER_2])

    def test_no_filter_returns_all(self):
        self.assertEqual(filter_clusters([CLUSTER_1, CLUSTER_2]), [CLUSTER_1, CLUSTER_2])


class TestNormalizeAndRender(unittest.TestCase):
    def test_normalize_flattens(self):
        flat = normalize_cluster(CLUSTER_1)
        self.assertEqual(flat["name"], "cce-demo-01")
        self.assertEqual(flat["id"], "uid-0001")
        self.assertEqual(flat["status"], "Available")
        self.assertEqual(flat["type"], "VirtualMachine")
        self.assertEqual(flat["flavor"], "cce.s1.small")
        self.assertEqual(flat["labels"], "env=test")

    def test_normalize_missing_labels_dash(self):
        flat = normalize_cluster(CLUSTER_2)
        self.assertEqual(flat["labels"], "-")
        self.assertEqual(flat["alias"], "-")

    def test_table_contains_basic_info(self):
        table = render_table([CLUSTER_1, CLUSTER_2])
        for fragment in ("cce-demo-01", "uid-0001", "Available", "VirtualMachine",
                         "cce.s1.small", "env=test"):
            self.assertIn(fragment, table)

    def test_names(self):
        self.assertEqual(
            cluster_names([CLUSTER_1, CLUSTER_2]), ["cce-demo-01", "cce-demo-02"])

    def test_names_fallback_to_uid(self):
        self.assertEqual(cluster_names([{"metadata": {"uid": "uid-9"}}]), ["uid-9"])


class TestSdkFallback(unittest.TestCase):
    """Regression: the SDK fallback must use modules that exist in the official
    huaweicloudsdkcce package and wire credentials from environment variables
    (BasicCredentials has no env auto-discovery)."""

    def test_official_sdk_imports_resolve(self):
        try:
            from huaweicloudsdkcce.v3 import CceClient, ListClustersRequest
            from huaweicloudsdkcce.v3.region.cce_region import CceRegion
        except ImportError:
            self.skipTest("huaweicloudsdkcce not installed")
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkcore.http.http_config import HttpConfig
        for obj in (BasicCredentials, Region, HttpConfig,
                    CceClient, ListClustersRequest, CceRegion):
            self.assertTrue(callable(obj), obj)

    def test_sdk_request_signature(self):
        try:
            from huaweicloudsdkcce.v3 import ListClustersRequest
        except ImportError:
            self.skipTest("huaweicloudsdkcce not installed")
        request = ListClustersRequest(detail="true", status="Available")
        self.assertEqual(request.detail, "true")
        self.assertEqual(request.status, "Available")
        with self.assertRaises(TypeError):
            ListClustersRequest(no_such_param=1)

    def test_sdk_fallback_missing_env_credentials_raises_config(self):
        env = {k: v for k, v in os.environ.items()
               if not k.upper().startswith(("HUAWEI", "HW_", "HWC"))}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                list_clusters_via_sdk("cn-north-4")
        self.assertIn("AK/SK", str(ctx.exception))

    def test_sdk_fallback_returns_items_with_env_credentials(self):
        try:
            import huaweicloudsdkcce.v3 as cce_v3
        except ImportError:
            self.skipTest("huaweicloudsdkcce not installed")

        captured = {}

        class _FakeCluster:
            def __init__(self, payload):
                self._payload = payload

            def to_dict(self):
                return self._payload

        class _FakeResponse:
            def __init__(self, items):
                self.items = items

        class _FakeBuilder:
            def with_credentials(self, credentials):
                captured["credentials"] = credentials
                return self

            def with_region(self, region):
                captured["region"] = region
                return self

            def with_http_config(self, config):
                return self

            def build(self):
                return captured["client"]

        fake_client = mock.Mock()
        fake_client.list_clusters.return_value = _FakeResponse(
            [_FakeCluster(CLUSTER_1), _FakeCluster(CLUSTER_2)])
        captured["client"] = fake_client

        env = {k: v for k, v in os.environ.items()
               if not k.upper().startswith(("HUAWEI", "HW_", "HWC"))}
        env.update({"HUAWEI_ACCESS_KEY": "test-ak",
                    "HUAWEI_SECRET_KEY": "test-sk",
                    "HUAWEI_PROJECT_ID": "pid-123"})
        with mock.patch.object(cce_v3.CceClient, "new_builder",
                               classmethod(lambda cls: _FakeBuilder())), \
                mock.patch.dict(os.environ, env, clear=True):
            clusters = list_clusters_via_sdk("cn-north-4")
        self.assertEqual(clusters, [CLUSTER_1, CLUSTER_2])
        credentials = captured["credentials"]
        self.assertEqual(getattr(credentials, "ak", None), "test-ak")
        self.assertEqual(getattr(credentials, "sk", None), "test-sk")
        self.assertEqual(getattr(credentials, "project_id", None), "pid-123")
        self.assertEqual(getattr(captured["region"], "id", None), "cn-north-4")


class TestMain(unittest.TestCase):
    def _run(self, argv, results):
        fake = FakeRunner(results)
        with mock.patch("list_cce.subprocess.run", fake), \
                mock.patch("sys.stdout") as stdout, \
                mock.patch("sys.stderr") as stderr:
            rc = main(argv)
        out = "".join(c[0][0] for c in stdout.write.call_args_list)
        err = "".join(c[0][0] for c in stderr.write.call_args_list)
        return rc, out, err

    def test_table_output(self):
        rc, out, err = self._run(
            ["--region", "cn-north-4"],
            [(json.dumps(LIST_RESPONSE), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("云容器引擎（CCE）集群列表", out)
        self.assertIn("cce-demo-01", out)
        self.assertIn("Available", out)
        self.assertEqual(err, "")

    def test_json_output(self):
        rc, out, err = self._run(
            ["--json"],
            [(json.dumps(LIST_RESPONSE), "", 0)])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload, [CLUSTER_1, CLUSTER_2])

    def test_names_only_output(self):
        rc, out, err = self._run(
            ["--names-only"],
            [(json.dumps(LIST_RESPONSE), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("cce-demo-01", out)
        self.assertIn("cce-demo-02", out)
        self.assertNotIn("flavor", out)

    def test_name_filter_applied(self):
        rc, out, err = self._run(
            ["--name", "demo-01"],
            [(json.dumps(LIST_RESPONSE), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("cce-demo-01", out)
        self.assertNotIn("cce-demo-02", out)

    def test_id_filter_applied(self):
        rc, out, err = self._run(
            ["--id", "uid-0002"],
            [(json.dumps(LIST_RESPONSE), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("cce-demo-02", out)
        self.assertNotIn("cce-demo-01", out)

    def test_empty_clusters_message(self):
        rc, out, err = self._run(
            ["--region", "cn-south-1"],
            [(json.dumps({"kind": "List", "items": []}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("无云容器引擎（CCE）集群", out)
        self.assertIn("cn-south-1", out)

    def test_empty_with_filter_message(self):
        rc, out, _ = self._run(
            ["--name", "nope"],
            [(json.dumps({"kind": "List", "items": []}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("name=nope", out)

    def test_empty_json_output(self):
        rc, out, err = self._run(
            ["--json"],
            [(json.dumps({"kind": "List", "items": []}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [])

    def test_empty_names_only_output(self):
        rc, out, err = self._run(
            ["--names-only"],
            [(json.dumps({"kind": "List", "items": []}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("共 0 个", out)
        self.assertNotIn("无云容器引擎", out)

    def test_auth_error_message(self):
        rc, out, err = self._run([], [("", "403 Forbidden", 1)])
        self.assertEqual(rc, 1)
        self.assertIn("[错误]", err)
        self.assertIn("IAM", err)

    def test_missing_ak_sk_error_message(self):
        rc, out, err = self._run([], [("", "ERROR: cli-ak empty", 1)])
        self.assertEqual(rc, 1)
        self.assertIn("AK/SK", err)

    def test_hcloud_not_installed(self):
        with mock.patch("list_cce.list_clusters_via_sdk",
                        side_effect=ConfigError("huaweicloudsdkcce 未安装")):
            rc, out, err = self._run([], [FileNotFoundError()])
        self.assertEqual(rc, 1)
        self.assertIn("未安装", err)

    def test_hcloud_missing_falls_back_to_sdk(self):
        with mock.patch("list_cce.list_clusters_via_sdk",
                        return_value=[CLUSTER_1]):
            rc, out, err = self._run([], [FileNotFoundError()])
        self.assertEqual(rc, 0)
        self.assertIn("cce-demo-01", out)

    def test_write_intent_argv_blocked(self):
        rc, out, err = self._run(["--operation", "DeleteCluster"], [])
        self.assertEqual(rc, 1)
        self.assertIn("写操作意图", err)

    def test_write_keyword_argv_blocked(self):
        rc, out, err = self._run(["--name", "detach-me"], [])
        self.assertEqual(rc, 1)
        self.assertIn("守卫拦截", err)


class TestErrorHierarchy(unittest.TestCase):
    def test_subclasses(self):
        for exc in (GuardError, ConfigError, AuthError, ApiError):
            self.assertTrue(issubclass(exc, CceListError))


if __name__ == "__main__":
    unittest.main()