#!/usr/bin/env python3
"""List Huawei Cloud CCE (Cloud Container Engine) clusters via KooCLI `hcloud CCE ListClusters`.

Primary execution path is KooCLI (`hcloud CCE ListClusters`, read-only GET
/api/v3/projects/{project_id}/clusters); when hcloud is not installed the script
falls back to the official `huaweicloudsdkcce` v3 SDK
(`CceClient.list_clusters`). Reads nothing but the active credential profile /
environment. Supports three output modes (table / --json / --names-only),
client-side --name / --id filtering (the v3 ListClusters API has no name/id query
parameters), and a strict write-intent guard: any argument that looks like a
mutating CCE operation is rejected before a single command is executed.

Usage:
    python3 scripts/list_cce.py [--region cn-north-4] [--json | --names-only]
                                [--name demo] [--id <cluster-uid>]
                                [--project-id <pid>] [--operation ListClusters]

Environment overrides (mostly for tests):
    CCE_LIST_HCLOUD_BIN   hcloud executable (default "hcloud")
    CCE_LIST_HCLOUD_ARGS  extra args injected before the CCE operation
"""

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_REGION = "cn-north-4"
SERVICE = "CCE"
ALLOWED_OPERATION = "ListClusters"

# Mutating CCE operations / intents — strictly rejected by the guard.
WRITE_INTENT_KEYWORDS = (
    "createcluster",
    "deletecluster",
    "updatecluster",
    "upgradecluster",
    "hibernatecluster",
    "wakeupcluster",
    "resizecluster",
    "rollbackcluster",
    "createaddon",
    "deleteaddon",
    "updateaddon",
    "createnode",
    "deletenode",
    "resizenode",
    "addnode",
    "removenode",
    "createpartition",
    "deletepartition",
    "creating",
    "deleting",
    "updating",
    "upgrading",
    "hibernating",
    "resizing",
    "create",
    "delete",
    "update",
    "modify",
    "upgrade",
    "resize",
    "hibernate",
    "wakeup",
    "rollback",
    "scale",
    "associate",
    "disassociate",
    "dissociate",
    "attach",
    "detach",
    "restart",
    "reboot",
    "reset",
    "stop",
    "start",
    "destroy",
    "remove",
    "add",
    "install",
    "uninstall",
    "enable",
    "disable",
    "migrate",
    "bind",
    "unbind",
)

# Preferred column order for the table view; remaining keys are appended sorted.
PREFERRED_COLUMNS = [
    "name",
    "id",
    "alias",
    "status",
    "type",
    "flavor",
    "version",
    "category",
    "billing_mode",
    "description",
    "created_at",
    "labels",
]

_CLUSTER_LIST_KEYS = ("items", "clusters", "cluster_list")

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
    "认证失败",
    "权限不足",
    "permission denied",
)

# KooCLI prints usage errors (e.g. "[USE_ERROR]Invalid parameter: xxx") on
# stdout WITH exit code 0 — the marker must be treated as a hard failure even
# when the return code looks successful.
_USE_ERROR_MARKER = "[use_error]"


class CceListError(Exception):
    """Base error for the CCE list skill."""


class GuardError(CceListError):
    """A write intent was detected and blocked (skill is read-only)."""


class ConfigError(CceListError):
    """hcloud missing or credentials (AK/SK) not configured."""


class AuthError(CceListError):
    """Authentication/authorization failure (invalid AK/SK or IAM 403)."""


class ApiError(CceListError):
    """hcloud / network / unexpected API failure."""


def guard_write_intent(text):
    """Raise GuardError if `text` carries a mutating intent.

    Normalizes separators so `--create-cluster`, `CreateCluster`, and
    `create_cluster` all hit the same keyword. Read-only vocabulary
    (list/show/get/describe) never matches.
    """
    low = re.sub(r"[\s_\-]+", "", str(text).lower())
    for keyword in WRITE_INTENT_KEYWORDS:
        if keyword in low:
            raise GuardError(
                "检测到写操作意图（关键词: %s）。本 skill 仅支持只读查询"
                "（CCE ListClusters），创建/删除/更新/扩缩容等变更操作已被守卫拦截。" % keyword
            )
    return False


def guard_operation(operation):
    """Only the read-only ListClusters operation may be executed."""
    if operation != ALLOWED_OPERATION:
        raise GuardError(
            "不允许的操作 %r：本 skill 仅允许只读操作 %s。"
            % (operation, ALLOWED_OPERATION)
        )
    return True


