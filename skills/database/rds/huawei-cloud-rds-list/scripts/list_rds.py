#!/usr/bin/env python3
"""List Huawei Cloud RDS instances via KooCLI `hcloud RDS ListInstances` (read-only GET).

Primary execution path is KooCLI; when hcloud is not installed, the script falls
back to the official `huaweicloudsdkrds` v3 SDK (`list_instances`). Reads nothing
but the active credential profile / environment. Supports three output modes
(table / --json / --names-only), --status / --name / --datastore-type filters
(--name / --datastore-type are server-side API filters; --status is applied
client-side because the real RDS ListInstances API has no status parameter),
offset paging, and a strict write-intent guard: any argument that looks like a
mutating RDS operation is rejected before a single command is executed.

Usage:
    python3 scripts/list_rds.py [--region cn-north-4] [--json | --names-only]
                                 [--status ACTIVE] [--name rds-01]
                                 [--datastore-type MySQL] [--page-size 100]
                                 [--operation ListInstances]

Environment overrides (mostly for tests):
    RDS_LIST_HCLOUD_BIN   hcloud executable (default "hcloud")
    RDS_LIST_HCLOUD_ARGS  extra args injected before the RDS operation
"""

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_REGION = "cn-north-4"
DEFAULT_PAGE_SIZE = 100
SERVICE = "RDS"
ALLOWED_OPERATION = "ListInstances"

# Mutating RDS operations / intents — strictly rejected by the guard.
WRITE_INTENT_KEYWORDS = (
    "createinstance",
    "deleteinstance",
    "updateinstance",
    "modifyinstance",
    "resizeflavor",
    "resize",
    "restartinstance",
    "stopinstance",
    "startinstance",
    "shutdowninstance",
    "changeflavor",
    "changepassword",
    "setbackuppolicy",
    "updatebackuppolicy",
    "createreadreplica",
    "deletereadreplica",
    "creating",
    "deleting",
    "updating",
    "resizing",
    "restoring",
    "create",
    "delete",
    "update",
    "modify",
    "restart",
    "stop",
    "start",
    "shutdown",
    "restore",
    "destroy",
)

# Preferred column order for the table view; remaining keys are appended sorted.
PREFERRED_COLUMNS = [
    "name",
    "id",
    "status",
    "engine",
    "engineVersion",
    "flavor_ref",
    "flavorRef",
    "privateIps",
    "availability_zone",
    "vpc_id",
    "subnet_id",
    "security_group_id",
    "type",
    "created",
    "updated",
    "enterprise_project_id",
    "tags",
    "charge_mode",
]

_INSTANCE_LIST_KEYS = ("instances", "instance_list", "instanceInfos")

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


class RdsListError(Exception):
    """Base error for the RDS list skill."""


class GuardError(RdsListError):
    """A write intent was detected and blocked (skill is read-only)."""


class ConfigError(RdsListError):
    """hcloud missing or credentials (AK/SK) not configured."""


class AuthError(RdsListError):
    """Authentication/authorization failure (invalid AK/SK or IAM 403)."""


class ApiError(RdsListError):
    """hcloud / network / unexpected API failure."""


def guard_write_intent(text):
    """Raise GuardError if `text` carries a mutating intent.

    Normalizes separators so `--create-instance`, `CreateInstance`, and
    `create_instance` all hit the same keyword. Read-only vocabulary
    (list/show/get/describe) never matches.
    """
    low = re.sub(r"[\s_\-]+", "", str(text).lower())
    for keyword in WRITE_INTENT_KEYWORDS:
        if keyword in low:
            raise GuardError(
                "检测到写操作意图（关键词: %s）。本 skill 仅支持只读查询"
                "（RDS ListInstances），创建/删除/扩缩容/重启等变更操作已被守卫拦截。" % keyword
            )
    return False


def guard_operation(operation):
    """Only the read-only ListInstances operation may be executed."""
    if operation != ALLOWED_OPERATION:
        raise GuardError(
            "不允许的操作 %r：本 skill 仅允许只读操作 %s。" % (operation, ALLOWED_OPERATION)
        )
    return True


