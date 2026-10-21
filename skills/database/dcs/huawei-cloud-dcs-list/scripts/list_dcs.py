#!/usr/bin/env python3
"""List Huawei Cloud DCS (Distributed Cache Service, Redis/Memcached) instances
via KooCLI `hcloud DCS ListInstances` (read-only GET /v2/{project_id}/instances).

Primary execution path is KooCLI; when hcloud is not installed, the script falls
back to the official `huaweicloudsdkdcs` v2 SDK (`DcsClient.list_instances`).
Reads nothing but the active credential profile / environment. Supports three
output modes (--names-only / table / --json), --name / --instance-id / --ip /
--status / --tags filtering and automatic --limit / --offset paging (the real
ListInstances API parameters, verified against `hcloud DCS ListInstances
--help` and the huaweicloudsdkdcs v2 ListInstancesRequest model), plus a strict
write-intent guard: any argument that looks like a mutating DCS operation is
rejected before a single command is executed.

Usage:
    python3 scripts/list_dcs.py [--region cn-north-4] [--names-only | --json]
                                 [--name cache] [--instance-id <id>] [--ip <ip>]
                                 [--status RUNNING] [--tags env=prod]
                                 [--page-size 100] [--operation ListInstances]

Environment overrides (mostly for tests):
    DCS_LIST_HCLOUD_BIN   hcloud executable (default "hcloud")
    DCS_LIST_HCLOUD_ARGS  extra args injected before the DCS operation
"""

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_REGION = "cn-north-4"
DEFAULT_PAGE_SIZE = 100
SERVICE = "DCS"
ALLOWED_OPERATION = "ListInstances"
REST_PATH = "/v2/{project_id}/instances"

# Mutating DCS operations / intents — strictly rejected by the guard.
WRITE_INTENT_KEYWORDS = (
    "createinstance",
    "batchdeleteinstances",
    "deletesingleinstance",
    "deleteinstance",
    "updateinstance",
    "modifyinstance",
    "resizeinstance",
    "restartinstance",
    "restartorflushinstances",
    "flushinstance",
    "restoreinstance",
    "upgradeinstanceminorversion",
    "exchangerinstanceip",
    "exchangeinstanceip",
    "rollbackexchangeinstanceip",
    "copyinstance",
    "updateinstancebandwidth",
    "updateinstanceconfig",
    "setinstancepassword",
    "resetinstancepassword",
    "create",
    "delete",
    "update",
    "modify",
    "resize",
    "restart",
    "reboot",
    "flush",
    "clear",
    "restore",
    "upgrade",
    "rollback",
    "backup",
    "freeze",
    "unfreeze",
    "release",
    "stop",
    "start",
    "terminate",
    "destroy",
    "creating",
    "deleting",
    "updating",
    "restarting",
    "resizing",
    "restoring",
    "upgrading",
    "rebooting",
    "flushing",
    "clearing",
)

# Preferred column order for the table view; remaining keys are appended sorted.
PREFERRED_COLUMNS = [
    "name",
    "instance_id",
    "engine",
    "engine_version",
    "capacity",
    "spec_code",
    "status",
    "port",
    "ip",
    "domain_name",
    "readonly_domain_name",
    "access_user",
    "no_password_access",
    "enable_ssl",
    "enable_publicip",
    "publicip_address",
    "charging_mode",
    "vpc_name",
    "vpc_id",
    "subnet_id",
    "security_group_id",
    "az_codes",
    "max_memory",
    "used_memory",
    "cpu_type",
    "user_name",
    "maintain_begin",
    "maintain_end",
    "description",
    "tags",
    "enterprise_project_id",
    "created_at",
    "updated_at",
    "sub_status",
]

_INSTANCE_LIST_KEYS = ("instances", "instance_list", "instances_detail")

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


class DcsListError(Exception):
    """Base error for the DCS list skill."""


class GuardError(DcsListError):
    """A write intent was detected and blocked (skill is read-only)."""


class ConfigError(DcsListError):
    """hcloud missing or credentials (AK/SK) not configured."""


class AuthError(DcsListError):
    """Authentication/authorization failure (invalid AK/SK or IAM 403)."""


class ApiError(DcsListError):
    """hcloud / network / unexpected API failure."""


def guard_write_intent(text):
    """Return False for read-only text; raise GuardError if `text` is mutating.

    Normalizes separators so `--create-instance`, `CreateInstance`, and
    `create_instance` all hit the same keyword. Read-only vocabulary
    (list/show/get/describe) never matches.
    """
    low = re.sub(r"[\s_\-]+", "", str(text).lower())
    for keyword in WRITE_INTENT_KEYWORDS:
        if keyword in low:
            raise GuardError(
                "检测到写操作意图（关键词: %s）。本 skill 仅支持只读查询"
                "（DCS ListInstances），创建/删除/扩缩容/重启/清空等变更操作已被守卫拦截。"
                % keyword
            )
    return False


