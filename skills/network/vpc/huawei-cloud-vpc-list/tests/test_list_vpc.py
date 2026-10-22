import json
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from list_vpc import (  # noqa: E402
    ALLOWED_OPERATION,
    ApiError,
    AuthError,
    ConfigError,
    GuardError,
    VpcListError,
    build_command,
    classify_hcloud_failure,
    extract_json,
    extract_vpcs,
    guard_operation,
    guard_write_intent,
    list_vpcs,
    list_vpcs_via_sdk,
    main,
    normalize_vpc,
    render_table,
    vpc_names,
)

VPC_1 = {
    "id": "vpc-0001",
    "name": "vpc-demo-01",
    "cidr": "192.168.0.0/16",
    "status": "OK",
    "description": "demo vpc",
    "routes": [
        {"destination": "0.0.0.0/0", "nexthop": "10.0.0.1"},
    ],
    "enterprise_project_id": "0",
    "tenant_id": "tenant-0001",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-02T00:00:00",
    "block_service_endpoint_states": "off",
    "enable_network_address_usage_metrics": False,
}
VPC_2 = {
    "id": "vpc-0002",
    "name": "vpc-demo-02",
    "cidr": "10.0.0.0/8",
    "status": "CREATING",
    "routes": [],
    "enterprise_project_id": "0",
    "tenant_id": "tenant-0001",
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


class TestWriteIntentGuard(unittest.TestCase):
    def test_read_intent_passes(self):
        self.assertFalse(guard_write_intent("--region cn-north-4 --json list vpcs"))
        self.assertFalse(guard_write_intent("show vpc details"))

    def test_create_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("CreateVpc vpc-new")

    def test_delete_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("--operation DeleteVpc")

    def test_mutating_verbs_blocked(self):
        for text in ("associate route", "disassociate port",
                     "detach subnet from vpc", "release vpc-01",
                     "update vpc name", "bind bandwidth"):
            with self.assertRaises(GuardError):
                guard_write_intent(text)

    def test_normalized_separators_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("--create-vpc")
        with self.assertRaises(GuardError):
            guard_write_intent("delete_subnet_route")

    def test_read_filter_value_passes(self):
        self.assertFalse(guard_write_intent("--id 1234abcd-0000-0000-0000-000000000000"))
        self.assertFalse(guard_write_intent("--enterprise-project-id 0"))

    def test_operation_guard_rejects_non_list(self):
        with self.assertRaises(GuardError):
            guard_operation("ShowVpc")
        self.assertTrue(guard_operation(ALLOWED_OPERATION))


class TestBuildCommand(unittest.TestCase):
    def test_basic(self):
        argv = build_command("cn-north-4")
        self.assertEqual(argv[0], "VPC")
        self.assertEqual(argv[1], "ListVpcs")
        self.assertIn("--cli-region=cn-north-4", argv)
        self.assertIn("--limit=100", argv)
        self.assertFalse(any(flag.startswith("--marker") for flag in argv))

    def test_marker_appended(self):
        argv = build_command("cn-north-4", marker="tok-123", limit=10)
        self.assertIn("--marker=tok-123", argv)
        self.assertIn("--limit=10", argv)

    def test_filters_forwarded_server_side(self):
        argv = build_command("cn-south-1", vpc_id="vpc-9",
                             enterprise_project_id="0", limit=10)
        self.assertIn("--id=vpc-9", argv)
        self.assertIn("--enterprise_project_id=0", argv)
        self.assertIn("--limit=10", argv)

    def test_no_write_flags_ever_added(self):
        argv = build_command("cn-north-4", enterprise_project_id="0")
        for flag in argv:
            self.assertFalse(flag.lower().lstrip("-").startswith(
                ("create", "delete", "update", "associate", "release")))


class TestExtract(unittest.TestCase):
    def test_extract_json_plain(self):
        data = extract_json(json.dumps({"vpcs": []}))
        self.assertEqual(data, {"vpcs": []})

    def test_extract_json_with_noise(self):
        data = extract_json("WARNING some noise\n{\"a\": 1}\n")
        self.assertEqual(data, {"a": 1})

    def test_extract_json_invalid(self):
        with self.assertRaises(ApiError):
            extract_json("<html>not json</html>")

    def test_extract_vpcs_known_keys(self):
        for key in ("vpcs", "vpc"):
            self.assertEqual(extract_vpcs({key: [VPC_1]}), [VPC_1])
        self.assertEqual(extract_vpcs([VPC_1]), [VPC_1])
        self.assertEqual(extract_vpcs({"page_info": {}}), [])


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
            "[USE_ERROR]Invalid parameter: enterprise_project_id\n\n"
            "Run `hcloud VPC ListVpcs --help` for details.", "", 0)
        self.assertIsInstance(err, ApiError)
        self.assertIn("参数错误", str(err))
        self.assertIn("--help", str(err))


