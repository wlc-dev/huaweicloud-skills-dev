#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inventory Huawei Cloud CSS (Cloud Search Service) clusters — read-only.

Primary path: KooCLI ``hcloud CSS ListClustersDetails`` plus, when a single
cluster is drilled into, ``ShowClusterDetail`` and ``ShowClusterVolumeUsage``.
When the hcloud binary is unavailable the script falls back to the official
``huaweicloudsdkcss`` v1 SDK (``CssClient``) with the same semantics.

Verified API facts (KooCLI 7.3.12 + local ``huaweicloudsdkcss`` v1 metadata):

- ``ListClustersDetails`` — ``GET /v1.0/{project_id}/clusters``; query params
  ``offset`` (1-based, default 1), ``limit`` (default 10, max 100),
  ``datastoreType``. Response ``{"clusters": [...], "totalSize": N}``.
- ``ShowClusterDetail`` — ``GET /v1.0/{project_id}/clusters/{cluster_id}``.
- ``ShowClusterVolumeUsage`` — ``GET /v1.0/{project_id}/clusters/{cluster_id}/volume``;
  response ``{"diskInfoList": [{"id","name","diskCapacity","diskUsed","percentage"}]}``.
- Cluster / node status: ``100`` creating, ``200`` available, ``303`` unavailable
  (for example a failed creation). Anything other than ``200`` is reported as
  abnormal and highlighted.

Read-only by design: only the three GET operations above are ever constructed,
and a write-intent guard rejects mutating intent before any command runs.

Usage:
    python3 scripts/list_css_clusters.py [--region cn-north-4]
                                         [--json | --table]
                                         [--name NAME [--fuzzy]]
                                         [--cluster-id CLUSTER_ID]
                                         [--status 200|100|303|abnormal]
                                         [--datastore-type elasticsearch]
                                         [--limit 10]

Environment overrides (mostly for tests):
    CSS_LIST_HCLOUD_BIN   hcloud executable (default "hcloud")
    CSS_LIST_HCLOUD_ARGS  extra args appended AFTER the read-only argv (guarded)
    CSS_LIST_SQC_BIN      skill-quality-cli executable override
    SKILL_QUALITY_REPORT  set to 0 to skip the skill-quality-cli wrapper
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# Never emit __pycache__/*.pyc into the shipped skill directory.
sys.dont_write_bytecode = True

DEFAULT_REGION = "cn-north-4"
DEFAULT_LIMIT = 10
MAX_LIMIT = 100
DEFAULT_MAX_PAGES = 200

SERVICE = "CSS"
LIST_OPERATION = "ListClustersDetails"
DETAIL_OPERATION = "ShowClusterDetail"
VOLUME_OPERATION = "ShowClusterVolumeUsage"
ALLOWED_OPERATIONS = (LIST_OPERATION, DETAIL_OPERATION, VOLUME_OPERATION)
ALLOWED_ACTIONS = ("list", "detail", "volume")

REST_PATHS = {
    LIST_OPERATION: "/v1.0/{project_id}/clusters",
    DETAIL_OPERATION: "/v1.0/{project_id}/clusters/{cluster_id}",
    VOLUME_OPERATION: "/v1.0/{project_id}/clusters/{cluster_id}/volume",
}

# Status codes documented in the CSS v1 API reference / SDK models.
CLUSTER_STATUS_MEANINGS = {
    "100": "创建中",
    "200": "可用",
    "303": "不可用（如创建失败）",
}
NODE_STATUS_MEANINGS = {
    "100": "创建中",
    "200": "可用",
    "303": "不可用（如创建失败）",
}
NORMAL_STATUS = "200"
CAPACITY_ALERT_PERCENT = 80.0

SKILL_QUALITY_SKILL_NAME = "huawei-cloud-css-cluster-list"
_QUALITY_OFF_VALUES = ("0", "false", "no", "off")
_USE_ERROR_MARKER = "[use_error]"

# Mutating CSS operations / intents — strictly rejected before execution.
WRITE_INTENT_KEYWORDS = (
    "createcluster",
    "deletecluster",
    "restartcluster",
    "rebootcluster",
    "rollingrestart",
    "updatecluster",
    "changeclustersubnet",
    "changesecuritygroup",
    "changemode",
    "extendcluster",
    "shrinkcluster",
    "addindependentnode",
    "retryupgradetask",
    "resetpassword",
    "createsnapshot",
    "deletesnapshot",
    "restoresnapshot",
    "startautocreatesnapshots",
    "createcnf",
    "deleteconf",
    "updatecnf",
    "createcerts",
    "deletecerts",
    "enableordisableelb",
    "startkibanapublic",
    "stopkibanapublic",
    "create",
    "delete",
    "update",
    "modify",
    "restart",
    "reboot",
    "scale",
    "shrink",
    "extend",
    "resize",
    "upgrade",
    "restore",
    "snapshot",
    "enable",
    "disable",
    "destroy",
    "remove",
    "modifycluster",
)

# Read-only option flags whose *values* are filter data that may legitimately
# contain status vocabulary (for example ``--status creating``); their values
# are dropped before the write-intent scan. ``--name`` is intentionally NOT in
# this list: a name such as ``create-me`` must still trip the guard.
_VALUE_STRIPPED_FLAGS = (
    "--region",
    "-r",
    "--cluster-id",
    "--cluster_id",
    "--status",
    "--datastore-type",
    "--datastore_type",
    "--limit",
    "--offset",
    "--max-pages",
    "--page-size",
)