def build_command(region, name=None, datastore_type=None,
                  instance_id=None, limit=DEFAULT_PAGE_SIZE, offset=0):
    """Build the hcloud RDS ListInstances argv (without the executable).

    Mirrors the real KooCLI parameter list (`hcloud RDS ListInstances --help`):
    --cli-region / --limit / --offset / --name / --datastore_type / --id.
    There is NO --status parameter on the server side — status filtering is
    applied client-side by `filter_by_status()` after the full list is fetched.
    """
    argv = [
        SERVICE,
        ALLOWED_OPERATION,
        "--cli-region=%s" % region,
        "--limit=%d" % limit,
        "--offset=%d" % offset,
    ]
    if name:
        argv.append("--name=%s" % name)
    if datastore_type:
        argv.append("--datastore_type=%s" % datastore_type)
    if instance_id:
        argv.append("--id=%s" % instance_id)
    return argv


def _hcloud_executable():
    return os.environ.get("RDS_LIST_HCLOUD_BIN", "hcloud")


def run_hcloud(argv):
    """Execute hcloud and return (stdout, stderr, returncode)."""
    cmd = [_hcloud_executable()]
    extra = os.environ.get("RDS_LIST_HCLOUD_ARGS", "").split()
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
            "hcloud 参数错误（KooCLI 拒绝了该参数组合，退出码 %s）：RDS ListInstances "
            "真实参数清单可通过 `hcloud RDS ListInstances --help` 查看。"
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
            "无权限访问 RDS，请检查 IAM 权限（403：AK/SK 无效或未授予 RDS 只读权限），"
            "参见 references/iam-policies.md。详情：%s" % blob[:300]
        )
    return ApiError(
        "hcloud 调用失败（退出码 %s）：%s" % (returncode, blob[:300])
    )


def extract_instances(payload):
    """Pull the instance list out of a ListInstances response."""
    if isinstance(payload, list):
        return payload
    for key in _INSTANCE_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _has_more(batch, collected, limit, payload):
    if not batch:
        return False
    total = None
    if isinstance(payload, dict):
        for key in ("total_count", "totalCount", "total"):
            if isinstance(payload.get(key), int):
                total = payload[key]
                break
    if total is not None and total >= 0:
        return collected < total
    return len(batch) >= limit


def filter_by_status(instances, status):
    """Client-side status filter (case-insensitive).

    The real RDS ListInstances API / KooCLI has no `status` parameter, so
    filtering by instance state happens here, after the full (paged) list has
    been fetched. An empty result is reported as a normal empty list.
    """
    if not status:
        return list(instances)
    wanted = str(status).strip().lower()
    matched = []
    for instance in instances:
        value = instance.get("status") if isinstance(instance, dict) else None
        if value is not None and str(value).strip().lower() == wanted:
            matched.append(instance)
    return matched


