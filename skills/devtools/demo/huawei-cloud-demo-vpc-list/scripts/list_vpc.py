#!/usr/bin/env python3
"""只读查询华为云 VPC 列表（hcloud VPC ListVpcs）。

安全基线：
- 仅构造 `hcloud VPC ListVpcs`（GET /v1/{project_id}/vpcs）；
- 写意图守卫在参数解析前拦截变更类词汇，命中即退出，不发出任何调用；
- 不读取、不回显、不落盘 AK/SK，凭据由 KooCLI profile / 环境变量提供。
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys

SERVICE = "VPC"
OPERATION = "ListVpcs"

# 写意图词汇：出现即视为变更类请求，技能为严格只读
MUTATING_WORDS = (
    "create", "delete", "update", "modify", "associate", "disassociate",
    "attach", "detach", "bind", "unbind", "release", "change", "restart",
    "remove", "add", "set", "drop", "reset",
)

# 这些开关后跟的是模式/数值/路径，不参与关键词判定
VALUE_FLAGS = ("--region", "-r", "--limit", "--max-pages", "--timeout", "--hcloud-bin")


class GuardError(Exception):
    """写意图被守卫拦截。"""


class ApiError(Exception):
    """KooCLI / OpenAPI 调用失败。"""


def guard(argv: list[str]) -> None:
    """扫描命令行，命中写意图词汇即抛 GuardError。"""
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token in VALUE_FLAGS:
            skip_next = True
            continue
        if token.startswith("-"):
            lowered = token.lower()
            for word in MUTATING_WORDS:
                if word in lowered:
                    raise GuardError(token)
            continue
        # 任何裸位置参数都不是本技能支持的用法（防止把 hcloud 子命令透传进来）
        raise GuardError(token)


def build_command(hcloud: str, region: str, limit: int, marker: str | None) -> list[str]:
    """唯一允许构造的 KooCLI 调用：只读 ListVpcs。"""
    cmd = [hcloud, SERVICE, OPERATION, f"--cli-region={region}", f"--limit={limit}"]
    if marker:
        cmd.append(f"--marker={marker}")
    return cmd


def extract_json(raw: str) -> dict:
    """从 hcloud 输出中截取 JSON（容忍前置 warning 文本）。"""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ApiError(f"输出不是 JSON：{raw[:200]!r}")
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ApiError(f"JSON 解析失败：{exc}; 原文 {raw[:200]!r}") from exc


def classify(parsed: dict, stderr: str) -> None:
    """把 KooCLI 错误信封转成明确的中文提示。"""
    err = parsed.get("error_code") or parsed.get("error_msg") or parsed.get("error")
    if not err:
        return
    detail = str(parsed.get("error_msg") or parsed.get("error_message") or err)
    if "403" in detail or str(err) == "403":
        raise ApiError("无权限访问虚拟私有云（VPC），请检查 IAM 权限（vpc:vpcs:list）")
    if "401" in detail or str(err) == "401":
        raise ApiError("凭据无效或已过期，请带外重新配置 KooCLI profile（勿在对话中传 AK/SK）")
    raise ApiError(f"华为云 API 返回错误：{detail[:200]}")


def fetch_page(hcloud: str, region: str, limit: int, marker: str | None, timeout: int) -> dict:
    cmd = build_command(hcloud, region, limit, marker)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise ApiError(
            "未找到 KooCLI（hcloud），请先安装：见 references/cli-installation-guide.md"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ApiError(f"KooCLI 调用超时（{timeout}s）") from exc

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    # KooCLI 部分参数错误 rc=0 但输出 [USE_ERROR]
    if "[USE_ERROR]" in stderr or "[USE_ERROR]" in stdout:
        raise ApiError(f"hcloud 参数错误：{(stderr or stdout)[:200]}")
    if proc.returncode != 0 and not stdout.startswith("{"):
        raise ApiError(f"hcloud 执行失败（rc={proc.returncode}）：{stderr[:200] or stdout[:200]}")
    parsed = extract_json(stdout)
    classify(parsed, stderr)
    return parsed


def collect(hcloud: str, region: str, limit: int, max_pages: int, timeout: int) -> list[dict]:
    vpcs: list[dict] = []
    marker: str | None = None
    for _ in range(max_pages):
        page = fetch_page(hcloud, region, limit, marker, timeout)
        vpcs.extend(page.get("vpcs") or [])
        marker = ((page.get("page_info") or {}).get("next_marker") or "").strip() or None
        if not marker:
            break
    return vpcs


def render_table(vpcs: list[dict], region: str) -> str:
    headers = ("id", "name", "cidr", "status", "enterprise_project_id", "created_at")
    rows = [[str(v.get(h) if v.get(h) not in (None, "") else "-") for h in headers] for v in vpcs]
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    out = [f"区域：{region}  共 {len(vpcs)} 个 VPC", line, "-" * len(line)]
    out.extend("  ".join(c.ljust(w) for c, w in zip(row, widths)) for row in rows)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # 守卫先于参数解析：任何写意图都在构造/执行命令之前被拦下
    try:
        guard(raw_args)
    except GuardError as exc:
        print(f"[错误] 检测到写操作意图（{exc}），本技能为只读，请求已被守卫拦截", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description="只读查询华为云 VPC 列表（hcloud VPC ListVpcs）"
    )
    parser.add_argument("--region", "-r", default="cn-north-4")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON 数组")
    parser.add_argument("--names-only", action="store_true", help="只输出名称清单")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--hcloud-bin", default="hcloud", help="hcloud 可执行文件路径")
    args = parser.parse_args(raw_args)

    if not 1 <= args.limit <= 2000:
        print("[错误] --limit 必须在 1–2000 之间", file=sys.stderr)
        return 1
    if args.max_pages < 1:
        print("[错误] --max-pages 必须 ≥ 1", file=sys.stderr)
        return 1

    hcloud = args.hcloud_bin
    if hcloud == "hcloud":
        hcloud = shutil.which("hcloud") or "hcloud"

    try:
        vpcs = collect(hcloud, args.region, args.limit, args.max_pages, args.timeout)
    except ApiError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    if args.names_only:
        for v in vpcs:
            print(v.get("name", "-"))
        if not vpcs:
            print(f"当前区域（{args.region}）无虚拟私有云（VPC）")
        return 0
    if args.json:
        print(json.dumps(vpcs, ensure_ascii=False, indent=2))
        return 0
    if not vpcs:
        print(f"当前区域（{args.region}）无虚拟私有云（VPC）")
        return 0
    print(render_table(vpcs, args.region))
    return 0


if __name__ == "__main__":
    sys.exit(main())