# AK/SK environment variable names, read directly (never by enumerating
# os.environ). hcloud reads its own profile; the SDK fallback needs these.
_AK_ENV_NAMES = (
    "HUAWEICLOUD_SDK_AK",
    "CLOUD_SDK_AK",
    "HUAWEI_ACCESS_KEY",
    "HW_ACCESS_KEY",
    "HWC_ACCESS_KEY",
    "HUAWEI_AK",
    "HW_AK",
)
_SK_ENV_NAMES = (
    "HUAWEICLOUD_SDK_SK",
    "CLOUD_SDK_SK",
    "HUAWEI_SECRET_KEY",
    "HW_SECRET_KEY",
    "HWC_SECRET_KEY",
    "HUAWEI_SK",
    "HW_SK",
)
_PROJECT_ID_ENV_NAMES = (
    "HUAWEICLOUD_SDK_PROJECT_ID",
    "CLOUD_SDK_PROJECT_ID",
)

_CREDENTIAL_MISSING_PATTERNS = (
    "cli-ak",
    "cli-sk",
    "access key",
    "secret key",
    "credential",
    "configure",
    "未配置",
    "配置为空",
    "no ak",
    "no sk",
    "ak/sk",
)

_AUTH_PATTERNS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "apigw.0301",
    "css.0051",
    "does not allow",
    "认证失败",
    "权限不足",
    "permission denied",
)

_FIELD_MISSING = "-"


class CssListError(Exception):
    """Base error for the CSS cluster-list skill."""


class GuardError(CssListError):
    """A write intent was detected and blocked (skill is read-only)."""


class ConfigError(CssListError):
    """hcloud / SDK missing, or credentials (AK/SK) not configured."""


class AuthError(CssListError):
    """Authentication/authorization failure (invalid AK/SK or IAM 403)."""


class ApiError(CssListError):
    """hcloud / network / unexpected API failure."""


# ---------------------------------------------------------------------------
# Read-only guard
# ---------------------------------------------------------------------------

def _normalize(text):
    return re.sub(r"[\s_\-]+", "", str(text).lower())


def guard_write_intent(text):
    """Raise GuardError when ``text`` carries a mutating intent."""
    low = _normalize(text)
    for keyword in WRITE_INTENT_KEYWORDS:
        if keyword in low:
            raise GuardError(
                "检测到写操作意图（关键词: %s）。本 skill 仅支持只读查询"
                "（CSS ListClustersDetails / ShowClusterDetail / "
                "ShowClusterVolumeUsage），创建/删除/重启/扩缩容/快照等变更"
                "操作已被守卫拦截。" % keyword
            )
    return False


def scannable_argv(argv):
    """Drop values of read-only flags, keeping everything else scannable."""
    out = []
    skip_next = False
    stripped = set(_VALUE_STRIPPED_FLAGS)
    for token in argv:
        if skip_next:
            out.append("<value>")
            skip_next = False
            continue
        if token in stripped:
            out.append(token)
            skip_next = True
            continue
        if "=" in token:
            flag = token.split("=", 1)[0]
            if flag in stripped:
                out.append(flag + "=<value>")
                continue
        out.append(token)
    return " ".join(out)


def guard_operation(operation):
    """Only the read-only CSS operations may be executed."""
    if operation not in ALLOWED_OPERATIONS:
        raise GuardError(
            "不允许的操作 %r：本 skill 仅允许只读操作 %s。"
            % (operation, ", ".join(ALLOWED_OPERATIONS))
        )
    return True


def guard_action(action):
    """``--action`` must be a read-only action when supplied."""
    if action is None:
        return True
    if str(action).lower() not in ALLOWED_ACTIONS:
        raise GuardError(
            "不允许的操作意图 --action %s：本 skill 仅允许只读动作 %s。"
            % (action, ", ".join(ALLOWED_ACTIONS))
        )
    return True


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def clamp_limit(limit):
    """Clamp the ListClustersDetails page size into the documented 1..100."""
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT, False
    if value < 1:
        return 1, True
    if value > MAX_LIMIT:
        return MAX_LIMIT, True
    return value, False


def build_list_command(region, limit=DEFAULT_LIMIT, offset=1,
                       datastore_type=None):
    """Build the read-only hcloud ListClustersDetails argv."""
    argv = [
        SERVICE,
        LIST_OPERATION,
        "--cli-region=%s" % region,
        "--limit=%d" % limit,
        "--offset=%d" % offset,
    ]
    if datastore_type:
        argv.append("--datastoreType=%s" % datastore_type)
    return argv


def build_detail_command(region, cluster_id):
    """Build the read-only hcloud ShowClusterDetail argv."""
    if not cluster_id:
        raise ConfigError(
            "ShowClusterDetail（集群详情）需要提供 --cluster-id。"
            "可先执行默认列表查询获取集群 ID。"
        )
    return [
        SERVICE,
        DETAIL_OPERATION,
        "--cli-region=%s" % region,
        "--cluster_id=%s" % cluster_id,
    ]


def build_volume_command(region, cluster_id):
    """Build the read-only hcloud ShowClusterVolumeUsage argv."""
    if not cluster_id:
        raise ConfigError(
            "ShowClusterVolumeUsage（容量观测）需要提供 --cluster-id。"
        )
    return [
        SERVICE,
        VOLUME_OPERATION,
        "--cli-region=%s" % region,
        "--cluster_id=%s" % cluster_id,
    ]


# ---------------------------------------------------------------------------
# hcloud execution
# ---------------------------------------------------------------------------

def _hcloud_executable():
    return os.environ.get("CSS_LIST_HCLOUD_BIN") or "hcloud"