def list_instances_via_sdk(region, name=None,
                           datastore_type=None, instance_id=None,
                           limit=DEFAULT_PAGE_SIZE, max_pages=100):
    """SDK fallback: query instances through `huaweicloudsdkrds` v3.

    Only invoked when hcloud is not installed. Credentials are taken from the
    standard environment variables (HUAWEI_*/HW_*/HWC_* AK/SK markers) — never
    passed as literals here. The official SDK has no env-var auto-discovery on
    `BasicCredentials()`, so AK/SK must be read explicitly. Region resolution
    uses the SDK's own `RdsRegion` catalog (official endpoints, no guessing),
    falling back to an explicit `Region(id, endpoint)` for custom regions.
    `ListInstancesRequest` has no `status` attribute (verified against the
    installed SDK: TypeError on `status=`), so status filtering is NOT done
    here — the caller applies `filter_by_status()` on the returned list.
    """
    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkcore.http.http_config import HttpConfig
        from huaweicloudsdkrds.v3 import RdsClient, ListInstancesRequest
        from huaweicloudsdkrds.v3.region.rds_region import RdsRegion
    except ImportError as exc:
        raise ConfigError(
            "未找到 hcloud（KooCLI），且 huaweicloudsdkcore/huaweicloudsdkrds 未安装，"
            "无法回退到 SDK。请安装 KooCLI 或 pip install huaweicloudsdkcore "
            "huaweicloudsdkrds。详情：%s" % exc
        )

    def _env_credential(markers):
        for key, value in os.environ.items():
            upper = key.upper()
            if not upper.startswith(("HUAWEI", "HW_", "HWC")):
                continue
            if any(marker in upper for marker in markers) and value:
                return value
        return None

    ak = _env_credential(("ACCESS_KEY", "_AK"))
    sk = _env_credential(("SECRET_KEY", "_SK"))
    if not ak or not sk:
        raise ConfigError(
            "SDK 回退缺少 AK/SK 凭证：官方 SDK 的 BasicCredentials 不会自动读取环境"
            "变量，且当前环境未检测到 HUAWEI_*/HW_*/HWC_* 形式的 AK/SK 环境变量。"
            "请在会话外设置 HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY（严禁在对话中粘贴"
            " AK/SK），参见 references/cli-installation-guide.md。"
        )
    credentials = BasicCredentials(ak=ak, sk=sk)  # env-sourced, never literals
    try:
        try:
            region_obj = RdsRegion.value_of(region)
        except (ValueError, KeyError, AttributeError):
            region_obj = Region(region, "https://rds.%s.myhuaweicloud.com" % region)
        client = RdsClient.new_builder() \
            .with_credentials(credentials) \
            .with_region(region_obj) \
            .with_http_config(HttpConfig.get_default_config()) \
            .build()
    except Exception as exc:  # region unknown / config broken
        raise ConfigError(
            "SDK 初始化失败（region=%s）：%s。请检查 huaweicloudsdkrds 安装与区域配置。"
            % (region, exc)
        )
    instances = []
    offset = 0
    for _ in range(max_pages):
        request = ListInstancesRequest(
            limit=limit, offset=offset,
            id=instance_id, name=name,
            datastore_type=datastore_type,
        )
        try:
            response = client.list_instances(request)
        except Exception as exc:
            low = str(exc).lower()
            if any(p in low for p in _AUTH_PATTERNS):
                raise AuthError(
                    "无权限访问 RDS，请检查 IAM 权限（403）。详情：%s" % str(exc)[:300]
                )
            raise ApiError("SDK 调用失败：%s" % str(exc)[:300])
        batch = list(response.instances or [])
        instances.extend(instance.to_dict() for instance in batch)
        total = getattr(response, "total_count", None)
        if total is not None and len(instances) >= total:
            break
        if len(batch) < limit:
            break
        offset += len(batch)
    else:
        raise ApiError("翻页超过 %d 页仍未取完，已中止以防死循环。" % max_pages)
    return instances


def list_instances(region, status=None, name=None, datastore_type=None,
                   instance_id=None, limit=DEFAULT_PAGE_SIZE, max_pages=100):
    """Query all RDS instances (paged); KooCLI first, SDK fallback.

    `status` is intentionally NOT forwarded to hcloud or the SDK — the real
    RDS ListInstances API has no status parameter. Instead the full list is
    fetched first, then `filter_by_status()` is applied client-side.
    """
    instances = []
    offset = 0
    for _page in range(max_pages):
        argv = build_command(region, name=name,
                             datastore_type=datastore_type,
                             instance_id=instance_id,
                             limit=limit, offset=offset)
        try:
            stdout, stderr, returncode = run_hcloud(argv)
        except ConfigError:
            # hcloud binary missing → one-shot SDK fallback (no CLI retry).
            instances = list_instances_via_sdk(
                region, name=name,
                datastore_type=datastore_type, instance_id=instance_id,
                limit=limit, max_pages=max_pages,
            )
            break
        if returncode != 0 or _USE_ERROR_MARKER in (stdout + " " + stderr).lower():
            # KooCLI usage errors print [USE_ERROR] on stdout with rc=0.
            raise classify_hcloud_failure(stdout, stderr, returncode)
        payload = extract_json(stdout)
        batch = extract_instances(payload)
        instances.extend(batch)
        if not _has_more(batch, len(instances), limit, payload):
            break
        offset += len(batch) if batch else limit
    else:
        raise ApiError("翻页超过 %d 页仍未取完，已中止以防死循环。" % max_pages)
    return filter_by_status(instances, status)


def normalize_instance(instance):
    """Flatten nested datastore / ip list fields into table-friendly keys."""
    flat = dict(instance)
    datastore = instance.get("datastore") or {}
    if isinstance(datastore, dict):
        flat.setdefault("engine", datastore.get("type", "-"))
        flat.setdefault("engineVersion", datastore.get("version", "-"))
    else:
        flat.setdefault("engine", "-")
        flat.setdefault("engineVersion", "-")
    private_ips = instance.get("private_ips") or instance.get("ips")
    if isinstance(private_ips, list):
        flat["privateIps"] = ",".join(str(ip) for ip in private_ips) if private_ips else "-"
    elif isinstance(private_ips, str):
        flat["privateIps"] = private_ips
    else:
        flat["privateIps"] = "-"
    nodes = instance.get("nodes") or []
    if isinstance(nodes, list) and nodes and "availability_zone" not in flat:
        az = nodes[0].get("availability_zone") if isinstance(nodes[0], dict) else None
        if az:
            flat["availability_zone"] = az
    return flat


