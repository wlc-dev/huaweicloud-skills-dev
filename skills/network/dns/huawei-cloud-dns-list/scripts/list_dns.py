#!/usr/bin/env python3
"""List Huawei Cloud DNS (云解析服务) zones / record sets via KooCLI `hcloud DNS`.

Primary execution path is KooCLI:
    hcloud DNS ListPublicZones  --cli-region=<region>   (read-only GET /v2/zones)
    hcloud DNS ListPrivateZones --cli-region=<region>   (read-only GET /v2/zones, type=private)
    hcloud DNS ListRecordSets   --cli-region=<region>   (read-only GET /v2/recordsets)
When hcloud is not installed the script falls back to the official
`huaweicloudsdkdns` v2 SDK (`DnsClient.list_public_zones` /
`list_private_zones` / `list_record_sets`). Reads nothing but the active
credential profile / environment. Supports three output modes
(table / --json / --names-only), --type / --id / --name filters (all real
server-side query parameters), marker-based paging, and a strict write-intent
guard: any argument that looks like a mutating DNS operation is rejected before
a single command is executed.

Usage:
    python3 scripts/list_dns.py [--region cn-north-4]
                                [--type public|private] [--recordsets]
                                [--json | --names-only]
                                [--id <zone-id>] [--name <domain>]
                                [--record-type A] [--page-size 100]
                                [--project-id <id>] [--operation ListPublicZones]

Environment overrides (mostly for tests):
    DNS_LIST_HCLOUD_BIN   hcloud executable (default "hcloud")
    DNS_LIST_HCLOUD_ARGS  extra args injected before the DNS operation
"""

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_REGION = "cn-north-4"
DEFAULT_PAGE_SIZE = 100
SERVICE = "DNS"

OP_LIST_PUBLIC_ZONES = "ListPublicZones"
OP_LIST_PRIVATE_ZONES = "ListPrivateZones"
OP_LIST_RECORD_SETS = "ListRecordSets"
ALLOWED_OPERATIONS = (
    OP_LIST_PUBLIC_ZONES,
    OP_LIST_PRIVATE_ZONES,
    OP_LIST_RECORD_SETS,
)

# Official read-only REST paths, verified from the huaweicloudsdkdns v2
# `DnsClient._*_http_info` metadata (never inferred).
REST_PATH_ZONES = "/v2/zones"
REST_PATH_RECORD_SETS = "/v2/recordsets"

# Mutating DNS operations / intents — strictly rejected by the guard.
WRITE_INTENT_KEYWORDS = (
    "createpubliczone",
    "createprivatezone",
    "deletepubliczone",
    "deleteprivatezone",
    "updatepubliczone",
    "updateprivatezone",
    "batchcreatepubliczones",
    "batchdeletepubliczones",
    "batchupdatzones",
    "createrecordset",
    "createrecordsets",
    "createpublicrecordset",
    "createprivateset",
    "deleterecordset",
    "deleterecordsets",
    "updaterecordset",
    "updaterecordsets",
    "batchcreaterecordsets",
    "batchdeleterecordsets",
    "batchupdaterecordsets",
    "create",
    "delete",
    "update",
    "modify",
    "associate",
    "disassociate",
    "dissociate",
    "attach",
    "detach",
    "bind",
    "unbind",
    "release",
    "remove",
    "destroy",
    "change",
    "transfer",
    "restore",
    "enable",
    "disable",
    "import",
    "export",
    "restart",
    "creating",
    "deleting",
    "updating",
    "enabling",
    "disabling",
)

# Preferred column order for the table view; remaining keys are appended sorted.
PREFERRED_COLUMNS = [
    "id",
    "name",
    "zone_type",
    "type",
    "status",
    "record_num",
    "records",
    "ttl",
    "zone_id",
    "zone_name",
    "email",
    "serial",
    "pool_id",
    "description",
    "enterprise_project_id",
    "project_id",
    "default",
    "create_at",
    "created_at",
    "update_at",
    "updated_at",
]

