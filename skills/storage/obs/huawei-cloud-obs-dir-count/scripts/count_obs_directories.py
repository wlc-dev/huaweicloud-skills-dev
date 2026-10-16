#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Count the number of directories (folders) in a Huawei Cloud OBS bucket.

Prints ONLY the count (a single integer) — nothing else.

Primary executor : KooCLI obsutil-backed `hcloud OBS ls <cloud_url> -d`
                   (counts immediate subdirectories at the given level).
Fallback executor: huaweicloudsdkobs Python SDK
                   (supports immediate and recursive directory counting).

Usage:
  python3 count_obs_directories.py --bucket <bucket> [--prefix <prefix>]
      [--recursive] [--region <region>] [--executor cli|sdk|auto]

Examples:
  python3 count_obs_directories.py --bucket my-bucket
  python3 count_obs_directories.py --bucket my-bucket --prefix photos
  python3 count_obs_directories.py --bucket my-bucket --recursive
"""

import argparse
import os
import re
import subprocess
import sys


CONFIG_GUIDANCE = (
    "请先在您的终端完成以下配置后重试：\n"
    "  1) 安装 KooCLI(hcloud) 并配置 obsutil 凭证：\n"
    "     hcloud obs config -i=<YourAK> -k=<YourSK> -e=obs.<Region>.myhuaweicloud.com\n"
    "     示例(cn-north-4)：hcloud obs config -i=<YourAK> -k=<YourSK> -e=obs.cn-north-4.myhuaweicloud.com\n"
    "  2) 或在环境变量中设置 AK/SK：HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY\n"
    "     （或 HUAWEICLOUD_SDK_AK / HUAWEICLOUD_SDK_SK）\n"
    "  AK/SK 可在华为云控制台『我的凭证』页面获取。请勿在对话中粘贴 AK/SK。"
)


def _translate_cli_error(raw):
    """Map common obsutil CLI error patterns to clear Chinese hints."""
    lower = (raw or "").lower()
    if "nosuchbucket" in lower or "bucket does not exist" in lower:
        return (
            "错误：指定的 OBS 桶不存在，或当前 AK/SK 无权访问该桶（NoSuchBucket）。\n"
            "请检查桶名是否正确，以及 IAM 权限是否包含 obs:bucket:ListBucket / obs:object:List。"
        )
    if "invalidaccesskeyid" in lower:
        return (
            "错误：AK/SK 无效或已过期（InvalidAccessKeyId）。\n"
            "请检查 obsutil 配置中的 AK/SK 是否正确：hcloud obs config -i=<YourAK> -k=<YourSK> -e=obs.<Region>.myhuaweicloud.com"
        )
    if "signaturedoesnotmatch" in lower or "signature" in lower:
        return "错误：请求签名校验失败，请核对 AK/SK 与端点配置是否正确。"
    if "accessdenied" in lower or "forbidden" in lower or "403" in lower:
        return (
            "错误：访问被拒绝（AccessDenied）。当前 AK/SK 无权限读取该桶，\n"
            "请检查 IAM 策略是否包含 obs:bucket:ListBucket / obs:object:List。"
        )
    if "please set ak, sk and endpoint" in lower or "configure the ak, sk and endpoint" in lower or "configuration file" in lower:
        return "错误：未检测到 obsutil 凭证配置。\n" + CONFIG_GUIDANCE
    if "command not found" in lower or "not found: hcloud" in lower or "hcloud: command not found" in lower:
        return (
            "错误：未找到 hcloud (KooCLI) 命令。\n"
            "请先安装 KooCLI，安装说明见 SKILL.md 的 references/cli-installation-guide.md。"
        )
    return None


def _translate_sdk_error(exc):
    """Map common huaweicloudsdkobs exceptions to clear Chinese hints."""
    msg = str(exc)
    lower = msg.lower()
    try:
        code = getattr(exc, "error_code", None) or ""
        lower = (msg + " " + str(code)).lower()
    except Exception:
        pass
    if "nosuchbucket" in lower or "bucket does not exist" in lower:
        return (
            "错误：指定的 OBS 桶不存在，或当前 AK/SK 无权访问该桶（NoSuchBucket）。\n"
            "请检查桶名是否正确，以及 IAM 权限是否包含 obs:bucket:ListBucket / obs:object:List。"
        )
    if "invalidaccesskeyid" in lower:
        return (
            "错误：AK/SK 无效或已过期（InvalidAccessKeyId）。\n"
            "请检查环境变量中的 AK/SK 是否正确（HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY）。"
        )
    if "signaturedoesnotmatch" in lower:
        return "错误：请求签名校验失败，请核对 AK/SK 与区域(region)参数是否正确。"
    if "accessdenied" in lower or "forbidden" in lower or "403" in lower:
        return (
            "错误：访问被拒绝（AccessDenied）。当前 AK/SK 无权限读取该桶，\n"
            "请检查 IAM 策略是否包含 obs:bucket:ListBucket / obs:object:List。"
        )
    if "connection" in lower or "timed out" in lower or "timeout" in lower:
        return "错误：网络连接失败或超时，请检查网络与区域(region)参数。"
    return None


def _get_ak_sk():
    """Resolve AK/SK from common Huawei Cloud environment variables."""
    ak = (
        os.environ.get("HUAWEI_ACCESS_KEY")
        or os.environ.get("HUAWEICLOUD_SDK_AK")
        or os.environ.get("HUAWEI_CLOUD_ACCESS_KEY")
        or os.environ.get("HW_ACCESS_KEY")
    )
    sk = (
        os.environ.get("HUAWEI_SECRET_KEY")
        or os.environ.get("HUAWEICLOUD_SDK_SK")
        or os.environ.get("HUAWEI_CLOUD_SECRET_KEY")
        or os.environ.get("HW_SECRET_KEY")
    )
    return ak, sk


def _build_sdk_client(region):
    from huaweicloudsdkobs.v1.obs_client import ObsClient
    from huaweicloudsdkobs.v1.obs_credentials import ObsCredentials
    from huaweicloudsdkobs.v1.region.obs_region import ObsRegion

    ak, sk = _get_ak_sk()
    if not ak or not sk:
        raise RuntimeError(
            "错误：未找到 AK/SK 凭证（HUAWEI_ACCESS_KEY / HUAWEI_SECRET_KEY，"
            "或 HUAWEICLOUD_SDK_AK / HUAWEICLOUD_SDK_SK）。\n" + CONFIG_GUIDANCE
        )
    credentials = ObsCredentials(ak, sk)
    return ObsClient.new_builder().with_credentials(credentials).with_region(ObsRegion.value_of(region)).build()


def _parse_folder_number(text):
    m = re.search(r"Folder number:\s*(\d+)", text)
    return int(m.group(1)) if m else None


def count_cli_immediate(bucket, prefix):
    """Count immediate subdirectories under bucket/prefix via hcloud OBS ls -d."""
    url = "obs://%s" % bucket
    if prefix:
        url += "/" + prefix.strip("/")
    url += "/"
    try:
        proc = subprocess.run(
            ["hcloud", "OBS", "ls", url, "-d"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "错误：未找到 hcloud (KooCLI) 命令。请先安装 KooCLI（见 "
            "references/cli-installation-guide.md），或使用 --executor sdk 走 SDK 路径。"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("错误：执行 hcloud OBS ls 超时，请检查网络后重试。")
    if proc.returncode != 0:
        raw = (proc.stderr or proc.stdout or "").strip()
        hint = _translate_cli_error(raw)
        raise RuntimeError(hint if hint else raw)
    n = _parse_folder_number(proc.stdout)
    if n is None:
        raise RuntimeError("Could not parse 'Folder number' from hcloud output")
    return n


def count_sdk_immediate(client, bucket, prefix):
    """Count immediate subdirectories via SDK (delimiter='/'), paginated."""
    from huaweicloudsdkobs.v1.model import ListObjectsRequest

    # OBS lists delimiter groups only when the prefix ends with '/', otherwise
    # it may return the folder marker itself instead of its children.
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    count = 0
    marker = None
    while True:
        req = ListObjectsRequest(
            bucket_name=bucket,
            prefix=prefix or None,
            delimiter="/",
            max_keys=1000,
            marker=marker,
        )
        d = client.list_objects(req).to_dict()
        count += len(d.get("common_prefixes") or [])
        marker = d.get("next_marker")
        if not d.get("is_truncated") or not marker:
            break
    return count


def count_sdk_recursive(client, bucket, prefix):
    """Count all directories (all levels) under bucket/prefix via SDK.

    Walks every object key and records each ancestor prefix ending with '/'.
    Zero-byte folder-marker keys (e.g. "photos/") are directories themselves.
    When a prefix is given, only directories strictly under it are counted
    (the prefix itself is not included).
    """
    from huaweicloudsdkobs.v1.model import ListObjectsRequest

    base = prefix.rstrip("/") + "/" if prefix else ""

    dirs = set()
    marker = None
    while True:
        req = ListObjectsRequest(
            bucket_name=bucket,
            prefix=prefix or None,
            max_keys=1000,
            marker=marker,
        )
        d = client.list_objects(req).to_dict()
        for c in d.get("contents") or []:
            key = c.get("key") or ""
            if base:
                if not key.startswith(base):
                    continue
                rel = key[len(base):]
            else:
                rel = key
            parts = rel.split("/")
            # Ancestor prefixes of each object key; a trailing empty part (folder
            # marker) makes the marker itself a directory.
            for i in range(1, len(parts)):
                dirs.add("/".join(parts[:i]) + "/")
        marker = d.get("next_marker")
        if not d.get("is_truncated") or not marker:
            break
    return len(dirs)


def _check_prerequisites(executor, recursive):
    """Best-effort startup validation so the user gets actionable hints before
    a raw English failure. Never touches stdout."""
    if executor == "sdk":
        return  # _build_sdk_client raises a clear Chinese hint when AK/SK is missing
    # cli / auto: only warn about a missing hcloud binary; obsutil credential
    # problems surface through _translate_cli_error at runtime.
    have_hcloud = False
    try:
        proc = subprocess.run(
            ["bash", "-lc", "command -v hcloud"], capture_output=True, text=True, timeout=10
        )
        have_hcloud = proc.returncode == 0
    except Exception:
        have_hcloud = False
    if not have_hcloud:
        print(
            "提示：未检测到 hcloud (KooCLI)。若需 CLI 方式执行，请先安装；"
            "也可用 --executor sdk 走 SDK 路径。\n"
            "安装说明见 references/cli-installation-guide.md。",
            file=sys.stderr,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Count directories in a Huawei Cloud OBS bucket. Prints ONLY the count."
    )
    parser.add_argument("--bucket", required=True, help="OBS bucket name")
    parser.add_argument("--prefix", default="", help="Optional directory prefix to count under")
    parser.add_argument("--recursive", action="store_true", help="Count all nested directories")
    parser.add_argument("--region", default="cn-north-4", help="Huawei Cloud region (default cn-north-4)")
    parser.add_argument(
        "--executor", default="auto", choices=["auto", "cli", "sdk"],
        help="Execution method: cli (hcloud obsutil), sdk (python SDK), auto (try cli first, fallback to sdk)",
    )
    args = parser.parse_args()

    recursive = args.recursive

    try:
        # --- Auto: prefer CLI for immediate counts, SDK for recursive ---
        if args.executor == "auto":
            if recursive:
                _check_prerequisites("sdk", recursive)
                client = _build_sdk_client(args.region)
                print(count_sdk_recursive(client, args.bucket, args.prefix))
                return
            _check_prerequisites("auto", recursive)
            try:
                print(count_cli_immediate(args.bucket, args.prefix))
                return
            except Exception as exc:
                try:
                    client = _build_sdk_client(args.region)
                    print(count_sdk_immediate(client, args.bucket, args.prefix))
                    return
                except Exception as sdk_exc:
                    raise sdk_exc from exc

        # --- Explicit executor ---
        if args.executor == "cli":
            if recursive:
                # CLI has no recursive flag; fall back to the SDK for recursive counting.
                _check_prerequisites("sdk", recursive)
                client = _build_sdk_client(args.region)
                print(count_sdk_recursive(client, args.bucket, args.prefix))
                return
            _check_prerequisites("cli", recursive)
            print(count_cli_immediate(args.bucket, args.prefix))
            return

        _check_prerequisites("sdk", recursive)
        client = _build_sdk_client(args.region)
        if recursive:
            print(count_sdk_recursive(client, args.bucket, args.prefix))
        else:
            print(count_sdk_immediate(client, args.bucket, args.prefix))

    except Exception as exc:
        hint = _translate_sdk_error(exc)
        if hint:
            print(hint, file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