def _hcloud_resolvable():
    """True when the hcloud executable can actually be launched."""
    exe = _hcloud_executable()
    if os.path.dirname(exe):
        return os.path.isfile(exe) and os.access(exe, os.X_OK)
    return shutil.which(exe) is not None


def _quality_report_enabled():
    value = os.environ.get("SKILL_QUALITY_REPORT")
    if value is None:
        return True
    return value.strip().lower() not in _QUALITY_OFF_VALUES


def _skill_quality_executable():
    override = os.environ.get("CSS_LIST_SQC_BIN")
    if override:
        return override
    found = shutil.which("skill-quality-cli")
    if found:
        return found
    local = os.path.join(os.path.expanduser("~"), ".local", "bin",
                         "skill-quality-cli")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return None


def _hcloud_argv(argv):
    cmd = [_hcloud_executable()]
    cmd.extend(argv)
    extra = os.environ.get("CSS_LIST_HCLOUD_ARGS", "").split()
    if extra:
        cmd.extend(extra)
    return cmd


def build_hcloud_command(argv):
    """Build the execution argv, wrapped with skill-quality-cli when available.

    Every CLI call is reported as ``skill-quality-cli run --skill-name
    huawei-cloud-css-cluster-list -- hcloud ...``. Degrades to bare hcloud when
    the telemetry CLI is missing (or ``SKILL_QUALITY_REPORT=0``). An explicit
    ``CSS_LIST_HCLOUD_BIN`` override is run verbatim so offline tests and the
    SDK fallback stay deterministic.
    """
    hcloud_cmd = _hcloud_argv(argv)
    if os.environ.get("CSS_LIST_HCLOUD_BIN"):
        return hcloud_cmd
    if not _hcloud_resolvable():
        return hcloud_cmd
    if not _quality_report_enabled():
        return hcloud_cmd
    quality_cli = _skill_quality_executable()
    if not quality_cli:
        return hcloud_cmd
    return ([quality_cli, "run", "--skill-name", SKILL_QUALITY_SKILL_NAME, "--"]
            + hcloud_cmd)


def run_hcloud(argv):
    """Execute hcloud and return (stdout, stderr, returncode)."""
    cmd = build_hcloud_command(argv)
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=120, universal_newlines=True,
        )
    except FileNotFoundError:
        raise ConfigError(
            "未找到 hcloud（KooCLI）。请先安装 KooCLI 并完成认证配置，"
            "参见 references/cli-installation-guide.md；或安装官方 SDK"
            "（huaweicloudsdkcore / huaweicloudsdkcss）走 SDK 回退。"
        )
    except subprocess.TimeoutExpired:
        raise ApiError("hcloud 执行超时（120s），请检查网络后重试。")
    return proc.stdout or "", proc.stderr or "", proc.returncode


def extract_json(stdout):
    """Parse hcloud stdout as JSON; tolerate wrapper/noise lines."""
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise ApiError("hcloud 输出无法解析为 JSON：%s" % text[:200])


def _payload_error(payload):
    """Return the error text when a payload is a CSS/KooCLI error envelope.

    KooCLI returns HTTP-level API errors on stdout with exit code 0, e.g.
    ``{"errCode": "CSS.0051", "externalMessage": "..."}``. Such an envelope must
    surface as an explicit error, never as an empty cluster list.
    """
    if not isinstance(payload, dict):
        return None
    for code_key, msg_key in (
        ("errCode", "externalMessage"),
        ("error_code", "error_msg"),
        ("errorCode", "errorMsg"),
        ("code", "message"),
    ):
        code = payload.get(code_key)
        if code:
            msg = payload.get(msg_key) or ""
            return ("%s %s" % (code, msg)).strip()
    err = payload.get("error")
    if isinstance(err, dict):
        code = err.get("error_code") or err.get("code") or err.get("errCode") or ""
        msg = err.get("error_msg") or err.get("message") or err.get("externalMessage") or ""
        text = ("%s %s" % (code, msg)).strip()
        return text or None
    if isinstance(err, str) and err.strip():
        return err.strip()
    return None


def classify_hcloud_failure(stdout, stderr, returncode):
    """Map a failed hcloud invocation to a domain error with explicit hints."""
    blob = ((stderr or "") + " " + (stdout or "")).strip()
    low = blob.lower()
    if _USE_ERROR_MARKER in low:
        return ApiError(
            "hcloud 参数错误（KooCLI 拒绝了该参数组合，退出码 %s）。可用参数"
            "可通过 `hcloud CSS ListClustersDetails --cli-region=<region> --help`"
            " 查看。详情：%s" % (returncode, blob[:300])
        )
    if any(p in low for p in _CREDENTIAL_MISSING_PATTERNS) and not re.search(
            r"\b40[13]\b", blob):
        return ConfigError(
            "缺少 AK/SK 凭证：hcloud 未配置有效凭证。请先运行 hcloud configure 或"
            "设置凭证环境变量（严禁在对话中粘贴 AK/SK），参见"
            " references/cli-installation-guide.md。详情：%s" % blob[:300]
        )
    if any(p in low for p in _AUTH_PATTERNS):
        return AuthError(
            "无权限访问云搜索服务（CSS），请检查 IAM 权限（403：AK/SK 无效、"
            "未授予 css:cluster:list / css:cluster:get，或当前策略不允许该操作），"
            "参见 references/iam-policies.md。详情：%s" % blob[:300]
        )
    return ApiError(
        "hcloud 调用失败（退出码 %s）：%s" % (returncode, blob[:300])
    )


# ---------------------------------------------------------------------------
# Payload extraction
# ---------------------------------------------------------------------------