_ITEM_LIST_KEYS = ("zones", "recordsets", "record_sets", "recordSets")

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


class DnsListError(Exception):
    """Base error for the DNS list skill."""


class GuardError(DnsListError):
    """A write intent was detected and blocked (skill is read-only)."""


class ConfigError(DnsListError):
    """hcloud missing or credentials (AK/SK) not configured."""


class AuthError(DnsListError):
    """Authentication/authorization failure (invalid AK/SK or IAM 403)."""


class ApiError(DnsListError):
    """hcloud / network / unexpected API failure."""


def guard_write_intent(text):
    """Raise GuardError if `text` carries a mutating intent.

    Normalizes separators so `--create-zone`, `CreatePublicZone`, and
    `create_zone` all hit the same keyword. Read-only vocabulary
    (list/show/get/describe) never matches.
    """
    low = re.sub(r"[\s_\-]+", "", str(text).lower())
    for keyword in WRITE_INTENT_KEYWORDS:
        if keyword in low:
            raise GuardError(
                "检测到写操作意图（关键词: %s）。本 skill 仅支持只读查询"
                "（DNS ListPublicZones / ListPrivateZones / ListRecordSets），"
                "创建/删除/更新域名的变更操作已被守卫拦截。" % keyword
            )
    return False


def guard_operation(operation):
    """Only the read-only list operations may be executed."""
    if operation not in ALLOWED_OPERATIONS:
        raise GuardError(
            "不允许的操作 %r：本 skill 仅允许只读操作 %s。"
            % (operation, " / ".join(ALLOWED_OPERATIONS))
        )
    return True


def resolve_operation(type_arg, recordsets):
    """Map --type / --recordsets to the concrete read-only DNS operation."""
    if recordsets:
        return OP_LIST_RECORD_SETS
    if type_arg == "private":
        return OP_LIST_PRIVATE_ZONES
    return OP_LIST_PUBLIC_ZONES


def build_command(region, operation, zone_type="public", item_id=None,
                  name=None, record_type=None, limit=DEFAULT_PAGE_SIZE,
                  marker=None):
    """Build the hcloud DNS argv (without the executable).

    Mirrors the real KooCLI parameter list for the read-only DNS list
    operations: --cli-region / --limit / --marker plus the real server-side
    filters. Zone listings use the operation's implicit type
    (ListPublicZones → public, ListPrivateZones → private); record-set
    listings take --zone_type (public/private) and an optional --type
    (record type, e.g. A/AAAA/CNAME).
    """
    argv = [
        SERVICE,
        operation,
        "--cli-region=%s" % region,
        "--limit=%d" % limit,
    ]
    if marker:
        argv.append("--marker=%s" % marker)
    if item_id:
        argv.append("--id=%s" % item_id)
    if name:
        argv.append("--name=%s" % name)
    if operation == OP_LIST_RECORD_SETS:
        argv.append("--zone_type=%s" % zone_type)
        if record_type:
            argv.append("--type=%s" % record_type)
    return argv


def _hcloud_executable():
    return os.environ.get("DNS_LIST_HCLOUD_BIN", "hcloud")


def run_hcloud(argv):
    """Execute hcloud and return (stdout, stderr, returncode)."""
    cmd = [_hcloud_executable()]
    extra = os.environ.get("DNS_LIST_HCLOUD_ARGS", "").split()
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
            "hcloud 参数错误（KooCLI 拒绝了该参数组合，退出码 %s）：DNS 列表操作"
            "真实参数清单可通过 `hcloud DNS ListPublicZones --help` 查看。"
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
            "无权限访问云解析服务（DNS），请检查 IAM 权限（403：AK/SK 无效或未授予 DNS 只读权限），"
            "参见 references/iam-policies.md。详情：%s" % blob[:300]
        )
    return ApiError(
        "hcloud 调用失败（退出码 %s）：%s" % (returncode, blob[:300])
    )