class TestListVpcs(unittest.TestCase):
    def test_single_page(self):
        fake = FakeRunner([(
            json.dumps({"vpcs": [VPC_1, VPC_2]}), "", 0)])
        with mock.patch("list_vpc.subprocess.run", fake):
            vpcs = list_vpcs("cn-north-4")
        self.assertEqual(vpcs, [VPC_1, VPC_2])
        self.assertEqual(len(fake.calls), 1)

    def test_pagination_via_next_marker(self):
        page1 = {"vpcs": [VPC_1],
                 "page_info": {"next_marker": "tok-2", "current_count": 1}}
        page2 = {"vpcs": [VPC_2],
                 "page_info": {"next_marker": None, "current_count": 1}}
        fake = FakeRunner([(json.dumps(page1), "", 0), (json.dumps(page2), "", 0)])
        with mock.patch("list_vpc.subprocess.run", fake):
            vpcs = list_vpcs("cn-north-4", limit=1)
        self.assertEqual(vpcs, [VPC_1, VPC_2])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("--marker=tok-2", fake.calls[1])

    def test_pagination_via_full_page_without_marker(self):
        page1 = {"vpcs": [VPC_1]}
        page2 = {"vpcs": []}
        fake = FakeRunner([(json.dumps(page1), "", 0), (json.dumps(page2), "", 0)])
        with mock.patch("list_vpc.subprocess.run", fake):
            vpcs = list_vpcs("cn-north-4", limit=1)
        self.assertEqual(vpcs, [VPC_1])

    def test_empty_region(self):
        fake = FakeRunner([(json.dumps({"vpcs": []}), "", 0)])
        with mock.patch("list_vpc.subprocess.run", fake):
            vpcs = list_vpcs("cn-north-4")
        self.assertEqual(vpcs, [])

    def test_filters_forwarded_to_cli(self):
        fake = FakeRunner([(
            json.dumps({"vpcs": [VPC_1]}), "", 0)])
        with mock.patch("list_vpc.subprocess.run", fake):
            list_vpcs("cn-north-4", vpc_id="vpc-0001", enterprise_project_id="0")
        call = fake.calls[0]
        self.assertTrue(any("--id=vpc-0001" in part for part in call))
        self.assertTrue(any("--enterprise_project_id=0" in part for part in call))

    def test_use_error_rc0_raises_api_error(self):
        fake = FakeRunner([(
            "[USE_ERROR]Invalid parameter: enterprise_project_id\n\n"
            "Run `hcloud VPC ListVpcs --help` for details.", "", 0)])
        with mock.patch("list_vpc.subprocess.run", fake):
            with self.assertRaises(ApiError) as ctx:
                list_vpcs("cn-north-4")
        self.assertIn("参数错误", str(ctx.exception))

    def test_nonzero_exit_403(self):
        fake = FakeRunner([("", "403 Forbidden", 1)])
        with mock.patch("list_vpc.subprocess.run", fake):
            with self.assertRaises(AuthError):
                list_vpcs("cn-north-4")

    def test_nonzero_exit_credentials(self):
        fake = FakeRunner([("", "ERROR: no AK configured", 1)])
        with mock.patch("list_vpc.subprocess.run", fake):
            with self.assertRaises(ConfigError):
                list_vpcs("cn-north-4")

    def test_timeout(self):
        fake = FakeRunner([subprocess.TimeoutExpired(cmd="hcloud", timeout=120)])
        with mock.patch("list_vpc.subprocess.run", fake):
            with self.assertRaises(ApiError):
                list_vpcs("cn-north-4")

    def test_sdk_fallback_when_hcloud_missing(self):
        with mock.patch("list_vpc.subprocess.run",
                        FakeRunner([FileNotFoundError()])), \
                mock.patch("list_vpc.list_vpcs_via_sdk",
                           return_value=[VPC_1, VPC_2]) as sdk_mock:
            vpcs = list_vpcs("cn-north-4", vpc_id="vpc-1",
                             enterprise_project_id="0", project_id="proj-1")
        self.assertEqual(vpcs, [VPC_1, VPC_2])
        self.assertEqual(sdk_mock.call_args.kwargs.get("vpc_id"), "vpc-1")
        self.assertEqual(sdk_mock.call_args.kwargs.get("project_id"), "proj-1")

    def test_sdk_fallback_unavailable_raises_config(self):
        with mock.patch("list_vpc.subprocess.run",
                        FakeRunner([FileNotFoundError()])), \
                mock.patch("list_vpc.list_vpcs_via_sdk",
                           side_effect=ConfigError("huaweicloudsdkvpc 未安装")):
            with self.assertRaises(ConfigError):
                list_vpcs("cn-north-4")

    def test_sdk_request_signature(self):
        # Regression guard: the real huaweicloudsdkvpc ListVpcsRequest must be
        # constructible with exactly the kwargs the fallback path sends.
        try:
            from huaweicloudsdkvpc.v2 import ListVpcsRequest
        except ImportError:
            self.skipTest("huaweicloudsdkvpc not installed")
        request = ListVpcsRequest(
            limit=100, marker=None, id="vpc-9", enterprise_project_id="0",
        )
        self.assertEqual(request.id, "vpc-9")
        self.assertEqual(request.enterprise_project_id, "0")
        with self.assertRaises(TypeError):
            ListVpcsRequest(no_such_param=1)