def extract_clusters(payload):
    """Pull the cluster list out of a ListClustersDetails response."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        value = payload.get("clusters")
        if isinstance(value, list):
            return value
    return []


def extract_total(payload):
    """Return the response totalSize as an int when present."""
    if not isinstance(payload, dict):
        return None
    for key in ("totalSize", "total_size", "total"):
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def extract_disk_info(payload):
    """Pull the per-node disk usage list out of a ShowClusterVolumeUsage body."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("body"), (dict, list)):
        return extract_disk_info(payload.get("body"))
    for key in ("diskInfoList", "disk_info_list", "diskInfos"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


# ---------------------------------------------------------------------------
# SDK fallback (huaweicloudsdkcss v1)
# ---------------------------------------------------------------------------

def _env_value(names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _sdk_credentials():
    """Build BasicCredentials from the whitelisted environment variables."""
    ak = _env_value(_AK_ENV_NAMES)
    sk = _env_value(_SK_ENV_NAMES)
    if not ak or not sk:
        raise ConfigError(
            "SDK 回退缺少 AK/SK 凭证：当前环境未检测到白名单中的 AK/SK 环境变量"
            "（如 HUAWEICLOUD_SDK_AK / CLOUD_SDK_AK 与 HUAWEICLOUD_SDK_SK /"
            " CLOUD_SDK_SK）。请在会话外设置其中之一（严禁在对话中粘贴 AK/SK），"
            "或安装 KooCLI 并配置 profile，参见 references/cli-installation-guide.md。"
        )
    project_id = _env_value(_PROJECT_ID_ENV_NAMES)
    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        # Credentials come from whitelisted env vars, never literals.
        return BasicCredentials(ak=ak, sk=sk, project_id=project_id)  # env-sourced, never literals
    except ImportError as exc:
        raise ConfigError(
            "未找到 hcloud（KooCLI），且 huaweicloudsdkcore 未安装，无法回退到"
            " SDK。请安装 KooCLI 或先运行 `python3 scripts/ensure_env.py`。详情：%s"
            % exc
        )


def _sdk_client(region):
    """Build the huaweicloudsdkcss v1 CssClient for the given region."""
    try:
        from huaweicloudsdkcss.v1 import CssClient
        from huaweicloudsdkcss.v1.region.css_region import CssRegion
    except ImportError as exc:
        raise ConfigError(
            "未找到 hcloud（KooCLI），且 huaweicloudsdkcss 未安装，无法回退到"
            " SDK。请安装 KooCLI 或先运行 `python3 scripts/ensure_env.py`"
            "（pip install huaweicloudsdkcore huaweicloudsdkcss）。详情：%s" % exc
        )
    try:
        try:
            region_obj = CssRegion.value_of(region)
        except (ValueError, KeyError, AttributeError):
            from huaweicloudsdkcore.region.region import Region
            region_obj = Region(region, "https://css.%s.myhuaweicloud.com" % region)
        from huaweicloudsdkcore.http.http_config import HttpConfig
        client = CssClient.new_builder() \
            .with_credentials(_sdk_credentials()) \
            .with_region(region_obj) \
            .with_http_config(HttpConfig.get_default_config()) \
            .build()
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(
            "SDK 初始化失败（region=%s）：%s。请检查 huaweicloudsdkcss 安装与区域"
            "配置。" % (region, exc)
        )
    return client


def _sdk_call(fn, request):
    try:
        return fn(request)
    except Exception as exc:
        low = str(exc).lower()
        if any(p in low for p in _AUTH_PATTERNS):
            raise AuthError(
                "无权限访问云搜索服务（CSS），请检查 IAM 权限"
                "（css:cluster:list / css:cluster:get，403）。详情：%s"
                % str(exc)[:300]
            )
        if isinstance(exc, CssListError):
            raise
        raise ApiError("SDK 调用失败：%s" % str(exc)[:300])


def _response_dict(response):
    """Best-effort conversion of an SDK response to a plain dict."""
    for attr in ("to_json_object", "to_dict"):
        fn = getattr(response, attr, None)
        if callable(fn):
            try:
                data = fn()
                if isinstance(data, dict):
                    return data
                if isinstance(data, list):
                    return {"diskInfoList": data}
            except Exception:
                continue
    body = getattr(response, "body", None)
    if isinstance(body, dict):
        return body
    if isinstance(body, list):
        return {"diskInfoList": body}
    return {}


def list_clusters_via_sdk(region, limit=DEFAULT_LIMIT, datastore_type=None,
                          max_pages=DEFAULT_MAX_PAGES):
    """SDK fallback: page through ListClustersDetails via huaweicloudsdkcss."""
    client = _sdk_client(region)
    from huaweicloudsdkcss.v1 import ListClustersDetailsRequest
    items = []
    seen = set()
    offset = 1
    total = None
    for _page in range(max_pages):
        request = ListClustersDetailsRequest(
            offset=offset, limit=limit, datastore_type=datastore_type)
        response = _sdk_call(client.list_clusters_details, request)
        data = _response_dict(response)
        batch = extract_clusters(data)
        total = extract_total(data)
        added = 0
        for record in batch:
            key = record.get("id") if isinstance(record, dict) else None
            if key is None:
                items.append(record)
                added += 1
                continue
            key = str(key)
            if key in seen:
                continue
            seen.add(key)
            items.append(record)
            added += 1
        if not batch or not added:
            break
        if total is not None and len(items) >= total:
            break
        if len(batch) < limit:
            break
        offset += len(batch)
    else:
        raise ApiError("SDK 翻页超过 %d 页仍未取完，已中止以防死循环。"
                       % max_pages)
    return items


def show_cluster_via_sdk(region, cluster_id):
    """SDK fallback: query one cluster through huaweicloudsdkcss v1."""
    client = _sdk_client(region)
    from huaweicloudsdkcss.v1 import ShowClusterDetailRequest
    request = ShowClusterDetailRequest(cluster_id=cluster_id)
    response = _sdk_call(client.show_cluster_detail, request)
    return _response_dict(response)


def show_volume_usage_via_sdk(region, cluster_id):
    """SDK fallback: per-node disk usage through huaweicloudsdkcss v1."""
    client = _sdk_client(region)
    from huaweicloudsdkcss.v1 import ShowClusterVolumeUsageRequest
    request = ShowClusterVolumeUsageRequest(cluster_id=cluster_id)
    response = _sdk_call(client.show_cluster_volume_usage, request)
    data = _response_dict(response)
    return extract_disk_info(data)


# ---------------------------------------------------------------------------
# Read-only API calls
# ---------------------------------------------------------------------------

def list_clusters(region, limit=DEFAULT_LIMIT, datastore_type=None,
                  max_pages=DEFAULT_MAX_PAGES):
    """Query all CSS clusters (paged); KooCLI first, SDK fallback if missing."""
    items = []
    seen = set()
    offset = 1
    total = None
    for _page in range(max_pages):
        argv = build_list_command(region, limit=limit, offset=offset,
                                  datastore_type=datastore_type)
        try:
            stdout, stderr, returncode = run_hcloud(argv)
        except ConfigError:
            return list_clusters_via_sdk(
                region, limit=limit, datastore_type=datastore_type,
                max_pages=max_pages)
        if returncode != 0 or _USE_ERROR_MARKER in (stdout + " " + stderr).lower():
            raise classify_hcloud_failure(stdout, stderr, returncode)
        payload = extract_json(stdout)
        err_text = _payload_error(payload)
        if err_text:
            raise classify_hcloud_failure("", err_text, returncode)
        batch = extract_clusters(payload)
        total = extract_total(payload)
        added = 0
        for record in batch:
            key = record.get("id") if isinstance(record, dict) else None
            if key is None:
                items.append(record)
                added += 1
                continue
            key = str(key)
            if key in seen:
                continue
            seen.add(key)
            items.append(record)
            added += 1
        if not batch or not added:
            break
        if total is not None and len(items) >= total:
            break
        if len(batch) < limit:
            break
        offset += len(batch)
    else:
        raise ApiError("翻页超过 %d 页仍未取完，已中止以防死循环。" % max_pages)
    return items


def show_cluster(region, cluster_id):
    """Query one cluster's details; KooCLI first, SDK fallback if missing."""
    argv = build_detail_command(region, cluster_id)
    try:
        stdout, stderr, returncode = run_hcloud(argv)
    except ConfigError:
        detail = show_cluster_via_sdk(region, cluster_id)
        if not detail:
            raise _cluster_not_found(cluster_id)
        return detail
    if returncode != 0 or _USE_ERROR_MARKER in (stdout + " " + stderr).lower():
        raise classify_hcloud_failure(stdout, stderr, returncode)
    payload = extract_json(stdout)
    err_text = _payload_error(payload)
    if err_text:
        raise classify_hcloud_failure("", err_text, returncode)
    if not isinstance(payload, dict) or not payload:
        raise _cluster_not_found(cluster_id)
    return payload


def show_volume_usage(region, cluster_id):
    """Query per-node disk usage; KooCLI first, SDK fallback if missing."""
    argv = build_volume_command(region, cluster_id)
    try:
        stdout, stderr, returncode = run_hcloud(argv)
    except ConfigError:
        return show_volume_usage_via_sdk(region, cluster_id)
    if returncode != 0 or _USE_ERROR_MARKER in (stdout + " " + stderr).lower():
        raise classify_hcloud_failure(stdout, stderr, returncode)
    payload = extract_json(stdout)
    err_text = _payload_error(payload)
    if err_text:
        raise classify_hcloud_failure("", err_text, returncode)
    return extract_disk_info(payload)


def _cluster_not_found(cluster_id):
    return ApiError(
        "集群 %s 不存在或当前账号无权访问。请确认集群 ID 正确、Region 与集群所在"
        "区域一致，并检查 IAM 是否授予 css:cluster:get。" % cluster_id
    )


# ---------------------------------------------------------------------------
# Normalisation and filtering
# ---------------------------------------------------------------------------

def _field(record, *names, default=_FIELD_MISSING):
    if not isinstance(record, dict):
        return default
    for name in names:
        if name in record and record[name] not in (None, "", [], {}):
            return record[name]
    return default


def _as_float(value):
    try:
        if value is None or value == "":
            return None
        return float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _status_text(status, meanings):
    text = str(status) if status not in (None, "") else _FIELD_MISSING
    meaning = meanings.get(text)
    return "%s(%s)" % (text, meaning) if meaning else text


def _node_volumes(instances):
    total = 0
    found = False
    for node in instances:
        volume = node.get("volume") if isinstance(node, dict) else None
        size = _as_float(volume.get("size")) if isinstance(volume, dict) else None
        if size is not None:
            total += size
            found = True
    return total if found else None


def normalize_cluster(record, region=None, usage_percent=None):
    """Flatten a raw cluster record into the fields used by the table views."""
    instances = record.get("instances") if isinstance(record, dict) else None
    if not isinstance(instances, list):
        instances = []
    datastore = record.get("datastore") if isinstance(record, dict) else None
    if not isinstance(datastore, dict):
        datastore = {}
    specs = []
    for node in instances:
        spec = _field(node, "specCode", "spec_code", default="")
        if spec and spec not in specs:
            specs.append(str(spec))
    status = str(_field(record, "status", default=""))
    percent = usage_percent
    return {
        "id": _field(record, "id", "clusterId", "cluster_id"),
        "name": _field(record, "name", "clusterName", "cluster_name"),
        "status": status or _FIELD_MISSING,
        "status_meaning": CLUSTER_STATUS_MEANINGS.get(status, ""),
        "datastore_type": _field(datastore, "type", default=_FIELD_MISSING),
        "version": _field(datastore, "version", default=_FIELD_MISSING),
        "node_spec": ",".join(specs) if specs else _FIELD_MISSING,
        "node_count": len(instances),
        "storage_gb": _node_volumes(instances),
        "usage_percent": percent,
        "vpc_id": _field(record, "vpcId", "vpc_id"),
        "subnet_id": _field(record, "subnetId", "subnet_id"),
        "security_group_id": _field(record, "securityGroupId",
                                    "security_group_id"),
        "created": _field(record, "created", "createdAt", "create_time"),
        "region": region or _FIELD_MISSING,
        "abnormal": status != NORMAL_STATUS,
        "capacity_alert": (percent is not None
                           and percent >= CAPACITY_ALERT_PERCENT),
    }


def normalize_node(node, region=None, usage=None):
    """Flatten a raw instance record into the fields used by the node view."""
    usage = usage or {}
    percent = _as_float(_field(usage, "percentage", "usage", default=None))
    status = str(_field(node, "status", default=""))
    return {
        "id": _field(node, "id", "instanceId", "instance_id"),
        "name": _field(node, "name", "instanceName", "instance_name"),
        "type": _field(node, "type", default=_FIELD_MISSING),
        "spec_code": _field(node, "specCode", "spec_code"),
        "status": status or _FIELD_MISSING,
        "status_meaning": NODE_STATUS_MEANINGS.get(status, ""),
        "ip": _field(node, "ip", "ipAddress", "ip_address"),
        "az_code": _field(node, "azCode", "az_code", "available_zone"),
        "usage_percent": percent,
        "disk_capacity": _field(usage, "diskCapacity", "disk_capacity",
                                default=None),
        "disk_used": _field(usage, "diskUsed", "disk_used", default=None),
        "region": region or _FIELD_MISSING,
        "abnormal": status != NORMAL_STATUS,
    }


def _status_tokens(raw):
    if not raw:
        return []
    return [token.strip() for token in str(raw).replace(";", ",").split(",")
            if token.strip()]


def filter_clusters(clusters, name=None, fuzzy=False, status=None):
    """Client-side name / status filtering over raw cluster records."""
    result = list(clusters)
    if name:
        needle = str(name).lower()
        if fuzzy:
            result = [c for c in result
                      if needle in str(_field(c, "name", default="")).lower()]
        else:
            result = [c for c in result
                      if str(_field(c, "name", default="")).lower() == needle]
    tokens = _status_tokens(status)
    if tokens:
        result = [c for c in result if _status_matches(c, tokens)]
    return result


def _status_matches(cluster, tokens):
    status = str(_field(cluster, "status", default=""))
    for token in tokens:
        low = token.lower()
        if low in ("abnormal", "异常"):
            if status != NORMAL_STATUS:
                return True
        elif low in ("normal", "available", "可用", "正常"):
            if status == NORMAL_STATUS:
                return True
        elif low in ("creating", "创建中"):
            if status == "100":
                return True
        elif low in ("failed", "unavailable", "不可用", "失败"):
            if status == "303":
                return True
        elif low == status:
            return True
    return False


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _cell(value):
    if value is None:
        return _FIELD_MISSING
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def render_table(headers, rows):
    """Render aligned plain-text table output."""
    if not rows:
        return ""
    columns = len(headers)
    widths = []
    for index in range(columns):
        widths.append(max([len(headers[index])]
                          + [len(row[index]) for row in rows]))
    lines = [
        "  ".join(headers[i].ljust(widths[i]) for i in range(columns)),
        "  ".join("-" * widths[i] for i in range(columns)),
    ]
    for row in rows:
        lines.append("  ".join(row[i].ljust(widths[i]) for i in range(columns)))
    return "\n".join(lines)


CLUSTER_HEADERS = [
    "集群ID", "名称", "状态", "引擎类型", "版本", "节点规格", "节点数",
    "存储容量(GB)", "磁盘使用率", "VPC", "子网", "安全组", "创建时间", "Region",
]


def _usage_text(percent, alert):
    if percent is None:
        return _FIELD_MISSING
    text = "%.2f%%" % percent
    if alert:
        text += " ⚠≥80%"
    return text


def _cluster_row(cluster):
    status_text = _status_text(cluster.get("status"), CLUSTER_STATUS_MEANINGS)
    marker = "⚠ " if cluster.get("abnormal") else ""
    return [
        _cell(cluster.get("id")),
        marker + _cell(cluster.get("name")),
        status_text,
        _cell(cluster.get("datastore_type")),
        _cell(cluster.get("version")),
        _cell(cluster.get("node_spec")),
        _cell(cluster.get("node_count")),
        _cell(cluster.get("storage_gb")),
        _usage_text(cluster.get("usage_percent"), cluster.get("capacity_alert")),
        _cell(cluster.get("vpc_id")),
        _cell(cluster.get("subnet_id")),
        _cell(cluster.get("security_group_id")),
        _cell(cluster.get("created")),
        _cell(cluster.get("region")),
    ]


def render_cluster_view(region, raw_clusters, with_usage=False, usage_lookup=None):
    """Render the cluster view (normal table + separate abnormal section)."""
    usage_lookup = usage_lookup or {}
    normalized = []
    for record in raw_clusters:
        cluster = normalize_cluster(
            record, region=region,
            usage_percent=usage_lookup.get(str(_field(record, "id", default=""))))
        normalized.append(cluster)
    normals = [c for c in normalized if not c["abnormal"]]
    abnormals = [c for c in normalized if c["abnormal"]]
    capacity = [c for c in normalized if c["capacity_alert"]]

    lines = [
        "Region %s 的 CSS 集群列表（共 %d 个%s）：" % (
            region, len(normalized),
            "，正常 %d / 异常 %d" % (len(normals), len(abnormals))
            if abnormals else "")
    ]
    rows = [_cluster_row(c) for c in normals] or [_cluster_row(c) for c in []]
    if normals:
        lines.append(render_table(CLUSTER_HEADERS, rows))
    elif not abnormals:
        lines.append("（无集群）")
    if abnormals:
        lines.append("")
        lines.append("⚠ 异常状态集群（共 %d 个，已与正常集群分开列出，请优先排查）："
                     % len(abnormals))
        lines.append(render_table(CLUSTER_HEADERS,
                                  [_cluster_row(c) for c in abnormals]))
    if capacity:
        lines.append("")
        lines.append("⚠ 容量使用率 ≥80%% 的集群（共 %d 个，需尽快扩容或清理）："
                     % len(capacity))
        for cluster in capacity:
            lines.append("- %s (%s)  磁盘使用率=%.2f%%"
                         % (cluster["name"], cluster["id"],
                            cluster["usage_percent"]))
    return "\n".join(lines)


NODE_HEADERS = [
    "节点ID", "节点名", "类型", "规格", "状态", "IP", "可用区",
    "磁盘使用率", "容量(GB)", "已用(GB)",
]


def _node_row(node):
    marker = "⚠ " if node.get("abnormal") else ""
    percent = node.get("usage_percent")
    return [
        _cell(node.get("id")),
        marker + _cell(node.get("name")),
        _cell(node.get("type")),
        _cell(node.get("spec_code")),
        _status_text(node.get("status"), NODE_STATUS_MEANINGS),
        _cell(node.get("ip")),
        _cell(node.get("az_code")),
        _usage_text(percent, percent is not None
                    and percent >= CAPACITY_ALERT_PERCENT),
        _cell(node.get("disk_capacity")),
        _cell(node.get("disk_used")),
    ]


def render_node_view(region, detail, disk_infos):
    """Render the per-cluster node view (normal + separate abnormal section)."""
    name = _field(detail, "name", default=_FIELD_MISSING)
    cluster_id = _field(detail, "id", default=_FIELD_MISSING)
    instances = _field(detail, "instances", default=[])
    if not isinstance(instances, list):
        instances = []
    usage_by_id = {}
    usage_by_name = {}
    for info in disk_infos or []:
        if not isinstance(info, dict):
            continue
        key = str(_field(info, "id", default=""))
        if key:
            usage_by_id[key] = info
        node_name = str(_field(info, "name", default=""))
        if node_name:
            usage_by_name[node_name] = info
    nodes = []
    for instance in instances:
        key = str(_field(instance, "id", default=""))
        node_name = str(_field(instance, "name", default=""))
        usage = usage_by_id.get(key) or usage_by_name.get(node_name)
        nodes.append(normalize_node(instance, region=region, usage=usage))
    normals = [n for n in nodes if not n["abnormal"]]
    abnormals = [n for n in nodes if n["abnormal"]]
    lines = [
        "集群 %s (%s) 的节点列表（共 %d 个，Region %s%s）：" % (
            name, cluster_id, len(nodes), region,
            "，异常 %d" % len(abnormals) if abnormals else "")
    ]
    if normals:
        lines.append(render_table(NODE_HEADERS,
                                  [_node_row(n) for n in normals]))
    elif not abnormals:
        lines.append("（该集群未返回节点信息）")
    if abnormals:
        lines.append("")
        lines.append("⚠ 异常节点（共 %d 个，已与正常节点分开列出，请优先排查）："
                     % len(abnormals))
        lines.append(render_table(NODE_HEADERS,
                                  [_node_row(n) for n in abnormals]))
    high_usage = [n for n in nodes
                  if n["usage_percent"] is not None
                  and n["usage_percent"] >= CAPACITY_ALERT_PERCENT]
    if high_usage:
        lines.append("")
        lines.append("⚠ 磁盘使用率 ≥80%% 的节点（共 %d 个）：" % len(high_usage))
        for node in high_usage:
            lines.append("- %s (%s)  磁盘使用率=%.2f%%"
                         % (node["name"], node["id"],
                            node["usage_percent"]))
    return "\n".join(lines)


def render_simple_view(region, raw_clusters, filters=None):
    """Render the default compact cluster list (name / id / status)."""
    filters = filters or {}
    lines = ["Region %s 的 CSS 集群列表（共 %d 个）："
             % (region, len(raw_clusters))]
    for record in raw_clusters:
        status = str(_field(record, "status", default=""))
        marker = "⚠ " if status != NORMAL_STATUS else "  "
        lines.append("%s%s  %s  状态=%s%s" % (
            marker,
            _field(record, "name", default=_FIELD_MISSING),
            _field(record, "id", default=_FIELD_MISSING),
            _status_text(status, CLUSTER_STATUS_MEANINGS),
            " [异常]" if status != NORMAL_STATUS else "",
        ))
    abnormal = [r for r in raw_clusters
                if str(_field(r, "status", default="")) != NORMAL_STATUS]
    if abnormal:
        lines.append("")
        lines.append("⚠ 异常状态集群（共 %d 个，已与正常集群分开列出，请优先排查）："
                     % len(abnormal))
        for record in abnormal:
            lines.append("- %s (%s)  状态=%s" % (
                _field(record, "name", default=_FIELD_MISSING),
                _field(record, "id", default=_FIELD_MISSING),
                _status_text(_field(record, "status", default=""),
                             CLUSTER_STATUS_MEANINGS),
            ))
    if filters:
        detail = ", ".join("%s=%s" % (k, v) for k, v in filters.items() if v)
        if detail:
            lines.append("过滤条件: %s" % detail)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _usage_percent_lookup(region, raw_clusters):
    """Best-effort per-cluster max disk usage; degrades to {} on API errors."""
    lookup = {}
    allowed = True
    for record in raw_clusters:
        cluster_id = str(_field(record, "id", default=""))
        if not cluster_id:
            continue
        if not allowed:
            continue
        try:
            infos = show_volume_usage(region, cluster_id)
        except AuthError:
            allowed = False
            continue
        except CssListError:
            continue
        percents = []
        for info in infos:
            if not isinstance(info, dict):
                continue
            value = _as_float(_field(info, "percentage", "usage", default=None))
            if value is not None:
                percents.append(value)
        if percents:
            lookup[cluster_id] = max(percents)
    return lookup


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="查询华为云 CSS（云搜索服务）集群列表与节点容量（只读）。")
    parser.add_argument("-r", "--region", default=DEFAULT_REGION,
                        help="目标 Region（默认 %s）" % DEFAULT_REGION)
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="以 JSON 输出原始响应")
    parser.add_argument("--table", action="store_true", dest="as_table",
                        help="输出完整字段集群视图（配合 --cluster-id 输出节点视图）")
    parser.add_argument("--name", help="按集群名称过滤（默认精确匹配）")
    parser.add_argument("--fuzzy", action="store_true", dest="fuzzy",
                        help="--name 使用模糊（子串）匹配")
    parser.add_argument("--cluster-id", dest="cluster_id",
                        help="下钻指定集群：输出集群详情与节点列表")
    parser.add_argument("--status",
                        help="按集群状态过滤（200/100/303、abnormal、normal 等，"
                             "客户端过滤）")
    parser.add_argument("--datastore-type", dest="datastore_type",
                        help="按引擎类型过滤（elasticsearch / opensearch）")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help="分页大小，取值 1~%d（默认 %d，自动分页取全量）"
                             % (MAX_LIMIT, DEFAULT_LIMIT))
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        dest="max_pages", help="最大翻页数（防死循环，默认 %d）"
                             % DEFAULT_MAX_PAGES)
    parser.add_argument("--action", default=None,
                        help="显式操作意图（仅允许只读 list/detail/volume；"
                             "写意图会被守卫拦截）")
    return parser.parse_args(argv)