def guard_operation(operation):
    """Only the read-only ListInstances operation may be executed."""
    if operation != ALLOWED_OPERATION:
        raise GuardError(
            "不允许的操作 %r：本 skill 仅允许只读操作 %s。" % (operation, ALLOWED_OPERATION)
        )
    return True


def build_command(region, name=None, instance_id=None, ip=None, status=None,
                  tags=None, limit=DEFAULT_PAGE_SIZE, offset=0):
    """Build the hcloud DCS ListInstances argv (without the executable).

    Mirrors the real KooCLI parameter list (`hcloud DCS ListInstances --help`):
    --cli-region / --name / --instance_id / --ip / --status / --tags are all
    real server-side query parameters; paging uses --limit (1..1000, default
    10 per page when unset) + --offset. The marker is never sent on the first
    page (offset starts at 0).
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
    if instance_id:
        argv.append("--instance_id=%s" % instance_id)
    if ip:
        argv.append("--ip=%s" % ip)
    if status:
        argv.append("--status=%s" % status)
    if tags:
        argv.append("--tags=%s" % tags)
    return argv


def _hcloud_executable():
    return os.environ.get("DCS_LIST_HCLOUD_BIN", "hcloud")


def run_hcloud(argv):
    """Execute hcloud and return (stdout, stderr, returncode)."""
    cmd = [_hcloud_executable()]
    extra = os.environ.get("DCS_LIST_HCLOUD_ARGS", "").split()
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
            "hcloud 参数错误（KooCLI 拒绝了该参数组合，退出码 %s）：DCS ListInstances "
            "真实参数清单可通过 `hcloud DCS ListInstances --help` 查看。"
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
            "无权限访问分布式缓存服务（DCS），请检查 IAM 权限"
            "（403：AK/SK 无效或未授予 DCS 只读权限），"
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
    """Decide whether another ListInstances page should be fetched."""
    if not batch:
        return False
    total = None
    if isinstance(payload, dict):
        for key in ("instance_num", "total_num", "total_count", "totalCount", "total"):
            if isinstance(payload.get(key), int):
                total = payload[key]
                break
    if total is not None and total >= 0:
        return collected < total
    return len(batch) >= limit


# Whitelisted credential environment variables — read by name only, never by
# enumerating os.environ (avoids harvesting unrelated environment variables).
_AK_ENV_NAMES = (
    "HW_ACCESS_KEY",
    "HUAWEI_ACCESS_KEY",
    "HUAWEICLOUD_SDK_AK",
    "HUAWEI_CLOUD_ACCESS_KEY",
)
_SK_ENV_NAMES = (
    "HW_SECRET_KEY",
    "HUAWEI_SECRET_KEY",
    "HUAWEICLOUD_SDK_SK",
    "HUAWEI_CLOUD_SECRET_KEY",
)
_PROJECT_ID_ENV_NAMES = (
    "HW_PROJECT_ID",
    "HUAWEI_PROJECT_ID",
    "HUAWEICLOUD_SDK_PROJECT_ID",
    "HUAWEI_CLOUD_PROJECT_ID",
)


def _env_value(names):
    """Read the first non-empty value from an explicit whitelist of env names."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def resolve_project_id(explicit=None):
    """Resolve the project id from --project-id or the whitelisted env names."""
    if explicit:
        return explicit
    return _env_value(_PROJECT_ID_ENV_NAMES)