class _FakeSdkResponse:
    def __init__(self, vpcs, next_marker=None):
        self.vpcs = vpcs

        class _PageInfo:
            pass

        if next_marker is not None:
            page = _PageInfo()
            page.next_marker = next_marker
            self.page_info = page


class _FakeSdkVpc:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


class _FakeSdkBuilder:
    def __init__(self, test):
        self._test = test

    def with_credentials(self, credentials):
        self._test._captured_credentials = credentials
        return self

    def with_region(self, region):
        self._test._captured_region = region
        return self

    def with_http_config(self, config):
        return self

    def build(self):
        return self._test._fake_client


class TestSdkFallback(unittest.TestCase):
    """The SDK fallback must use modules that exist in the official
    huaweicloudsdkvpc package and wire credentials (including the project id
    required by /v1/{project_id}/...) from environment variables
    (BasicCredentials has no env auto-discovery)."""

    def setUp(self):
        self._captured_credentials = None
        self._captured_region = None
        self._fake_client = mock.Mock()
        self._fake_client.list_vpcs.return_value = _FakeSdkResponse(
            [_FakeSdkVpc(VPC_1), _FakeSdkVpc(VPC_2)], None)
        try:
            import huaweicloudsdkvpc.v2 as vpc_v2
        except ImportError:
            self.skipTest("huaweicloudsdkvpc not installed")
        self._builder_patch = mock.patch.object(
            vpc_v2.VpcClient, "new_builder",
            classmethod(lambda cls: _FakeSdkBuilder(self)))
        self._builder_patch.start()
        self.addCleanup(self._builder_patch.stop)

    def _clean_credential_env(self):
        credential_vars = (
            "HW_ACCESS_KEY",
            "HUAWEI_ACCESS_KEY",
            "HUAWEICLOUD_SDK_AK",
            "HUAWEI_CLOUD_ACCESS_KEY",
            "HW_SECRET_KEY",
            "HUAWEI_SECRET_KEY",
            "HUAWEICLOUD_SDK_SK",
            "HUAWEI_CLOUD_SECRET_KEY",
            "HW_PROJECT_ID",
            "HUAWEI_PROJECT_ID",
            "HUAWEICLOUD_SDK_PROJECT_ID",
            "HUAWEI_CLOUD_PROJECT_ID",
        )
        return {name: "" for name in credential_vars}

    def test_official_sdk_imports_resolve(self):
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkcore.http.http_config import HttpConfig
        from huaweicloudsdkvpc.v2 import VpcClient, ListVpcsRequest
        from huaweicloudsdkvpc.v2.region.vpc_region import VpcRegion
        for obj in (BasicCredentials, Region, HttpConfig,
                    VpcClient, ListVpcsRequest, VpcRegion):
            self.assertTrue(callable(obj), obj)

    def test_sdk_fallback_returns_vpcs_with_env_credentials(self):
        env = dict(self._clean_credential_env(),
                   HUAWEI_ACCESS_KEY="test-ak",
                   HUAWEI_SECRET_KEY="test-sk",
                   HUAWEI_PROJECT_ID="test-project")
        with mock.patch.dict(os.environ, env, clear=True):
            vpcs = list_vpcs_via_sdk("cn-north-4")
        self.assertEqual(vpcs, [VPC_1, VPC_2])
        credentials = self._captured_credentials
        self.assertIsNotNone(credentials)
        self.assertEqual(getattr(credentials, "ak", None), "test-ak")
        self.assertEqual(getattr(credentials, "sk", None), "test-sk")
        self.assertEqual(getattr(credentials, "project_id", None), "test-project")
        self.assertEqual(getattr(self._captured_region, "id", None), "cn-north-4")

    def test_explicit_project_id_overrides_env(self):
        env = dict(self._clean_credential_env(),
                   HUAWEI_ACCESS_KEY="test-ak",
                   HUAWEI_SECRET_KEY="test-sk",
                   HUAWEI_PROJECT_ID="env-project")
        with mock.patch.dict(os.environ, env, clear=True):
            list_vpcs_via_sdk("cn-north-4", project_id="cli-project")
        self.assertEqual(
            getattr(self._captured_credentials, "project_id", None), "cli-project")

    def test_sdk_fallback_missing_env_credentials_raises_config(self):
        env = dict(self._clean_credential_env(), HUAWEI_PROJECT_ID="test-project")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                list_vpcs_via_sdk("cn-north-4")
        message = str(ctx.exception)
        self.assertIn("AK/SK", message)
        self.assertNotIn("未安装", message)

    def test_sdk_fallback_missing_project_id_raises_config(self):
        env = dict(self._clean_credential_env(),
                   HUAWEI_ACCESS_KEY="test-ak", HUAWEI_SECRET_KEY="test-sk")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                list_vpcs_via_sdk("cn-north-4")
        self.assertIn("project_id", str(ctx.exception))

    def test_sdk_pagination_via_page_info(self):
        first = _FakeSdkResponse([_FakeSdkVpc(VPC_1)], "tok-2")
        second = _FakeSdkResponse([_FakeSdkVpc(VPC_2)], None)
        self._fake_client.list_vpcs.side_effect = [first, second]
        env = dict(self._clean_credential_env(),
                   HUAWEI_ACCESS_KEY="test-ak",
                   HUAWEI_SECRET_KEY="test-sk",
                   HUAWEI_PROJECT_ID="test-project")
        with mock.patch.dict(os.environ, env, clear=True):
            vpcs = list_vpcs_via_sdk("cn-north-4")
        self.assertEqual(vpcs, [VPC_1, VPC_2])
        second_request = self._fake_client.list_vpcs.call_args_list[1][0][0]
        self.assertEqual(second_request.marker, "tok-2")

    def test_sdk_pagination_via_last_id_when_page_full(self):
        # Typed ListVpcsResponse carries no page_info; a full page continues
        # from the last returned VPC id.
        first = _FakeSdkResponse([_FakeSdkVpc(VPC_1), _FakeSdkVpc(VPC_2)], None)
        second = _FakeSdkResponse([], None)
        self._fake_client.list_vpcs.side_effect = [first, second]
        env = dict(self._clean_credential_env(),
                   HUAWEI_ACCESS_KEY="test-ak",
                   HUAWEI_SECRET_KEY="test-sk",
                   HUAWEI_PROJECT_ID="test-project")
        with mock.patch.dict(os.environ, env, clear=True):
            vpcs = list_vpcs_via_sdk("cn-north-4", limit=2)
        self.assertEqual(vpcs, [VPC_1, VPC_2])
        second_request = self._fake_client.list_vpcs.call_args_list[1][0][0]
        self.assertEqual(second_request.marker, "vpc-0002")