def _filters_from_args(args):
    return {
        "name": args.name,
        "fuzzy": args.fuzzy,
        "status": args.status,
        "datastore_type": args.datastore_type,
    }


def main(argv=None):
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parse_args(raw_argv)

    try:
        guard_write_intent(scannable_argv(raw_argv))
        guard_action(args.action)
        limit, clamped = clamp_limit(args.limit)
        if clamped:
            print("[提示] --limit 超出 1~%d，已自动调整为 %d。"
                  % (MAX_LIMIT, limit), file=sys.stderr)

        if args.cluster_id:
            guard_operation(DETAIL_OPERATION)
            detail = show_cluster(args.region, args.cluster_id)
            try:
                disk_infos = show_volume_usage(args.region, args.cluster_id)
            except CssListError as exc:
                disk_infos = []
                print("[提示] 未能获取节点磁盘使用率：%s" % exc, file=sys.stderr)
            if args.as_json:
                print(json.dumps({"cluster": detail,
                                  "volumeUsage": disk_infos},
                                 ensure_ascii=False, indent=2))
            else:
                print(render_node_view(args.region, detail, disk_infos))
            return 0

        guard_operation(LIST_OPERATION)
        clusters = list_clusters(
            args.region, limit=limit, datastore_type=args.datastore_type,
            max_pages=max(1, args.max_pages))
        clusters = filter_clusters(
            clusters, name=args.name, fuzzy=args.fuzzy, status=args.status)

        if args.as_json:
            print(json.dumps(clusters, ensure_ascii=False, indent=2))
            return 0

        if not clusters:
            detail = []
            if args.name:
                detail.append("name=%s%s" % (args.name,
                                             "(fuzzy)" if args.fuzzy else ""))
            if args.status:
                detail.append("status=%s" % args.status)
            if args.datastore_type:
                detail.append("datastoreType=%s" % args.datastore_type)
            print("Region %s 下暂无 CSS 集群%s。" % (
                args.region,
                "（过滤条件: %s）" % ", ".join(detail) if detail else ""))
            return 0

        if args.as_table:
            usage_lookup = _usage_percent_lookup(args.region, clusters)
            print(render_cluster_view(args.region, clusters,
                                      with_usage=True,
                                      usage_lookup=usage_lookup))
        else:
            filters = {}
            if args.name:
                filters["name"] = args.name + ("(fuzzy)" if args.fuzzy else "")
            if args.status:
                filters["status"] = args.status
            if args.datastore_type:
                filters["datastoreType"] = args.datastore_type
            print(render_simple_view(args.region, clusters, filters=filters))
        return 0
    except CssListError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())