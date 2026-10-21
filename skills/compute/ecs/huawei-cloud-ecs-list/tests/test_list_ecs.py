import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from list_ecs import (  # noqa: E402
    ALLOWED_OPERATION,
    ApiError,
    AuthError,
    ConfigError,
    GuardError,
    EcsListError,
    MD_TABLE_COLUMNS,
    OutputError,
    active_filter_descriptions,
    build_command,
    classify_hcloud_failure,
    default_markdown_name,
    default_txt_name,
    extract_servers,
    extract_json,
    format_query_time,
    guard_operation,
    guard_text_from_argv,
    guard_write_intent,
    list_servers,
    list_servers_via_sdk,
    main,
    normalize_server,
    render_markdown,
    render_table,
    render_txt,
    sdk_server_to_dict,
    server_names,
    server_summary_lines,
    write_markdown_file,
    write_txt_file,
)

SERVER_1 = {
    "id": "ecs-0001",
    "name": "ecs-web-01",
    "status": "ACTIVE",
    "flavor": {"id": "s6.large.2", "name": "s6.large.2", "vcpus": "2", "ram": "4096"},
    "addresses": {
        "vpc-subnet": [
            {"addr": "192.168.0.10", "OS-EXT-IPS:type": "fixed", "version": 4}
        ]
    },
    "OS-EXT-AZ:availability_zone": "cn-north-4a",
    "image": {"id": "img-0001"},
    "key_name": "kp-demo",
    "enterprise_project_id": "0",
}
SERVER_2 = {
    "id": "ecs-0002",
    "name": "ecs-db-02",
    "status": "SHUTOFF",
    "flavor": {"id": "s6.xlarge.2", "name": "s6.xlarge.2", "vcpus": "4", "ram": "8192"},
    "addresses": {
        "vpc-subnet": [
            {"addr": "192.168.0.11", "OS-EXT-IPS:type": "fixed"},
            {"addr": "10.0.0.5", "OS-EXT-IPS:type": "floating"},
        ]
    },
    "OS-EXT-AZ:availability_zone": "cn-north-4b",
    "tags": ["env:test"],
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
        self.assertFalse(guard_write_intent("--region cn-north-4 --json list servers"))
        self.assertFalse(guard_write_intent("show server details flavors"))

    def test_create_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("CreateServers ecs-new")

    def test_delete_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("--operation DeleteServers")

    def test_mutating_verbs_blocked(self):
        for text in ("resize flavor", "reboot ecs-01", "stop server",
                     "update server name", "attach volume", "server-action"):
            with self.assertRaises(GuardError):
                guard_write_intent(text)

    def test_normalized_separators_blocked(self):
        with self.assertRaises(GuardError):
            guard_write_intent("--create-server")
        with self.assertRaises(GuardError):
            guard_write_intent("delete_server")

    def test_operation_guard_rejects_non_list(self):
        with self.assertRaises(GuardError):
            guard_operation("ShowServer")
        with self.assertRaises(GuardError):
            guard_operation("BatchStartServers")
        self.assertTrue(guard_operation(ALLOWED_OPERATION))

    def test_guard_text_strips_filter_values(self):
        # The read-only filter values must NOT be scanned: ECS statuses such as
        # REBUILD/RESIZE and arbitrary instance names may contain write words.
        self.assertEqual(guard_text_from_argv(["--status", "REBUILD"]), "")
        self.assertEqual(guard_text_from_argv(["--status=RESIZE"]), "")
        self.assertEqual(guard_text_from_argv(["--name", "restart-me"]), "")
        self.assertEqual(guard_text_from_argv(["--region", "cn-north-4"]), "")
        # Operation name is still scanned (defense in depth).
        self.assertIn("DeleteServers",
                      guard_text_from_argv(["--operation", "DeleteServers"]))
        # Flag names are scanned.
        self.assertIn("--create-server",
                      guard_text_from_argv(["--create-server"]))

    def test_status_rebuild_not_blocked(self):
        # Regression guard: `--status REBUILD` is a legitimate read filter.
        self.assertFalse(
            guard_write_intent(guard_text_from_argv(["--status", "REBUILD"])))
        self.assertFalse(
            guard_write_intent(guard_text_from_argv(["--name", "stop-me"])))

    def test_guard_text_strips_md_file_values(self):
        # The Markdown output path is file-system data, not a cloud operation:
        # a report named `ecs-delete-report.md` must not trip the guard.
        self.assertEqual(
            guard_text_from_argv(["--md-file", "ecs-delete-report.md"]), "")
        self.assertEqual(
            guard_text_from_argv(["--md-file=ecs-delete-report.md"]), "")
        self.assertEqual(
            guard_text_from_argv(["--output-md", "ecs-start-stop-report.md"]), "")
        # `--md-file` takes an optional value: a following *flag* is still
        # scanned, so a mutating flag cannot hide behind it.
        self.assertIn("--create-server",
                      guard_text_from_argv(["--md-file", "--create-server"]))
        self.assertIn("DeleteServers",
                      guard_text_from_argv(["--md-file", "--operation",
                                            "DeleteServers"]))

    def test_md_file_path_with_write_words_not_blocked(self):
        self.assertFalse(guard_write_intent(
            guard_text_from_argv(["--md-file", "ecs-delete-report.md"])))
        self.assertFalse(guard_write_intent(
            guard_text_from_argv(["--md-file", "ecs-restart-report.md"])))

    def test_guard_text_strips_txt_file_values(self):
        # Same exemption as --md-file: the TXT output path is file-system data.
        self.assertEqual(
            guard_text_from_argv(["--txt-file", "ecs-delete-report.txt"]), "")
        self.assertEqual(
            guard_text_from_argv(["--txt-file=ecs-delete-report.txt"]), "")
        self.assertEqual(
            guard_text_from_argv(["--output-txt", "ecs-stop-report.txt"]), "")
        # Optional value: a following *flag* is still scanned.
        self.assertIn("--create-server",
                      guard_text_from_argv(["--txt-file", "--create-server"]))
        self.assertIn("DeleteServers",
                      guard_text_from_argv(["--txt-file", "--operation",
                                            "DeleteServers"]))

    def test_txt_file_path_with_write_words_not_blocked(self):
        self.assertFalse(guard_write_intent(
            guard_text_from_argv(["--txt-file", "ecs-delete-report.txt"])))
        self.assertFalse(guard_write_intent(
            guard_text_from_argv(["--output-txt", "ecs-start-report.txt"])))


class TestBuildCommand(unittest.TestCase):
    def test_basic(self):
        argv = build_command("cn-north-4")
        self.assertEqual(argv[0], "ECS")
        self.assertEqual(argv[1], "ListServersDetails")
        self.assertIn("--cli-region=cn-north-4", argv)
        self.assertIn("--limit=100", argv)
        self.assertIn("--offset=0", argv)

    def test_filters_appended(self):
        argv = build_command("cn-south-1", status="ACTIVE", name="ecs-web",
                             limit=10, offset=20)
        self.assertIn("--status=ACTIVE", argv)
        self.assertIn("--name=ecs-web", argv)
        self.assertIn("--limit=10", argv)
        self.assertIn("--offset=20", argv)

    def test_status_is_server_side_param(self):
        # ECS ListServersDetails DOES expose a server-side status parameter
        # (verified against huaweicloudsdkecs v2 ListServersDetailsRequest).
        argv = build_command("cn-north-4", status="ACTIVE")
        self.assertIn("--status=ACTIVE", argv)

    def test_no_write_flags_ever_added(self):
        argv = build_command("cn-north-4", status="ACTIVE", name="ecs-web")
        for flag in argv:
            self.assertFalse(
                flag.lower().lstrip("-").startswith(
                    ("create", "delete", "update", "reboot", "resize")))


class TestExtract(unittest.TestCase):
    def test_extract_json_plain(self):
        data = extract_json(json.dumps({"servers": []}))
        self.assertEqual(data, {"servers": []})

    def test_extract_json_with_noise(self):
        data = extract_json("WARNING noise\n{\"count\": 1}\n")
        self.assertEqual(data, {"count": 1})

    def test_extract_json_invalid(self):
        with self.assertRaises(ApiError):
            extract_json("<html>not json</html>")

    def test_extract_servers_known_keys(self):
        for key in ("servers", "server_list"):
            self.assertEqual(extract_servers({key: [SERVER_1]}), [SERVER_1])
        self.assertEqual(extract_servers([SERVER_1]), [SERVER_1])
        self.assertEqual(extract_servers({"count": 0}), [])


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
        # KooCLI usage errors exit rc=0 with [USE_ERROR] on stdout — must be
        # classified as an explicit parameter error, not a JSON parse issue.
        err = classify_hcloud_failure(
            "[USE_ERROR]Invalid parameter: xxx\n\n"
            "Run `hcloud ECS ListServersDetails --help` for details.", "", 0)
        self.assertIsInstance(err, ApiError)
        self.assertIn("参数错误", str(err))
        self.assertIn("--help", str(err))


class TestListServers(unittest.TestCase):
    def test_single_page(self):
        fake = FakeRunner([(
            json.dumps({"servers": [SERVER_1, SERVER_2], "count": 2}), "", 0)])
        with mock.patch("list_ecs.subprocess.run", fake):
            servers = list_servers("cn-north-4")
        self.assertEqual(servers, [SERVER_1, SERVER_2])
        self.assertEqual(len(fake.calls), 1)

    def test_pagination_via_count(self):
        page1 = {"servers": [SERVER_1], "count": 2}
        page2 = {"servers": [SERVER_2], "count": 2}
        fake = FakeRunner([(json.dumps(page1), "", 0), (json.dumps(page2), "", 0)])
        with mock.patch("list_ecs.subprocess.run", fake):
            servers = list_servers("cn-north-4", limit=1)
        self.assertEqual(servers, [SERVER_1, SERVER_2])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("--offset=1", fake.calls[1])

    def test_pagination_via_full_page_without_count(self):
        page1 = {"servers": [SERVER_1]}
        page2 = {"servers": []}
        fake = FakeRunner([(json.dumps(page1), "", 0), (json.dumps(page2), "", 0)])
        with mock.patch("list_ecs.subprocess.run", fake):
            servers = list_servers("cn-north-4", limit=1)
        self.assertEqual(servers, [SERVER_1])

    def test_empty_region(self):
        fake = FakeRunner([(json.dumps({"servers": [], "count": 0}), "", 0)])
        with mock.patch("list_ecs.subprocess.run", fake):
            servers = list_servers("cn-north-4")
        self.assertEqual(servers, [])

    def test_status_and_name_forwarded_server_side(self):
        fake = FakeRunner([(
            json.dumps({"servers": [SERVER_1], "count": 1}), "", 0)])
        with mock.patch("list_ecs.subprocess.run", fake):
            servers = list_servers("cn-north-4", status="ACTIVE", name="ecs-web")
        self.assertEqual(servers, [SERVER_1])
        call = fake.calls[0]
        self.assertIn("--status=ACTIVE", call)
        self.assertIn("--name=ecs-web", call)

    def test_use_error_rc0_raises_api_error(self):
        fake = FakeRunner([(
            "[USE_ERROR]Invalid parameter: xxx\n\n"
            "Run `hcloud ECS ListServersDetails --help` for details.", "", 0)])
        with mock.patch("list_ecs.subprocess.run", fake):
            with self.assertRaises(ApiError) as ctx:
                list_servers("cn-north-4")
        self.assertIn("参数错误", str(ctx.exception))

    def test_nonzero_exit_403(self):
        fake = FakeRunner([("", "403 Forbidden", 1)])
        with mock.patch("list_ecs.subprocess.run", fake):
            with self.assertRaises(AuthError):
                list_servers("cn-north-4")

    def test_nonzero_exit_credentials(self):
        fake = FakeRunner([("", "ERROR: no AK configured", 1)])
        with mock.patch("list_ecs.subprocess.run", fake):
            with self.assertRaises(ConfigError):
                list_servers("cn-north-4")

    def test_timeout(self):
        fake = FakeRunner([subprocess.TimeoutExpired(cmd="hcloud", timeout=120)])
        with mock.patch("list_ecs.subprocess.run", fake):
            with self.assertRaises(ApiError):
                list_servers("cn-north-4")

    def test_sdk_fallback_when_hcloud_missing(self):
        with mock.patch("list_ecs.subprocess.run",
                        FakeRunner([FileNotFoundError()])), \
                mock.patch("list_ecs.list_servers_via_sdk",
                           return_value=[SERVER_1, SERVER_2]) as sdk_mock:
            servers = list_servers("cn-north-4", status="ACTIVE", name="ecs-web")
        self.assertEqual(servers, [SERVER_1, SERVER_2])
        self.assertEqual(sdk_mock.call_args.kwargs.get("status"), "ACTIVE")
        self.assertEqual(sdk_mock.call_args.kwargs.get("name"), "ecs-web")

    def test_sdk_fallback_unavailable_raises_config(self):
        with mock.patch("list_ecs.subprocess.run",
                        FakeRunner([FileNotFoundError()])), \
                mock.patch("list_ecs.list_servers_via_sdk",
                           side_effect=ConfigError("huaweicloudsdkecs 未安装")):
            with self.assertRaises(ConfigError):
                list_servers("cn-north-4")

    def test_sdk_request_accepts_status_and_name(self):
        # Regression guard: the real huaweicloudsdkecs ListServersDetailsRequest
        # must be constructible with exactly the kwargs the fallback path sends.
        try:
            from huaweicloudsdkecs.v2 import ListServersDetailsRequest
        except ImportError:
            self.skipTest("huaweicloudsdkecs not installed")
        request = ListServersDetailsRequest(
            limit=100, offset=0, name="ecs-web", status="ACTIVE",
        )
        self.assertEqual(request.status, "ACTIVE")
        self.assertEqual(request.name, "ecs-web")
        self.assertIsNone(getattr(request, "datastore_type", None))


class TestSdkServerToDict(unittest.TestCase):
    def test_remaps_python_attr_names_to_wire_names(self):
        try:
            from huaweicloudsdkecs.v2 import ServerDetail
        except ImportError:
            self.skipTest("huaweicloudsdkecs not installed")
        detail = ServerDetail(
            id="ecs-9", name="ecs-live", status="ACTIVE",
            access_i_pv4="1.2.3.4",
            os_ext_a_zavailability_zone="cn-north-4a",
            flavor={"id": "s6.large.2", "name": "s6.large.2", "vcpus": "2", "ram": "4096"},
        )
        flat = sdk_server_to_dict(detail)
        self.assertEqual(flat["id"], "ecs-9")
        self.assertEqual(flat["name"], "ecs-live")
        self.assertEqual(flat["accessIPv4"], "1.2.3.4")
        self.assertEqual(flat["OS-EXT-AZ:availability_zone"], "cn-north-4a")
        # None-valued SDK fields must be dropped.
        self.assertNotIn("user_id", flat)

    def test_wire_name_dict_passes_through(self):
        flat = sdk_server_to_dict(dict(SERVER_1))
        self.assertEqual(flat["name"], "ecs-web-01")
        self.assertEqual(flat["OS-EXT-AZ:availability_zone"], "cn-north-4a")


class _FakeSdkResponse:
    def __init__(self, servers, count):
        self.servers = servers
        self.count = count


class _FakeSdkServer:
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


class TestSdkFallbackFix(unittest.TestCase):
    """Regression: the SDK fallback must use modules that exist in the official
    huaweicloudsdk packages and wire credentials from environment variables
    (BasicCredentials has no env auto-discovery)."""

    def setUp(self):
        self._captured_credentials = None
        self._captured_region = None
        self._fake_client = mock.Mock()
        self._fake_client.list_servers_details.return_value = _FakeSdkResponse(
            [_FakeSdkServer(SERVER_1), _FakeSdkServer(SERVER_2)], 2)
        try:
            import huaweicloudsdkecs.v2 as ecs_v2
        except ImportError:
            self.skipTest("huaweicloudsdkecs not installed")
        self._builder_patch = mock.patch.object(
            ecs_v2.EcsClient, "new_builder",
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
        )
        return {name: "" for name in credential_vars}

    def test_official_sdk_imports_resolve(self):
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkcore.http.http_config import HttpConfig
        from huaweicloudsdkecs.v2 import EcsClient, ListServersDetailsRequest
        from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion
        for obj in (BasicCredentials, Region, HttpConfig,
                    EcsClient, ListServersDetailsRequest, EcsRegion):
            self.assertTrue(callable(obj), obj)

    def test_sdk_fallback_returns_servers_with_env_credentials(self):
        env = dict(self._clean_credential_env(),
                   HUAWEI_ACCESS_KEY="test-ak",
                   HUAWEI_SECRET_KEY="test-sk")
        with mock.patch.dict(os.environ, env, clear=True):
            servers = list_servers_via_sdk("cn-north-4")
        self.assertEqual(servers, [SERVER_1, SERVER_2])
        credentials = self._captured_credentials
        self.assertIsNotNone(credentials)
        self.assertEqual(getattr(credentials, "ak", None), "test-ak")
        self.assertEqual(getattr(credentials, "sk", None), "test-sk")
        self.assertEqual(getattr(self._captured_region, "id", None), "cn-north-4")

    def test_sdk_fallback_missing_env_credentials_raises_config(self):
        with mock.patch.dict(os.environ, self._clean_credential_env(),
                             clear=True):
            with self.assertRaises(ConfigError) as ctx:
                list_servers_via_sdk("cn-north-4")
        message = str(ctx.exception)
        self.assertIn("AK/SK", message)
        self.assertNotIn("未安装", message)

    def test_sdk_fallback_alternative_env_prefixes(self):
        env = dict(self._clean_credential_env(),
                   HW_ACCESS_KEY="alt-ak", HW_SECRET_KEY="alt-sk")
        with mock.patch.dict(os.environ, env, clear=True):
            list_servers_via_sdk("cn-north-4")
        self.assertEqual(getattr(self._captured_credentials, "ak", None), "alt-ak")


class TestNormalizeAndRender(unittest.TestCase):
    def test_normalize_flattens_flavor_az_and_ips(self):
        flat = normalize_server(SERVER_1)
        self.assertEqual(flat["flavor"], "s6.large.2")
        self.assertEqual(flat["vcpus"], "2")
        self.assertEqual(flat["ram"], "4096")
        self.assertEqual(flat["availability_zone"], "cn-north-4a")
        self.assertEqual(flat["privateIps"], "192.168.0.10")
        self.assertEqual(flat["publicIps"], "-")
        self.assertEqual(flat["image_id"], "img-0001")

    def test_normalize_public_and_private_ips(self):
        flat = normalize_server(SERVER_2)
        self.assertEqual(flat["privateIps"], "192.168.0.11")
        self.assertEqual(flat["publicIps"], "10.0.0.5")

    def test_normalize_missing_fields_dash(self):
        flat = normalize_server({"id": "ecs-x"})
        self.assertEqual(flat["availability_zone"], "-")
        self.assertEqual(flat["privateIps"], "-")
        self.assertEqual(flat["publicIps"], "-")

    def test_normalize_sdk_attr_names(self):
        flat = normalize_server({
            "id": "ecs-y",
            "os_ext_a_zavailability_zone": "cn-north-4c",
            "access_i_pv4": "9.9.9.9",
        })
        self.assertEqual(flat["availability_zone"], "cn-north-4c")
        self.assertEqual(flat["publicIps"], "9.9.9.9")

    def test_table_contains_basic_info(self):
        table = render_table([SERVER_1, SERVER_2])
        for fragment in ("ecs-web-01", "ecs-0001", "ACTIVE", "s6.large.2",
                         "cn-north-4a", "192.168.0.10", "ecs-db-02",
                         "SHUTOFF", "10.0.0.5"):
            self.assertIn(fragment, table)

    def test_names(self):
        self.assertEqual(
            server_names([SERVER_1, SERVER_2]), ["ecs-web-01", "ecs-db-02"])

    def test_names_fallback_to_id(self):
        self.assertEqual(server_names([{"id": "ecs-9"}]), ["ecs-9"])

    def test_summary_lines_include_id(self):
        lines = server_summary_lines([SERVER_1, SERVER_2])
        self.assertEqual(lines[0], "ecs-web-01  (id: ecs-0001)")
        self.assertEqual(lines[1], "ecs-db-02  (id: ecs-0002)")


class TestMain(unittest.TestCase):
    def _run(self, argv, results):
        fake = FakeRunner(results)
        with mock.patch("list_ecs.subprocess.run", fake), \
                mock.patch("sys.stdout") as stdout, \
                mock.patch("sys.stderr") as stderr:
            rc = main(argv)
        out = "".join(c[0][0] for c in stdout.write.call_args_list)
        err = "".join(c[0][0] for c in stderr.write.call_args_list)
        return rc, out, err

    def test_table_output(self):
        rc, out, err = self._run(
            ["--region", "cn-north-4"],
            [(json.dumps({"servers": [SERVER_1, SERVER_2], "count": 2}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("ECS 实例列表", out)
        self.assertIn("ecs-web-01", out)
        self.assertIn("ACTIVE", out)
        self.assertEqual(err, "")

    def test_json_output(self):
        rc, out, err = self._run(
            ["--json"],
            [(json.dumps({"servers": [SERVER_1], "count": 1}), "", 0)])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload, [SERVER_1])

    def test_names_only_output(self):
        rc, out, err = self._run(
            ["--names-only"],
            [(json.dumps({"servers": [SERVER_1, SERVER_2], "count": 2}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("ecs-web-01", out)
        self.assertIn("ecs-0001", out)
        self.assertIn("ecs-db-02", out)
        self.assertNotIn("flavor", out)

    def test_empty_instances_message(self):
        rc, out, err = self._run(
            ["--region", "cn-south-1"],
            [(json.dumps({"servers": [], "count": 0}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("无 ECS 实例", out)
        self.assertIn("cn-south-1", out)

    def test_empty_with_filter_message(self):
        rc, out, _ = self._run(
            ["--status", "ACTIVE"],
            [(json.dumps({"servers": [], "count": 0}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("status=ACTIVE", out)

    def test_status_filter_main_server_side(self):
        # End-to-end: --status ACTIVE is forwarded to the server (ECS has a
        # real status query parameter) and only matching servers are returned.
        fake = FakeRunner([
            (json.dumps({"servers": [SERVER_1], "count": 1}), "", 0)])
        with mock.patch("list_ecs.subprocess.run", fake), \
                mock.patch("sys.stdout") as stdout, \
                mock.patch("sys.stderr"):
            rc = main(["--status", "ACTIVE"])
        out = "".join(c[0][0] for c in stdout.write.call_args_list)
        self.assertEqual(rc, 0)
        self.assertIn("ecs-web-01", out)
        self.assertIn("--status=ACTIVE", fake.calls[0])

    def test_empty_json_output(self):
        rc, out, err = self._run(
            ["--json"],
            [(json.dumps({"servers": [], "count": 0}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [])

    def test_empty_names_only_output(self):
        rc, out, err = self._run(
            ["--names-only"],
            [(json.dumps({"servers": [], "count": 0}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertIn("共 0 个", out)
        self.assertNotIn("无 ECS 实例", out)

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
        with mock.patch("list_ecs.list_servers_via_sdk",
                        side_effect=ConfigError("huaweicloudsdkecs 未安装")):
            rc, out, err = self._run([], [FileNotFoundError()])
        self.assertEqual(rc, 1)
        self.assertIn("未安装", err)

    def test_hcloud_missing_falls_back_to_sdk(self):
        with mock.patch("list_ecs.list_servers_via_sdk",
                        return_value=[SERVER_1]):
            rc, out, err = self._run([], [FileNotFoundError()])
        self.assertEqual(rc, 0)
        self.assertIn("ecs-web-01", out)

    def test_write_intent_argv_blocked(self):
        rc, out, err = self._run(["--operation", "DeleteServers"], [])
        self.assertEqual(rc, 1)
        self.assertIn("写操作意图", err)

    def test_write_flag_argv_blocked(self):
        rc, out, err = self._run(["--create-server"], [])
        self.assertEqual(rc, 1)
        self.assertIn("写操作意图", err)

    def test_status_rebuild_not_blocked(self):
        # `--status REBUILD` is a legitimate read filter — must NOT be blocked.
        rc, out, err = self._run(
            ["--status", "REBUILD"],
            [(json.dumps({"servers": [SERVER_2], "count": 1}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertNotIn("写操作意图", err)

    def test_name_write_word_not_blocked(self):
        rc, out, err = self._run(
            ["--name", "stop-me"],
            [(json.dumps({"servers": [SERVER_1], "count": 1}), "", 0)])
        self.assertEqual(rc, 0)
        self.assertNotIn("写操作意图", err)


class TestMarkdownReport(unittest.TestCase):
    """render_markdown / naming helpers (offline, no file system)."""

    def test_render_contains_region_time_total_and_table(self):
        md = render_markdown("cn-north-4", [SERVER_1, SERVER_2],
                             datetime.datetime(2026, 10, 20, 9, 30, 0))
        self.assertIn("# Huawei Cloud ECS 实例清单", md)
        self.assertIn("**Region**: cn-north-4", md)
        self.assertIn("**查询时间**: 2026-10-20 09:30:00", md)
        self.assertIn("**实例总数**: 2", md)
        self.assertIn("| 实例名称 | 实例 ID |", md)
        self.assertIn("| --- | --- |", md)
        self.assertIn("| ecs-web-01 | ecs-0001 |", md)
        self.assertIn("| ecs-db-02 | ecs-0002 |", md)

    def test_render_generated_at_defaults_to_now(self):
        md = render_markdown("cn-north-4", [SERVER_1])
        self.assertRegex(md, r"\*\*查询时间\*\*: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_render_name_falls_back_to_id(self):
        md = render_markdown("cn-north-4", [{"id": "ecs-9"}],
                             datetime.datetime(2026, 10, 20))
        self.assertIn("| ecs-9 | ecs-9 |", md)

    def test_render_empty_list_message_and_filters(self):
        md = render_markdown("cn-south-1", [], datetime.datetime(2026, 10, 20),
                            filters=["status=ACTIVE", "name=ecs-web"])
        self.assertIn("**实例总数**: 0", md)
        self.assertIn("共 0 个实例", md)
        self.assertIn("status=ACTIVE, name=ecs-web", md)
        self.assertNotIn("| 实例名称", md)

    def test_render_empty_list_without_filters(self):
        md = render_markdown("cn-south-1", [], datetime.datetime(2026, 10, 20))
        self.assertIn("共 0 个实例", md)
        self.assertNotIn("过滤条件", md)

    def test_render_escapes_pipes_and_newlines(self):
        md = render_markdown("cn-north-4", [{"id": "ecs|1", "name": "web\n01"}],
                             datetime.datetime(2026, 10, 20))
        self.assertIn("| web 01 | ecs\\|1 |", md)

    def test_render_multi_column_header(self):
        # Issue #20: the inventory table must be multi-column (>2) and carry the
        # fixed name/ID/status/flavor/vCPU/memory/AZ/private-IP/public-IP set.
        md = render_markdown("cn-north-4", [SERVER_1, SERVER_2],
                             datetime.datetime(2026, 10, 20))
        header = "| %s |" % " | ".join(label for _, label in MD_TABLE_COLUMNS)
        self.assertIn(header, md)
        self.assertIn("| --- | --- | --- | --- | --- | --- | --- | --- | --- |", md)
        labels = [label for _, label in MD_TABLE_COLUMNS]
        for expected in ("实例名称", "实例 ID", "状态", "规格", "vCPU", "内存",
                         "可用区", "私网IP", "公网IP"):
            self.assertIn(expected, labels)
        self.assertGreater(len(MD_TABLE_COLUMNS), 2)

    def test_render_multi_column_rows(self):
        md = render_markdown("cn-north-4", [SERVER_1, SERVER_2],
                             datetime.datetime(2026, 10, 20))
        self.assertIn(
            "| ecs-web-01 | ecs-0001 | ACTIVE | s6.large.2 | 2 | 4096 | "
            "cn-north-4a | 192.168.0.10 | - |", md)
        # SERVER_2 has a floating IP -> comma-joined public IP value.
        self.assertIn(
            "| ecs-db-02 | ecs-0002 | SHUTOFF | s6.xlarge.2 | 4 | 8192 | "
            "cn-north-4b | 192.168.0.11 | 10.0.0.5 |", md)

    def test_render_multi_value_ips_comma_joined(self):
        server = {
            "id": "ecs-multi",
            "name": "ecs-multi",
            "addresses": {
                "vpc-subnet": [
                    {"addr": "192.168.0.20", "OS-EXT-IPS:type": "fixed"},
                    {"addr": "192.168.0.21", "OS-EXT-IPS:type": "fixed"},
                ]
            },
        }
        md = render_markdown("cn-north-4", [server], datetime.datetime(2026, 10, 20))
        self.assertIn("192.168.0.20,192.168.0.21", md)

    def test_render_missing_columns_render_dash(self):
        md = render_markdown("cn-north-4", [{"id": "ecs-9"}],
                             datetime.datetime(2026, 10, 20))
        self.assertIn(
            "| ecs-9 | ecs-9 | - | - | - | - | - | - | - |", md)

    def test_default_name_uses_region_and_date(self):
        self.assertEqual(
            default_markdown_name("cn-north-4",
                                  datetime.datetime(2026, 10, 20, 23, 59)),
            "ecs-list-cn-north-4-20261020.md")
        self.assertEqual(
            default_markdown_name("cn-south-1", datetime.datetime(2026, 1, 2)),
            "ecs-list-cn-south-1-20260102.md")

    def test_format_query_time(self):
        self.assertEqual(
            format_query_time(datetime.datetime(2026, 1, 2, 3, 4, 5)),
            "2026-01-02 03:04:05")
        self.assertRegex(format_query_time(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_active_filter_descriptions(self):
        self.assertEqual(active_filter_descriptions("ACTIVE", "ecs-web"),
                         ["status=ACTIVE", "name=ecs-web"])
        self.assertEqual(active_filter_descriptions(status="ACTIVE"),
                         ["status=ACTIVE"])
        self.assertEqual(active_filter_descriptions(), [])


class TestMarkdownFileWrite(unittest.TestCase):
    """write_markdown_file: UTF-8, atomic, no half file on failure."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ecs-md-write-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_writes_utf8_and_returns_absolute_path(self):
        target = os.path.join(self.dir, "out.md")
        path = write_markdown_file(target, "# 实例清单\ntext\n")
        self.assertEqual(path, os.path.abspath(target))
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "# 实例清单\ntext\n")
        # No temporary sibling left behind.
        self.assertEqual(os.listdir(self.dir), ["out.md"])

    def test_overwrites_existing_report(self):
        target = os.path.join(self.dir, "out.md")
        write_markdown_file(target, "old")
        write_markdown_file(target, "new")
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "new")

    def test_missing_directory_raises_and_leaves_nothing(self):
        target = os.path.join(self.dir, "nope", "out.md")
        with self.assertRaises(OutputError) as ctx:
            write_markdown_file(target, "x")
        self.assertIn("无法写入 Markdown 文件", str(ctx.exception))
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(os.path.dirname(target)))
        self.assertEqual(os.listdir(self.dir), [])

    def test_unwritable_target_raises_and_leaves_no_temp(self):
        # A directory as the target makes the final move fail everywhere
        # (root included, unlike a chmod-based permission test).
        target = os.path.join(self.dir, "target-dir")
        os.mkdir(target)
        with self.assertRaises(OutputError) as ctx:
            write_markdown_file(target, "x")
        self.assertIn("无法写入 Markdown 文件", str(ctx.exception))
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(os.listdir(self.dir), ["target-dir"])


class TestMainMarkdownOutput(unittest.TestCase):
    """`main()` end-to-end for --md-file / --output-md (mocked hcloud)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ecs-md-main-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self._cwd = os.getcwd()
        self.addCleanup(os.chdir, self._cwd)
        os.chdir(self.dir)

    def _run(self, argv, results):
        fake = FakeRunner(results)
        with mock.patch("list_ecs.subprocess.run", fake), \
                mock.patch("sys.stdout") as stdout, \
                mock.patch("sys.stderr") as stderr:
            rc = main(argv)
        out = "".join(c[0][0] for c in stdout.write.call_args_list)
        err = "".join(c[0][0] for c in stderr.write.call_args_list)
        return rc, out, err

    @staticmethod
    def _page(servers):
        return [(json.dumps({"servers": servers, "count": len(servers)}), "", 0)]

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_explicit_path_creates_report_and_hints_absolute_path(self):
        target = os.path.join(self.dir, "inventory.md")
        rc, out, err = self._run(
            ["--md-file", target], self._page([SERVER_1, SERVER_2]))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertTrue(os.path.isfile(target))
        content = self._read(target)
        full_header = "| %s |" % " | ".join(label for _, label in MD_TABLE_COLUMNS)
        for fragment in ("**Region**: cn-north-4", "**查询时间**:",
                         "**实例总数**: 2", full_header,
                         "| ecs-web-01 | ecs-0001 | ACTIVE | s6.large.2 | 2 | "
                         "4096 | cn-north-4a | 192.168.0.10 | - |"):
            self.assertIn(fragment, content)
        self.assertIn(os.path.abspath(target), out)
        # The default stdout table is still printed (additive, not exclusive).
        self.assertIn("ECS 实例列表", out)

    def test_no_value_uses_default_file_name(self):
        rc, out, err = self._run(["--md-file"], self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        expected = "ecs-list-cn-north-4-%s.md" % datetime.date.today().strftime("%Y%m%d")
        self.assertEqual(os.listdir(self.dir), [expected])
        self.assertIn(os.path.abspath(expected), out)
        self.assertIn("| ecs-web-01 | ecs-0001 |", self._read(expected))

    def test_no_value_uses_requested_region_in_default_name(self):
        rc, out, err = self._run(["-r", "cn-south-1", "--md-file"],
                                 self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        expected = "ecs-list-cn-south-1-%s.md" % datetime.date.today().strftime("%Y%m%d")
        self.assertEqual(os.listdir(self.dir), [expected])
        self.assertIn("**Region**: cn-south-1", self._read(expected))

    def test_output_md_alias(self):
        rc, out, err = self._run(["--output-md", "alias.md"],
                                 self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "alias.md")))

    def test_path_with_write_words_not_blocked(self):
        rc, out, err = self._run(["--md-file=ecs-delete-report.md"],
                                 self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        self.assertNotIn("写操作意图", err)
        self.assertTrue(
            os.path.isfile(os.path.join(self.dir, "ecs-delete-report.md")))

    def test_empty_list_report_exits_zero(self):
        rc, out, err = self._run(["--status", "ACTIVE", "--md-file", "empty.md"],
                                 self._page([]))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        content = self._read(os.path.join(self.dir, "empty.md"))
        self.assertIn("共 0 个实例", content)
        self.assertIn("status=ACTIVE", content)
        self.assertIn("**实例总数**: 0", content)
        # stdout behaviour for an empty list is unchanged.
        self.assertIn("无 ECS 实例", out)

    def test_write_failure_reports_error_and_exits_one(self):
        target = os.path.join(self.dir, "absent-dir", "out.md")
        rc, out, err = self._run(["--md-file", target], self._page([SERVER_1]))
        self.assertEqual(rc, 1)
        self.assertIn("[错误]", err)
        self.assertIn("无法写入 Markdown 文件", err)
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(os.path.dirname(target)))
        # No half file / temp sibling anywhere.
        self.assertEqual(os.listdir(self.dir), [])

    def test_json_mode_unchanged_and_no_file_without_flag(self):
        rc, out, err = self._run(["--json"], self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [SERVER_1])
        self.assertEqual(os.listdir(self.dir), [])

    def test_names_only_md_is_additive(self):
        rc, out, err = self._run(["--names-only", "--md-file", "inv.md"],
                                 self._page([SERVER_1, SERVER_2]))
        self.assertEqual(rc, 0)
        self.assertIn("ecs-web-01  (id: ecs-0001)", out)
        self.assertIn("| ecs-db-02 | ecs-0002 |",
                      self._read(os.path.join(self.dir, "inv.md")))

    def test_md_written_before_write_intent_still_blocked(self):
        rc, out, err = self._run(["--md-file", "out.md", "--operation",
                                  "DeleteServers"], [])
        self.assertEqual(rc, 1)
        self.assertIn("写操作意图", err)
        self.assertEqual(os.listdir(self.dir), [])


class TestErrorHierarchy(unittest.TestCase):
    def test_subclasses(self):
        for exc in (GuardError, ConfigError, AuthError, ApiError, OutputError):
            self.assertTrue(issubclass(exc, EcsListError))


class TestTxtReport(unittest.TestCase):
    """render_txt / default_txt_name (offline, no file system)."""

    def test_render_contains_region_time_total_and_inventory(self):
        txt = render_txt("cn-north-4", [SERVER_1, SERVER_2],
                         datetime.datetime(2026, 10, 20, 9, 30, 0))
        self.assertIn("Huawei Cloud ECS 实例清单", txt)
        self.assertIn("Region: cn-north-4", txt)
        self.assertIn("查询时间: 2026-10-20 09:30:00", txt)
        self.assertIn("实例总数: 2", txt)
        self.assertIn("实例清单", txt)
        # Header uses the same fixed column set as the Markdown export.
        header = " | ".join(label for _, label in MD_TABLE_COLUMNS)
        self.assertIn(header, txt)

    def test_render_generated_at_defaults_to_now(self):
        txt = render_txt("cn-north-4", [SERVER_1])
        self.assertRegex(txt, r"查询时间: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_render_data_rows_and_separator(self):
        txt = render_txt("cn-north-4", [SERVER_1, SERVER_2],
                         datetime.datetime(2026, 10, 20))
        self.assertIn(
            "ecs-web-01 | ecs-0001 | ACTIVE | s6.large.2 | 2 | 4096 | "
            "cn-north-4a | 192.168.0.10 | -", txt)
        self.assertIn(
            "ecs-db-02 | ecs-0002 | SHUTOFF | s6.xlarge.2 | 4 | 8192 | "
            "cn-north-4b | 192.168.0.11 | 10.0.0.5", txt)

    def test_render_name_falls_back_to_id(self):
        txt = render_txt("cn-north-4", [{"id": "ecs-9"}],
                         datetime.datetime(2026, 10, 20))
        self.assertIn("ecs-9 | ecs-9 | - | - | - | - | - | - | -", txt)

    def test_render_empty_list_message_and_filters(self):
        txt = render_txt("cn-south-1", [], datetime.datetime(2026, 10, 20),
                         filters=["status=ACTIVE", "name=ecs-web"])
        self.assertIn("实例总数: 0", txt)
        self.assertIn("过滤条件: status=ACTIVE, name=ecs-web", txt)
        self.assertIn("共 0 个实例", txt)
        self.assertIn("（过滤条件: status=ACTIVE, name=ecs-web）", txt)
        self.assertNotIn("实例名称", txt)

    def test_render_empty_list_without_filters(self):
        txt = render_txt("cn-south-1", [], datetime.datetime(2026, 10, 20))
        self.assertIn("共 0 个实例", txt)
        self.assertNotIn("过滤条件", txt)

    def test_render_folds_newlines_and_keeps_plain_text(self):
        # Pure text carries no Markdown escaping: a pipe stays literal, while a
        # newline is folded so an instance stays on a single line.
        txt = render_txt("cn-north-4", [{"id": "ecs|1", "name": "web\n01"}],
                         datetime.datetime(2026, 10, 20))
        self.assertIn("web 01 | ecs|1 | -", txt)
        self.assertNotIn("\\|", txt)

    def test_render_multi_value_ips_comma_joined(self):
        server = {
            "id": "ecs-multi",
            "name": "ecs-multi",
            "addresses": {
                "vpc-subnet": [
                    {"addr": "192.168.0.20", "OS-EXT-IPS:type": "fixed"},
                    {"addr": "192.168.0.21", "OS-EXT-IPS:type": "fixed"},
                ]
            },
        }
        txt = render_txt("cn-north-4", [server], datetime.datetime(2026, 10, 20))
        self.assertIn("192.168.0.20,192.168.0.21", txt)

    def test_default_name_uses_region_and_date(self):
        self.assertEqual(
            default_txt_name("cn-north-4",
                             datetime.datetime(2026, 10, 20, 23, 59)),
            "ecs-list-cn-north-4-20261020.txt")
        self.assertEqual(
            default_txt_name("cn-south-1", datetime.datetime(2026, 1, 2)),
            "ecs-list-cn-south-1-20260102.txt")


class TestTxtFileWrite(unittest.TestCase):
    """write_txt_file: UTF-8, atomic, no half file on failure."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ecs-txt-write-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_writes_utf8_and_returns_absolute_path(self):
        target = os.path.join(self.dir, "out.txt")
        path = write_txt_file(target, "实例清单\ntext\n")
        self.assertEqual(path, os.path.abspath(target))
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "实例清单\ntext\n")
        # No temporary sibling left behind.
        self.assertEqual(os.listdir(self.dir), ["out.txt"])

    def test_overwrites_existing_report(self):
        target = os.path.join(self.dir, "out.txt")
        write_txt_file(target, "old")
        write_txt_file(target, "new")
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "new")

    def test_missing_directory_raises_and_leaves_nothing(self):
        target = os.path.join(self.dir, "nope", "out.txt")
        with self.assertRaises(OutputError) as ctx:
            write_txt_file(target, "x")
        self.assertIn("无法写入 TXT 文件", str(ctx.exception))
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(os.path.dirname(target)))
        self.assertEqual(os.listdir(self.dir), [])

    def test_unwritable_target_raises_and_leaves_no_temp(self):
        # A directory as the target makes the final move fail everywhere.
        target = os.path.join(self.dir, "target-dir")
        os.mkdir(target)
        with self.assertRaises(OutputError) as ctx:
            write_txt_file(target, "x")
        self.assertIn("无法写入 TXT 文件", str(ctx.exception))
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(os.listdir(self.dir), ["target-dir"])


class TestMainTxtOutput(unittest.TestCase):
    """`main()` end-to-end for --txt-file / --output-txt (mocked hcloud)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ecs-txt-main-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self._cwd = os.getcwd()
        self.addCleanup(os.chdir, self._cwd)
        os.chdir(self.dir)

    def _run(self, argv, results):
        fake = FakeRunner(results)
        with mock.patch("list_ecs.subprocess.run", fake), \
                mock.patch("sys.stdout") as stdout, \
                mock.patch("sys.stderr") as stderr:
            rc = main(argv)
        out = "".join(c[0][0] for c in stdout.write.call_args_list)
        err = "".join(c[0][0] for c in stderr.write.call_args_list)
        return rc, out, err

    @staticmethod
    def _page(servers):
        return [(json.dumps({"servers": servers, "count": len(servers)}), "", 0)]

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_explicit_path_creates_report_and_hints_absolute_path(self):
        target = os.path.join(self.dir, "inventory.txt")
        rc, out, err = self._run(
            ["--txt-file", target], self._page([SERVER_1, SERVER_2]))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertTrue(os.path.isfile(target))
        content = self._read(target)
        header = " | ".join(label for _, label in MD_TABLE_COLUMNS)
        for fragment in ("Region: cn-north-4", "查询时间:", "实例总数: 2",
                         header,
                         "ecs-web-01 | ecs-0001 | ACTIVE | s6.large.2 | 2 | "
                         "4096 | cn-north-4a | 192.168.0.10 | -"):
            self.assertIn(fragment, content)
        self.assertIn(os.path.abspath(target), out)
        # The default stdout table is still printed (additive, not exclusive).
        self.assertIn("ECS 实例列表", out)

    def test_no_value_uses_default_file_name(self):
        rc, out, err = self._run(["--txt-file"], self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        expected = "ecs-list-cn-north-4-%s.txt" % datetime.date.today().strftime("%Y%m%d")
        self.assertEqual(os.listdir(self.dir), [expected])
        self.assertIn(os.path.abspath(expected), out)
        self.assertIn("ecs-web-01 | ecs-0001 |", self._read(expected))

    def test_no_value_uses_requested_region_in_default_name(self):
        rc, out, err = self._run(["-r", "cn-south-1", "--txt-file"],
                                 self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        expected = "ecs-list-cn-south-1-%s.txt" % datetime.date.today().strftime("%Y%m%d")
        self.assertEqual(os.listdir(self.dir), [expected])
        self.assertIn("Region: cn-south-1", self._read(expected))

    def test_output_txt_alias(self):
        rc, out, err = self._run(["--output-txt", "alias.txt"],
                                 self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "alias.txt")))

    def test_path_with_write_words_not_blocked(self):
        rc, out, err = self._run(["--txt-file=ecs-delete-report.txt"],
                                 self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        self.assertNotIn("写操作意图", err)
        self.assertTrue(
            os.path.isfile(os.path.join(self.dir, "ecs-delete-report.txt")))

    def test_empty_list_report_exits_zero(self):
        rc, out, err = self._run(["--status", "ACTIVE", "--txt-file", "empty.txt"],
                                 self._page([]))
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        content = self._read(os.path.join(self.dir, "empty.txt"))
        self.assertIn("共 0 个实例", content)
        self.assertIn("status=ACTIVE", content)
        self.assertIn("实例总数: 0", content)
        # stdout behaviour for an empty list is unchanged.
        self.assertIn("无 ECS 实例", out)

    def test_write_failure_reports_error_and_exits_one(self):
        target = os.path.join(self.dir, "absent-dir", "out.txt")
        rc, out, err = self._run(["--txt-file", target], self._page([SERVER_1]))
        self.assertEqual(rc, 1)
        self.assertIn("[错误]", err)
        self.assertIn("无法写入 TXT 文件", err)
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(os.path.dirname(target)))
        # No half file / temp sibling anywhere.
        self.assertEqual(os.listdir(self.dir), [])

    def test_json_mode_unchanged_and_no_file_without_flag(self):
        rc, out, err = self._run(["--json"], self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [SERVER_1])
        self.assertEqual(os.listdir(self.dir), [])

    def test_names_only_txt_is_additive(self):
        rc, out, err = self._run(["--names-only", "--txt-file", "inv.txt"],
                                 self._page([SERVER_1, SERVER_2]))
        self.assertEqual(rc, 0)
        self.assertIn("ecs-web-01  (id: ecs-0001)", out)
        self.assertIn("ecs-db-02 | ecs-0002 |",
                      self._read(os.path.join(self.dir, "inv.txt")))

    def test_txt_and_md_and_json_all_stacked(self):
        rc, out, err = self._run(
            ["--json", "--md-file", "out.md", "--txt-file", "out.txt"],
            self._page([SERVER_1]))
        self.assertEqual(rc, 0)
        # stdout mode (JSON) is unchanged; the file-path hints are appended
        # after it, exactly like the existing additive Markdown export.
        self.assertEqual(json.loads(out.split("已生成")[0]), [SERVER_1])
        self.assertIn("已生成 Markdown 文件", out)
        self.assertIn("已生成 TXT 文件", out)
        self.assertEqual(sorted(os.listdir(self.dir)), ["out.md", "out.txt"])
        self.assertIn("ecs-web-01 | ecs-0001 |",
                      self._read(os.path.join(self.dir, "out.txt")))

    def test_txt_written_before_write_intent_still_blocked(self):
        rc, out, err = self._run(["--txt-file", "out.txt", "--operation",
                                  "DeleteServers"], [])
        self.assertEqual(rc, 1)
        self.assertIn("写操作意图", err)
        self.assertEqual(os.listdir(self.dir), [])


if __name__ == "__main__":
    unittest.main()