def build_command(region):
    """Build the hcloud CCE ListClusters argv (without the executable).

    The v3 ListClusters API (GET /api/v3/projects/{project_id}/clusters)
    exposes no name/id query parameters and no paging parameters — it returns
    the full cluster list for the project in one response. Only --cli-region is
    required; the project_id path parameter is resolved by KooCLI from the
    credential profile.
    """
    return [
        SERVICE,
        ALLOWED_OPERATION,
        "--cli-region=%s" % region,
    ]


def _hcloud_executable():
    return os.environ.get("CCE_LIST_HCLOUD_BIN", "hcloud")


def run_hcloud(argv):
    """Execute hcloud and return (stdout, stderr, returncode)."""
    cmd = [_hcloud_executable()]
    extra = os.environ.get("CCE_LIST_HCLOUD_ARGS", "").split()
    if extra:
        cmd.extend(extra)
    cmd.extend(argv)
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=120, universal_newlines=True,
        )
    except FileNotFoundError:
        raise ConfigError(
            "未找到 hcloud（KooCLI）。请先安装 KooCLI 并完成认证配置，"
            "参见 references/cli-installation-guide.md。"
        )
    except subprocess.TimeoutExpired:
        raise ApiError("hcloud 执行超时（120s），请检查网络后重试。")
    return proc.stdout or "", proc.stderr or "", proc.returncode


def extract_json(stdout):
    """Parse hcloud stdout as JSON; tolerate wrapper/noise lines."""
    text = stdout.strip()
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


def classify_hcloud_failure(stdout, stderr, returncode):
    """Map a failed hcloud invocation to a domain error with explicit hints."""
    blob = (stderr + " " + stdout).strip()
    low = blob.lower()
    if _USE_ERROR_MARKER in low:
        return ApiError(
            "hcloud 参数错误（KooCLI 拒绝了该参数组合，退出码 %s）：CCE ListClusters "
            "真实参数清单可通过 `hcloud CCE ListClusters --help` 查看。"
            "详情：%s" % (returncode, blob[:300])
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
            "无权限访问云容器引擎（CCE），请检查 IAM 权限（403：AK/SK 无效或未授予 CCE 只读权限），"
            "参见 references/iam-policies.md。详情：%s" % blob[:300]
        )
    return ApiError(
        "hcloud 调用失败（退出码 %s）：%s" % (returncode, blob[:300])
    )