def _field(instance, *names, default="-"):
    for name in names:
        if name in instance and instance[name] not in (None, ""):
            return instance[name]
    return default


def instance_names(instances):
    names = []
    for instance in instances:
        name = _field(instance, "name", "instance_name", default=None)
        if name is None:
            name = _field(instance, "id", "instance_id")
        names.append(str(name))
    return names


def _cell(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def render_table(instances):
    """Render full-field table output (union of all returned fields)."""
    rows_data = [normalize_instance(instance) for instance in instances]
    columns = []
    for key in PREFERRED_COLUMNS:
        if any(key in i for i in rows_data):
            columns.append(key)
    for key in sorted({k for i in rows_data for k in i}):
        if key not in columns:
            columns.append(key)
    if not columns:
        columns = ["name", "id"]
    rows = [[_cell(_field(i, col)) for col in columns] for i in rows_data]
    widths = [max(len(col), *(len(row[i]) for row in rows)) for i, col in enumerate(columns)]
    header = "  ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
    separator = "  ".join("-" * w for w in widths)
    lines = [header, separator]
    for row in rows:
        lines.append("  ".join(row[i].ljust(widths[i]) for i in range(len(columns))))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="查询华为云 RDS 实例列表（KooCLI hcloud RDS ListInstances，只读）。")
    parser.add_argument("-r", "--region", default=DEFAULT_REGION,
                        help="目标 Region（默认 %s）" % DEFAULT_REGION)
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="以 JSON 输出完整原始字段")
    parser.add_argument("--names-only", action="store_true", dest="names_only",
                        help="仅输出实例名称清单")
    parser.add_argument("--status",
                        help="按实例状态过滤（ACTIVE/FAILED/BUILDING 等；"
                             "RDS ListInstances API 无此参数，全量取回后本地过滤）")
    parser.add_argument("--name", help="按实例名称过滤")
    parser.add_argument("--datastore-type", dest="datastore_type",
                        help="按数据库引擎过滤（MySQL/PostgreSQL/SQLServer）")
    parser.add_argument("--instance-id", dest="instance_id",
                        help="按实例 ID 过滤（精确查询）")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE,
                        dest="page_size", help="分页大小（默认 %d）" % DEFAULT_PAGE_SIZE)
    parser.add_argument("--operation", default=ALLOWED_OPERATION,
                        help="hcloud RDS 操作名（仅允许只读 %s）" % ALLOWED_OPERATION)
    args = parser.parse_args(argv)

    try:
        # Write-intent guard: scan the raw argv + validate the operation name.
        guard_write_intent(" ".join(argv if argv is not None else sys.argv[1:]))
        guard_operation(args.operation)
        if args.status:
            guard_write_intent(args.status)
        if args.name:
            guard_write_intent(args.name)
        instances = list_instances(
            args.region,
            status=args.status,
            name=args.name,
            datastore_type=args.datastore_type,
            instance_id=args.instance_id,
            limit=args.page_size,
        )
    except RdsListError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(instances, ensure_ascii=False, indent=2))
        return 0

    if args.names_only:
        print("Region %s 的 RDS 实例名称列表（共 %d 个）：" % (args.region, len(instances)))
        for name in instance_names(instances):
            print("- %s" % name)
        return 0

    if not instances:
        filters = []
        if args.status:
            filters.append("status=%s" % args.status)
        if args.name:
            filters.append("name=%s" % args.name)
        if args.datastore_type:
            filters.append("datastore_type=%s" % args.datastore_type)
        suffix = "（过滤条件: %s）" % ", ".join(filters) if filters else ""
        print("当前区域（%s）无 RDS 实例%s。" % (args.region, suffix))
        return 0

    print("Region %s 的 RDS 实例列表（共 %d 个，完整字段）：" % (args.region, len(instances)))
    print(render_table(instances))
    return 0


if __name__ == "__main__":
    sys.exit(main())