class TestNormalizeAndRender(unittest.TestCase):
    def test_normalize_compacts_routes(self):
        flat = normalize_vpc(VPC_1)
        self.assertIsInstance(flat["routes"], str)
        self.assertIn("0.0.0.0/0", flat["routes"])
        self.assertEqual(flat["name"], "vpc-demo-01")

    def test_normalize_empty_routes(self):
        flat = normalize_vpc(VPC_2)
        self.assertEqual(flat["routes"], "[]")

    def test_table_contains_basic_info(self):
        table = render_table([VPC_1, VPC_2])
        for fragment in ("vpc-0001", "vpc-demo-01", "192.168.0.0/16", "OK",
                         "vpc-0002", "10.0.0.0/8", "CREATING"):
            self.assertIn(fragment, table)

    def test_names(self):
        self.assertEqual(
            vpc_names([VPC_1, VPC_2]), ["vpc-demo-01", "vpc-demo-02"])

    def test_names_fallback_to_id(self):
        self.assertEqual(vpc_names([{"id": "vpc-9"}]), ["vpc-9"])


class TestMain(unittest.TestCase):
    def _run(self, argv, results):
        fake = FakeRunner(results)
        with mock.patch("list_vpc.subprocess.run", fake), \
                mock.patch("sys.stdout") as stdout, \
                mock.patch("sys.stderr") as stderr:
            rc = main(argv)
        out = "".join(c[0][0] for c in stdout.write.call_args_list)
        err = "".join(c[0][0] for c in stderr.write.call_args_list)
        return rc, out, err

    def test_table_output(self):
        rc, out, err = self._run(
            ["--region", "cn-north-4"],
            [(json.dumps({"vpcs": [VPC_1, VPC_2]}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("虚拟私有云（VPC）列表", out)
        self.assertIn("vpc-0001", out)
        self.assertIn("OK", out)
        self.assertEqual(err, "")

    def test_json_output(self):
        rc, out, err = self._run(
            ["--json"],
            [(json.dumps({"vpcs": [VPC_1]}), "", 0)])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload, [VPC_1])

    def test_names_only_output(self):
        rc, out, err = self._run(
            ["--names-only"],
            [(json.dumps({"vpcs": [VPC_1, VPC_2]}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("vpc-demo-01", out)
        self.assertIn("vpc-demo-02", out)
        self.assertNotIn("cidr", out)

    def test_empty_vpcs_message(self):
        rc, out, err = self._run(
            ["--region", "cn-south-1"],
            [(json.dumps({"vpcs": []}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("无虚拟私有云（VPC）", out)
        self.assertIn("cn-south-1", out)

    def test_empty_with_filter_message(self):
        rc, out, _ = self._run(
            ["--enterprise-project-id", "0"],
            [(json.dumps({"vpcs": []}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("enterprise_project_id=0", out)

    def test_id_filter_main_forwarded(self):
        fake = FakeRunner([
            (json.dumps({"vpcs": [VPC_1]}), "", 0)])
        with mock.patch("list_vpc.subprocess.run", fake), \
                mock.patch("sys.stdout"), \
                mock.patch("sys.stderr"):
            rc = main(["--id", "vpc-0001"])
        self.assertEqual(rc, 0)
        self.assertTrue(any("--id=vpc-0001" in part for part in fake.calls[0]))

    def test_empty_json_output(self):
        rc, out, err = self._run(
            ["--json"],
            [(json.dumps({"vpcs": []}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [])

    def test_empty_names_only_output(self):
        rc, out, err = self._run(
            ["--names-only"],
            [(json.dumps({"vpcs": []}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("共 0 个", out)
        self.assertNotIn("无虚拟私有云（VPC）", out)

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
        with mock.patch("list_vpc.list_vpcs_via_sdk",
                        side_effect=ConfigError("huaweicloudsdkvpc 未安装")):
            rc, out, err = self._run([], [FileNotFoundError()])
        self.assertEqual(rc, 1)
        self.assertIn("未安装", err)

    def test_hcloud_missing_falls_back_to_sdk(self):
        with mock.patch("list_vpc.list_vpcs_via_sdk",
                        return_value=[VPC_1]):
            rc, out, err = self._run([], [FileNotFoundError()])
        self.assertEqual(rc, 0)
        self.assertIn("vpc-0001", out)

    def test_project_id_forwarded_to_sdk(self):
        with mock.patch("list_vpc.list_vpcs_via_sdk",
                        return_value=[VPC_1]) as sdk_mock:
            rc, out, err = self._run(["--project-id", "proj-9"],
                                     [FileNotFoundError()])
        self.assertEqual(rc, 0)
        self.assertEqual(sdk_mock.call_args.kwargs.get("project_id"), "proj-9")

    def test_write_intent_argv_blocked(self):
        rc, out, err = self._run(["--operation", "DeleteVpc"], [])
        self.assertEqual(rc, 1)
        self.assertIn("写操作意图", err)

    def test_write_keyword_argv_blocked(self):
        rc, out, err = self._run(["--id", "release-me"], [])
        self.assertEqual(rc, 1)
        self.assertIn("守卫拦截", err)


class TestErrorHierarchy(unittest.TestCase):
    def test_subclasses(self):
        for exc in (GuardError, ConfigError, AuthError, ApiError):
            self.assertTrue(issubclass(exc, VpcListError))


if __name__ == "__main__":
    unittest.main()