def extract_items(payload):
    """Pull the zone / record-set list out of a DNS list response."""
    if isinstance(payload, list):
        return payload
    for key in _ITEM_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _item_id(item):
    if isinstance(item, dict):
        return item.get("id")
    return None


def _total_count(payload):
    """Read `metadata.total_count` from a DNS list response, if present."""
    if isinstance(payload, dict):
        meta = payload.get("metadata") or payload.get("page_info") \
            or payload.get("pageInfo")
        if isinstance(meta, dict):
            total = meta.get("total_count")
            if total is None:
                total = meta.get("totalCount")
            if isinstance(total, int) and not isinstance(total, bool):
                return total
    return None


def _next_marker(payload, items):
    """Determine the marker for the next page.

    The DNS list APIs page by the **id of the last resource of the previous
    page** (their responses carry `metadata.total_count` but no
    `next_marker`); a `next_marker` is honoured first if a proxy ever
    provides one.
    """
    if isinstance(payload, dict):
        page_info = (payload.get("page_info") or payload.get("pageInfo")
                     or payload.get("metadata"))
        if isinstance(page_info, dict):
            marker = page_info.get("next_marker") or page_info.get("nextMarker")
            if marker:
                return str(marker)
    if items:
        last_id = _item_id(items[-1])
        if last_id:
            return str(last_id)
    return None