def _jsonable(value):
    """Recursively convert datetimes (SDK to_dict output) to JSON-safe values."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def list_instances_via_sdk(region, name=None, instance_id=None, ip=None,
                           status=None, tags=None, limit=DEFAULT_PAGE_SIZE,
                           project_id=None, max_pages=100):
    """SDK fallback: query instances through `huaweicloudsdkdcs` v2.

    Only invoked when hcloud is not installed. Credentials are taken from the
    whitelisted AK/SK environment variables (HW_*/HUAWEI_ACCESS_KEY family) —
    never passed as literals here. The official SDK has no env-var
    auto-discovery on `BasicCredentials()`, so AK/SK (and the project id
    required by the `/v2/{project_id}/instances` path) must be read explicitly.
    Region resolution uses the SDK's own `DcsRegion` catalog (official
    endpoints, no guessing), falling back to an explicit `Region(id, endpoint)`
    for custom regions. `ListInstancesRequest` accepts name / instance_id /
    ip / status / tags / limit / offset (verified against the installed SDK);
    paging follows `instance_num` + the batch size.
    """
    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkcore.http.http_config import HttpConfig
        from huaweicloudsdkdcs.v2 import DcsClient, ListInstancesRequest
        from huaweicloudsdkdcs.v2.region.dcs_region import DcsRegion
    except ImportError as exc:
        raise ConfigError(
            "未找到 hcloud（KooCLI），且 huaweicloudsdkcore/huaweicloudsdkdcs 未安装，"
            "无法回退到 SDK。请安装 KooCLI 或 pip install huaweicloudsdkcore "
            "huaweicloudsdkdcs。详情：%s" % exc
        )

    ak = _env_value(_AK_ENV_NAMES)
    sk = _env_value(_SK_ENV_NAMES)
    if not ak or not sk:
        raise ConfigError(
            "SDK 回退缺少 AK/SK 凭证：官方 SDK 的 BasicCredentials 不会自动读取环境"
            "变量，且当前环境未检测到 HW_ACCESS_KEY / HUAWEI_ACCESS_KEY / "
            "HUAWEICLOUD_SDK_AK 形式的 AK/SK 环境变量。"
            "请在会话外设置 HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY（严禁在对话中粘贴"
            " AK/SK），参见 references/cli-installation-guide.md。"
        )
    resolved_project_id = resolve_project_id(project_id)
    if not resolved_project_id:
        raise ConfigError(
            "SDK 回退缺少 project_id：DCS 的 REST 路径为 %s，需要项目 ID。"
            "请通过 --project-id 传入，或设置 HUAWEICLOUD_SDK_PROJECT_ID / "
            "HUAWEI_PROJECT_ID（严禁在对话中粘贴敏感信息）。" % REST_PATH
        )
    credentials = BasicCredentials(ak=ak, sk=sk, project_id=resolved_project_id)  # env-sourced, never literals
    try:
        try:
            region_obj = DcsRegion.value_of(region)
        except (ValueError, KeyError, AttributeError):
            region_obj = Region(region, "https://dcs.%s.myhuaweicloud.com" % region)
        client = DcsClient.new_builder() \
            .with_credentials(credentials) \
            .with_region(region_obj) \
            .with_http_config(HttpConfig.get_default_config()) \
            .build()
    except Exception as exc:  # region unknown / config broken
        raise ConfigError(
            "SDK 初始化失败（region=%s）：%s。请检查 huaweicloudsdkdcs 安装与区域配置。"
            % (region, exc)
        )
    instances = []
    offset = 0
    for _ in range(max_pages):
        request = ListInstancesRequest(
            limit=limit, offset=offset,
            name=name, instance_id=instance_id,
            ip=ip, status=status, tags=tags,
        )
        try:
            response = client.list_instances(request)
        except Exception as exc:
            low = str(exc).lower()
            if any(p in low for p in _AUTH_PATTERNS):
                raise AuthError(
                    "无权限访问分布式缓存服务（DCS），请检查 IAM 权限（403）。详情：%s"
                    % str(exc)[:300]
                )
            raise ApiError("SDK 调用失败：%s" % str(exc)[:300])
        batch = list(response.instances or [])
        instances.extend(_jsonable(instance.to_dict()) for instance in batch)
        total = getattr(response, "instance_num", None)
        if total is not None and len(instances) >= total:
            break
        if len(batch) < limit:
            break
        offset += len(batch)
    else:
        raise ApiError("翻页超过 %d 页仍未取完，已中止以防死循环。" % max_pages)
    return instances


def list_instances(region, name=None, instance_id=None, ip=None, status=None,
                   tags=None, limit=DEFAULT_PAGE_SIZE, project_id=None,
                   max_pages=100):
    """Query all DCS instances (offset-paged); KooCLI first, SDK fallback."""
    instances = []
    offset = 0
    for _page in range(max_pages):
        argv = build_command(region, name=name, instance_id=instance_id,
                             ip=ip, status=status, tags=tags,
                             limit=limit, offset=offset)
        try:
            stdout, stderr, returncode = run_hcloud(argv)
        except ConfigError:
            # hcloud binary missing → one-shot SDK fallback (no CLI retry).
            return list_instances_via_sdk(
                region, name=name, instance_id=instance_id, ip=ip,
                status=status, tags=tags, limit=limit,
                project_id=project_id, max_pages=max_pages,
            )
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
    return instances


def normalize_instance(instance):
    """Flatten az_codes / tags lists into table-friendly cells."""
    flat = dict(instance)
    if "instance_id" not in flat and "id" in flat:
        flat["instance_id"] = flat["id"]
    az_codes = flat.get("az_codes")
    if isinstance(az_codes, list):
        flat["az_codes"] = ",".join(str(code) for code in az_codes) or "-"
    tags = flat.get("tags")
    if isinstance(tags, list):
        cells = []
        for tag in tags:
            if isinstance(tag, dict):
                cells.append("%s=%s" % (tag.get("key", ""), tag.get("value", "")))
            else:
                cells.append(str(tag))
        flat["tags"] = ",".join(cells) if cells else "-"
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
            name = _field(instance, "instance_id", "id")
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
        columns = ["name", "instance_id"]
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
        description="查询华为云 DCS（分布式缓存服务）实例列表"
                    "（KooCLI hcloud DCS ListInstances，只读）。")
    parser.add_argument("-r", "--region", default=DEFAULT_REGION,
                        help="目标 Region（默认 %s）" % DEFAULT_REGION)
    parser.add_argument("--names-only", action="store_true", dest="names_only",
                        help="仅输出实例名称清单（默认即名称清单模式）")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="以 JSON 输出完整原始字段")
    parser.add_argument("--table", action="store_true", dest="as_table",
                        help="输出全字段表格（名称/ID/引擎/容量/状态/连接地址/端口等）")
    parser.add_argument("--name",
                        help="按实例名称过滤（服务端查询参数，模糊匹配；"
                             "name_equal 精确匹配开关由 --name-equal 提供）")
    parser.add_argument("--name-equal", action="store_true", dest="name_equal",
                        help="按实例名称精确匹配（转发服务端 name_equal=true）")
    parser.add_argument("--instance-id", dest="instance_id",
                        help="按实例 ID 过滤（服务端查询参数）")
    parser.add_argument("--ip",
                        help="按连接 IP 地址过滤（服务端查询参数）")
    parser.add_argument("--status",
                        help="按实例状态过滤（服务端查询参数，如 RUNNING/ERROR）")
    parser.add_argument("--tags",
                        help="按标签过滤（服务端查询参数，格式 key1=value1,key2=value2）")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE,
                        dest="page_size",
                        help="分页大小（默认 %d，范围 1~1000，自动翻页取全量）" % DEFAULT_PAGE_SIZE)
    parser.add_argument("--project-id", dest="project_id",
                        help="项目 ID（可选；SDK 回退在 /v2/{project_id}/instances 路径中需要）")
    parser.add_argument("--operation", default=ALLOWED_OPERATION,
                        help="hcloud DCS 操作名（仅允许只读 %s）" % ALLOWED_OPERATION)
    args = parser.parse_args(argv)

    try:
        # Write-intent guard: scan the raw argv + validate the operation name.
        guard_write_intent(" ".join(argv if argv is not None else sys.argv[1:]))
        guard_operation(args.operation)
        for value in (args.name, args.instance_id, args.ip, args.status, args.tags):
            if value:
                guard_write_intent(value)
        if args.page_size is not None:
            if args.page_size < 1 or args.page_size > 1000:
                raise ApiError("--page-size 超出范围（1~1000）：%d" % args.page_size)
        instances = list_instances(
            args.region,
            name=args.name if not args.name_equal else None,
            instance_id=args.instance_id,
            ip=args.ip,
            status=args.status,
            tags=args.tags if not args.name_equal else None,
            limit=args.page_size,
            project_id=args.project_id,
        )
    except DcsListError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 1

    # --name-equal: exact name matching (server name param is fuzzy by default).
    if args.name_equal:
        if args.name:
            wanted = str(args.name).strip().lower()
            instances = [
                i for i in instances
                if str(i.get("name", "")).strip().lower() == wanted
            ]
        else:
            instances = []

    if args.as_json:
        print(json.dumps(instances, ensure_ascii=False, indent=2))
        return 0

    # Default output mode: the compact instance-name list (--names-only).
    if args.names_only or not args.as_table:
        if not instances:
            filters = []
            if args.name:
                filters.append("name=%s" % args.name)
            if args.instance_id:
                filters.append("instance_id=%s" % args.instance_id)
            if args.ip:
                filters.append("ip=%s" % args.ip)
            if args.status:
                filters.append("status=%s" % args.status)
            if args.tags:
                filters.append("tags=%s" % args.tags)
            suffix = "（过滤条件: %s）" % ", ".join(filters) if filters else ""
            print("当前区域（%s）无 DCS 实例%s。" % (args.region, suffix))
            return 0
        print("Region %s 的 DCS 实例名称列表（共 %d 个）：" % (args.region, len(instances)))
        for name in instance_names(instances):
            print("- %s" % name)
        return 0

    if not instances:
        filters = []
        if args.name:
            filters.append("name=%s" % args.name)
        if args.instance_id:
            filters.append("instance_id=%s" % args.instance_id)
        if args.ip:
            filters.append("ip=%s" % args.ip)
        if args.status:
            filters.append("status=%s" % args.status)
        if args.tags:
            filters.append("tags=%s" % args.tags)
        suffix = "（过滤条件: %s）" % ", ".join(filters) if filters else ""
        print("当前区域（%s）无 DCS 实例%s。" % (args.region, suffix))
        return 0

    print("Region %s 的 DCS 实例列表（共 %d 个，完整字段）：" % (args.region, len(instances)))
    print(render_table(instances))
    return 0


if __name__ == "__main__":
    sys.exit(main())