def extract_clusters(payload):
    """Pull the cluster list out of a ListClusters response.

    The v3 ListClusters response is a Kubernetes-style list:
    {"kind": "List", "apiVersion": "v3", "items": [...]}.
    """
    if isinstance(payload, list):
        return payload
    for key in _CLUSTER_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _jsonable(value):
    """Recursively convert datetimes (SDK to_dict output) to JSON-safe values."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _env_credential(markers):
    for key, value in os.environ.items():
        upper = key.upper()
        if not upper.startswith(("HUAWEI", "HW_", "HWC")):
            continue
        if any(marker in upper for marker in markers) and value:
            return value
    return None


def _env_project_id():
    for key, value in os.environ.items():
        upper = key.upper()
        if upper.startswith(("HUAWEI", "HW_", "HWC")) and "PROJECT_ID" in upper and value:
            return value
    return None


def list_clusters_via_sdk(region, project_id=None):
    """SDK fallback: query CCE clusters through `huaweicloudsdkcce` v3.

    Only invoked when hcloud is not installed. Credentials are taken from the
    standard environment variables (HUAWEI_*/HW_*/HWC_* AK/SK markers) — never
    passed as literals here. The official SDK has no env-var auto-discovery on
    `BasicCredentials()`, so AK/SK must be read explicitly. The v3 ListClusters
    path (`/api/v3/projects/{project_id}/clusters`) needs a project id, which is
    taken from an explicit `--project-id` / HUAWEI_PROJECT_ID if present;
    otherwise the SDK resolves it from the credentials via IAM.
    """
    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkcore.http.http_config import HttpConfig
        from huaweicloudsdkcce.v3 import CceClient, ListClustersRequest
        from huaweicloudsdkcce.v3.region.cce_region import CceRegion
    except ImportError as exc:
        raise ConfigError(
            "未找到 hcloud（KooCLI），且 huaweicloudsdkcore/huaweicloudsdkcce 未安装，"
            "无法回退到 SDK。请安装 KooCLI 或 pip install huaweicloudsdkcore "
            "huaweicloudsdkcce。详情：%s" % exc
        )

    ak = _env_credential(("ACCESS_KEY", "_AK"))
    sk = _env_credential(("SECRET_KEY", "_SK"))
    if not ak or not sk:
        raise ConfigError(
            "SDK 回退缺少 AK/SK 凭证：官方 SDK 的 BasicCredentials 不会自动读取环境"
            "变量，且当前环境未检测到 HUAWEI_*/HW_*/HWC_* 形式的 AK/SK 环境变量。"
            "请在会话外设置 HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY（严禁在对话中粘贴"
            " AK/SK），参见 references/cli-installation-guide.md。"
        )
    pid = project_id or _env_project_id()
    credentials = BasicCredentials(ak=ak, sk=sk, project_id=pid)  # env-sourced, never literals
    try:
        try:
            region_obj = CceRegion.value_of(region)
        except (ValueError, KeyError, AttributeError):
            region_obj = Region(region, "https://cce.%s.myhuaweicloud.com" % region)
        client = CceClient.new_builder() \
            .with_credentials(credentials) \
            .with_region(region_obj) \
            .with_http_config(HttpConfig.get_default_config()) \
            .build()
    except Exception as exc:  # region unknown / config broken
        raise ConfigError(
            "SDK 初始化失败（region=%s）：%s。请检查 huaweicloudsdkcce 安装与区域配置。"
            % (region, exc)
        )
    request = ListClustersRequest()
    try:
        response = client.list_clusters(request)
    except Exception as exc:
        low = str(exc).lower()
        if any(p in low for p in _AUTH_PATTERNS):
            raise AuthError(
                "无权限访问云容器引擎（CCE），请检查 IAM 权限（403）。详情：%s" % str(exc)[:300]
            )
        raise ApiError("SDK 调用失败：%s" % str(exc)[:300])
    batch = list(getattr(response, "items", None) or [])
    return [_jsonable(cluster.to_dict()) for cluster in batch]


def list_clusters(region, name=None, cluster_id=None, project_id=None):
    """Query all CCE clusters; KooCLI first, SDK fallback."""
    argv = build_command(region)
    try:
        stdout, stderr, returncode = run_hcloud(argv)
    except ConfigError:
        # hcloud binary missing → one-shot SDK fallback (no CLI retry).
        return list_clusters_via_sdk(region, project_id=project_id)
    if returncode != 0 or _USE_ERROR_MARKER in (stdout + " " + stderr).lower():
        # KooCLI usage errors print [USE_ERROR] on stdout with rc=0.
        raise classify_hcloud_failure(stdout, stderr, returncode)
    payload = extract_json(stdout)
    return extract_clusters(payload)


def _metadata(cluster):
    metadata = cluster.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _spec(cluster):
    spec = cluster.get("spec")
    return spec if isinstance(spec, dict) else {}


def _status(cluster):
    status = cluster.get("status")
    return status if isinstance(status, dict) else {}


def _flatten_kv(value):
    if isinstance(value, dict):
        pairs = ["%s=%s" % (k, v) for k, v in value.items()]
        return ",".join(pairs) if pairs else "-"
    if isinstance(value, list):
        pairs = []
        for item in value:
            if isinstance(item, dict):
                key = item.get("key", "")
                val = item.get("value", "")
                pairs.append("%s=%s" % (key, val))
            else:
                pairs.append(str(item))
        return ",".join(pairs) if pairs else "-"
    if value in (None, ""):
        return "-"
    return value


def normalize_cluster(cluster):
    """Flatten a Kubernetes-style cluster object into a table-friendly row."""
    metadata = _metadata(cluster)
    spec = _spec(cluster)
    status = _status(cluster)
    flat = {
        "name": metadata.get("name") or "-",
        "id": metadata.get("uid") or "-",
        "alias": metadata.get("alias") or "-",
        "status": status.get("phase") or "-",
        "type": spec.get("type") or "-",
        "flavor": spec.get("flavor") or "-",
        "version": spec.get("version") or "-",
        "category": spec.get("category") or "-",
        "billing_mode": spec.get("billing_mode") if spec.get("billing_mode") is not None else "-",
        "description": spec.get("description") or "-",
        "created_at": metadata.get("creation_timestamp") or "-",
        "labels": _flatten_kv(metadata.get("labels")),
    }
    return flat


def _cell(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _field(row, *names, default="-"):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


def render_table(clusters):
    """Render full-field table output (union of all flattened fields)."""
    rows_data = [normalize_cluster(cluster) for cluster in clusters]
    columns = []
    for key in PREFERRED_COLUMNS:
        if any(key in c for c in rows_data):
            columns.append(key)
    for key in sorted({k for c in rows_data for k in c}):
        if key not in columns:
            columns.append(key)
    if not columns:
        columns = ["name", "id"]
    rows = [[_cell(_field(c, col)) for col in columns] for c in rows_data]
    widths = [max(len(col), *(len(row[i]) for row in rows)) for i, col in enumerate(columns)]
    header = "  ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
    separator = "  ".join("-" * w for w in widths)
    lines = [header, separator]
    for row in rows:
        lines.append("  ".join(row[i].ljust(widths[i]) for i in range(len(columns))))
    return "\n".join(lines)


def cluster_names(clusters):
    names = []
    for cluster in clusters:
        metadata = _metadata(cluster)
        name = metadata.get("name") or metadata.get("alias") or metadata.get("uid")
        names.append(str(name if name else "-"))
    return names


def filter_clusters(clusters, name=None, cluster_id=None):
    """Apply client-side name / id filters.

    The v3 ListClusters API exposes no name/id query parameters, so filtering is
    done locally: name is a case-insensitive substring match, id is a
    case-insensitive exact match against metadata.uid.
    """
    result = clusters
    if name:
        needle = name.lower()
        result = [c for c in result
                  if needle in str(_metadata(c).get("name", "")).lower()]
    if cluster_id:
        needle = cluster_id.lower()
        result = [c for c in result
                  if str(_metadata(c).get("uid", "")).lower() == needle]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="查询华为云云容器引擎（CCE）集群列表（KooCLI hcloud CCE ListClusters，只读）。")
    parser.add_argument("-r", "--region", default=DEFAULT_REGION,
                        help="目标 Region（默认 %s）" % DEFAULT_REGION)
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="以 JSON 输出完整原始字段")
    parser.add_argument("--names-only", action="store_true", dest="names_only",
                        help="仅输出集群名称清单")
    parser.add_argument("--name", help="按集群名称过滤（客户端子串匹配，大小写不敏感）")
    parser.add_argument("--id", dest="cluster_id",
                        help="按集群 UID 过滤（客户端精确匹配，大小写不敏感）")
    parser.add_argument("--project-id", dest="project_id",
                        help="项目 ID（仅 SDK 回退且 AK/SK 无 IAM 读取权限时需要）")
    parser.add_argument("--operation", default=ALLOWED_OPERATION,
                        help="hcloud CCE 操作名（仅允许只读 %s）" % ALLOWED_OPERATION)
    args = parser.parse_args(argv)

    try:
        # Write-intent guard: scan the raw argv + validate the operation name.
        guard_write_intent(" ".join(argv if argv is not None else sys.argv[1:]))
        guard_operation(args.operation)
        if args.name:
            guard_write_intent(args.name)
        if args.cluster_id:
            guard_write_intent(args.cluster_id)
        clusters = list_clusters(
            args.region,
            name=args.name,
            cluster_id=args.cluster_id,
            project_id=args.project_id,
        )
        clusters = filter_clusters(clusters, name=args.name, cluster_id=args.cluster_id)
    except CceListError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(clusters, ensure_ascii=False, indent=2))
        return 0

    if args.names_only:
        print("Region %s 的云容器引擎（CCE）集群名称列表（共 %d 个）：" % (args.region, len(clusters)))
        for name in cluster_names(clusters):
            print("- %s" % name)
        return 0

    if not clusters:
        filters = []
        if args.name:
            filters.append("name=%s" % args.name)
        if args.cluster_id:
            filters.append("id=%s" % args.cluster_id)
        suffix = "（过滤条件: %s）" % ", ".join(filters) if filters else ""
        print("当前区域（%s）无云容器引擎（CCE）集群%s。" % (args.region, suffix))
        return 0

    print("Region %s 的云容器引擎（CCE）集群列表（共 %d 个，完整字段）：" % (args.region, len(clusters)))
    print(render_table(clusters))
    return 0


if __name__ == "__main__":
    sys.exit(main())