def _jsonable(value):
    """Recursively convert datetimes (SDK to_dict output) to JSON-safe values."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


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


def list_dns_via_sdk(region, operation, zone_type="public", item_id=None,
                     name=None, record_type=None, limit=DEFAULT_PAGE_SIZE,
                     project_id=None, max_pages=100):
    """SDK fallback: query DNS through `huaweicloudsdkdns` v2.

    Only invoked when hcloud is not installed. Credentials are taken from the
    whitelisted AK/SK environment variables (HW_*/HUAWEI_ACCESS_KEY family) —
    never passed as literals here. The official SDK has no env-var
    auto-discovery on `BasicCredentials()`, so AK/SK and the project id must be
    read explicitly. Region resolution uses the SDK's own `DnsRegion` catalog
    (official endpoints, no guessing), falling back to an explicit
    `Region(id, endpoint)` for custom regions.
    """
    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkcore.http.http_config import HttpConfig
        from huaweicloudsdkdns.v2 import (
            DnsClient, ListPublicZonesRequest, ListPrivateZonesRequest,
            ListRecordSetsRequest,
        )
        from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
    except ImportError as exc:
        raise ConfigError(
            "未找到 hcloud（KooCLI），且 huaweicloudsdkcore/huaweicloudsdkdns 未安装，"
            "无法回退到 SDK。请安装 KooCLI 或 pip install huaweicloudsdkcore "
            "huaweicloudsdkdns。详情：%s" % exc
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
            "SDK 回退缺少 project_id：DNS 的 REST 路径为 %s / %s，需要项目 ID。"
            "请通过 --project-id 传入，或设置 HUAWEICLOUD_SDK_PROJECT_ID / "
            "HUAWEI_PROJECT_ID（严禁在对话中粘贴敏感信息）。"
            % (REST_PATH_ZONES, REST_PATH_RECORD_SETS)
        )
    credentials = BasicCredentials(ak=ak, sk=sk, project_id=resolved_project_id)  # env-sourced, never literals
    try:
        try:
            region_obj = DnsRegion.value_of(region)
        except (ValueError, KeyError, AttributeError):
            region_obj = Region(region, "https://dns.%s.myhuaweicloud.com" % region)
        client = DnsClient.new_builder() \
            .with_credentials(credentials) \
            .with_region(region_obj) \
            .with_http_config(HttpConfig.get_default_config()) \
            .build()
    except Exception as exc:  # region unknown / config broken
        raise ConfigError(
            "SDK 初始化失败（region=%s）：%s。请检查 huaweicloudsdkdns 安装与区域配置。"
            % (region, exc)
        )
    items = []
    marker = None
    for _ in range(max_pages):
        if operation == OP_LIST_RECORD_SETS:
            request = ListRecordSetsRequest(
                zone_type=zone_type, limit=limit, marker=marker,
                id=item_id, name=name, type=record_type,
            )
        elif operation == OP_LIST_PRIVATE_ZONES:
            request = ListPrivateZonesRequest(
                type="private", limit=limit, marker=marker,
                id=item_id, name=name,
            )
        else:
            request = ListPublicZonesRequest(
                type="public", limit=limit, marker=marker,
                id=item_id, name=name,
            )
        try:
            if operation == OP_LIST_RECORD_SETS:
                response = client.list_record_sets(request)
                batch_objs = list(response.recordsets or [])
            elif operation == OP_LIST_PRIVATE_ZONES:
                response = client.list_private_zones(request)
                batch_objs = list(response.zones or [])
            else:
                response = client.list_public_zones(request)
                batch_objs = list(response.zones or [])
        except Exception as exc:
            low = str(exc).lower()
            if any(p in low for p in _AUTH_PATTERNS):
                raise AuthError(
                    "无权限访问云解析服务（DNS），请检查 IAM 权限（403）。详情：%s"
                    % str(exc)[:300]
                )
            raise ApiError("SDK 调用失败：%s" % str(exc)[:300])
        batch = [_jsonable(obj.to_dict()) for obj in batch_objs]
        items.extend(batch)
        try:
            total = _total_count(_jsonable(response.to_dict()))
        except Exception:
            total = None
        if total is not None and len(items) >= total:
            break
        next_marker = _next_marker({}, batch)
        if not next_marker or not batch or len(batch) < limit \
                or next_marker == marker:
            break
        marker = next_marker
    else:
        raise ApiError("翻页超过 %d 页仍未取完，已中止以防死循环。" % max_pages)
    return items


def list_dns(region, operation, zone_type="public", item_id=None, name=None,
             record_type=None, limit=DEFAULT_PAGE_SIZE, project_id=None,
             max_pages=100):
    """Query all DNS zones / record sets (marker-paged); KooCLI first, SDK fallback."""
    items = []
    marker = None
    for _page in range(max_pages):
        argv = build_command(region, operation, zone_type=zone_type,
                             item_id=item_id, name=name,
                             record_type=record_type, limit=limit, marker=marker)
        try:
            stdout, stderr, returncode = run_hcloud(argv)
        except ConfigError:
            # hcloud binary missing → one-shot SDK fallback (no CLI retry).
            items = list_dns_via_sdk(
                region, operation, zone_type=zone_type, item_id=item_id,
                name=name, record_type=record_type, limit=limit,
                project_id=project_id, max_pages=max_pages,
            )
            break
        if returncode != 0 or _USE_ERROR_MARKER in (stdout + " " + stderr).lower():
            # KooCLI usage errors print [USE_ERROR] on stdout with rc=0.
            raise classify_hcloud_failure(stdout, stderr, returncode)
        payload = extract_json(stdout)
        batch = extract_items(payload)
        items.extend(batch)
        total = _total_count(payload)
        if total is not None and len(items) >= total:
            break
        new_marker = _next_marker(payload, batch)
        if not new_marker or not batch or len(batch) < limit \
                or new_marker == marker:
            break
        marker = new_marker
    else:
        raise ApiError("翻页超过 %d 页仍未取完，已中止以防死循环。" % max_pages)
    return items


def _field(item, *names, default="-"):
    for name in names:
        if name in item and item[name] not in (None, ""):
            return item[name]
    return default


def item_names(items):
    """Compact name list (DNS domain name, falling back to id)."""
    names = []
    for item in items:
        name = _field(item, "name", default=None)
        if name is None:
            name = _field(item, "id")
        names.append(str(name))
    return names


def _cell(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def render_table(items):
    """Render full-field table output (union of all returned fields)."""
    rows_data = [dict(item) for item in items]
    columns = []
    for key in PREFERRED_COLUMNS:
        if any(key in row for row in rows_data):
            columns.append(key)
    for key in sorted({k for row in rows_data for k in row}):
        if key not in columns:
            columns.append(key)
    if not columns:
        columns = ["id", "name"]
    rows = [[_cell(_field(row, col)) for col in columns] for row in rows_data]
    widths = [max(len(col), *(len(row[i]) for row in rows))
              for i, col in enumerate(columns)]
    header = "  ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
    separator = "  ".join("-" * w for w in widths)
    lines = [header, separator]
    for row in rows:
        lines.append("  ".join(row[i].ljust(widths[i])
                               for i in range(len(columns))))
    return "\n".join(lines)


def _zone_type_label(zone_type):
    return "私网" if zone_type == "private" else "公网"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="查询华为云云解析服务（DNS）域名/记录集名称列表"
                    "（KooCLI hcloud DNS ListPublicZones/ListPrivateZones/ListRecordSets，只读）。")
    parser.add_argument("-r", "--region", default=DEFAULT_REGION,
                        help="目标 Region（默认 %s）" % DEFAULT_REGION)
    parser.add_argument("--type", choices=("public", "private"), default="public",
                        help="域名类型：public 公网域名（默认）/ private 私网域名")
    parser.add_argument("--recordsets", action="store_true", dest="recordsets",
                        help="改为查询记录集列表（ListRecordSets）而非域名列表")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="以 JSON 输出完整原始字段")
    parser.add_argument("--names-only", action="store_true", dest="names_only",
                        help="仅输出域名 / 记录集名称清单")
    parser.add_argument("--id", dest="item_id",
                        help="按域名 ID（或记录集 ID）过滤（服务端查询参数）")
    parser.add_argument("--name",
                        help="按域名过滤（服务端模糊查询参数）")
    parser.add_argument("--record-type", dest="record_type",
                        help="记录集类型过滤（仅 --recordsets 有效，如 A / AAAA / CNAME）")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE,
                        dest="page_size",
                        help="分页大小（默认 %d，范围 0~500）" % DEFAULT_PAGE_SIZE)
    parser.add_argument("--project-id", dest="project_id",
                        help="项目 ID（可选；SDK 回退在 /v2/zones、/v2/recordsets 路径中需要）")
    parser.add_argument("--operation", default=None,
                        help="hcloud DNS 操作名（仅允许只读 %s）"
                             % " / ".join(ALLOWED_OPERATIONS))
    args = parser.parse_args(argv)

    raw_argv = argv if argv is not None else sys.argv[1:]

    try:
        # Write-intent guard: scan the raw argv + validate the operation name.
        guard_write_intent(" ".join(raw_argv))
        operation = args.operation or resolve_operation(args.type, args.recordsets)
        guard_operation(operation)
        items = list_dns(
            args.region,
            operation,
            zone_type=args.type,
            item_id=args.item_id,
            name=args.name,
            record_type=args.record_type,
            limit=args.page_size,
            project_id=args.project_id,
        )
    except DnsListError as exc:
        print("[错误] %s" % exc, file=sys.stderr)
        return 1

    is_record_sets = operation == OP_LIST_RECORD_SETS
    subject = "DNS 记录集" if is_record_sets else "DNS %s域名" % _zone_type_label(args.type)

    if args.as_json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    if args.names_only:
        print("Region %s 的 %s名称列表（共 %d 个）："
              % (args.region, subject, len(items)))
        for name in item_names(items):
            print("- %s" % name)
        return 0

    if not items:
        filters = []
        if args.item_id:
            filters.append("id=%s" % args.item_id)
        if args.name:
            filters.append("name=%s" % args.name)
        if args.record_type and is_record_sets:
            filters.append("record_type=%s" % args.record_type)
        suffix = "（过滤条件: %s）" % ", ".join(filters) if filters else ""
        print("当前区域（%s）无 %s%s。" % (args.region, subject, suffix))
        return 0

    print("Region %s 的 %s列表（共 %d 个，完整字段）："
          % (args.region, subject, len(items)))
    print(render_table(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())