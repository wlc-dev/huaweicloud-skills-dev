---
name: huawei-cloud-obs-dir-count
description: |
  Counts the number of directories (folders) inside a Huawei Cloud OBS
  (Object Storage Service) bucket and returns ONLY the numeric count. Supports
  counting the immediate subdirectories under the bucket (or a given prefix)
  as well as all nested directories recursively. Uses the KooCLI obsutil-backed
  `hcloud OBS ls -d` command (primary) or the huaweicloudsdkobs Python SDK
  (fallback). Read-only — never creates, modifies or deletes any resource.
  Use this skill whenever the user wants to know how many directories/folders an
  OBS bucket contains, e.g. for inventory, capacity review or structure checks.
  Triggers include: "count OBS directories", "OBS directory count", "number of
  directories in bucket", "OBS folder count", "how many folders in bucket",
  "OBS目录数量", "查询OBS目录数量", "OBS目录数", "桶目录数量", "目录数量",
  "文件夹数量", "统计目录", "目录统计".
tags:
  - huawei-cloud
  - obs
  - directory
  - count
  - query
  - inventory
---

# Huawei Cloud OBS Directory Count Skill

## Overview

This skill counts the number of directories (folders) in a Huawei Cloud OBS bucket and returns **only the count** (a single integer). It is a read-only statistics skill: it never creates, modifies, or deletes buckets, directories, or objects.

**Architecture:**

```
Agent → hcloud CLI (KooCLI OBS / obsutil, primary) → Huawei Cloud OBS API
       ↘ huaweicloudsdkobs Python SDK (fallback)            ↗
```

**Two counting modes:**

| Mode | Description | Example |
|------|-------------|---------|
| Immediate (default) | Number of subdirectories directly under the bucket (or a given prefix) | `obs://bucket/` → 11 |
| Recursive (`--recursive`) | Total number of directories at all nesting levels | all directories in the bucket → 203 |

**Applicable Scenarios:**

- Inventory: "how many directories does this bucket have?"
- Structure review: verify a bucket layout matches expectations
- Capacity/storage planning: estimate directory-level layout before migration
- Compliance auditing: detect unexpected directories

> **能力边界（Capability Boundary）：**
> 本 Skill **仅统计目录（文件夹 / common prefixes）数量**，**不统计文件或对象（objects/files）数量**。
> 若用户询问"桶里有多少个文件/对象"、总存储量或对象总大小，请明确告知本 Skill 不提供该能力，
> 并引导使用其他 OBS 技能或华为云控制台 OBS 监控页。

## Prerequisites

1. **hcloud CLI** (KooCLI) installed and authenticated — See `references/cli-installation-guide.md`
2. **obsutil** installed — required by the `hcloud OBS ls` command (bundled with KooCLI or standalone)
3. **OBS credentials configured for obsutil** — `hcloud OBS ls` reads AK/SK/endpoint from the obsutil config file
   (`.obsutilconfig` in the user home directory), which is **separate** from the KooCLI account credentials
4. **Python 3.8+** with `huaweicloudsdkobs` package (SDK fallback) — `pip install huaweicloudsdkobs`
5. **IAM permissions** — `obs:bucket:ListBucket`, `obs:object:List` — See `references/iam-policies.md`

> **OBS credentials are separate.** Before running, check whether obsutil credentials are configured:
>
> ```bash
> hcloud OBS ls -s -limit=1
> ```
>
> If the output is `Please set ak, sk and endpoint in the configuration file!` or an `InvalidAccessKeyId` error,
> obsutil credentials are not configured. Ask the user to configure them in their own terminal (never ask the user
> to paste AK/SK into the conversation). Provide the following example command:
>
> ```
> hcloud obs config -i=<YourAK> -k=<YourSK> -e=obs.<Region>.myhuaweicloud.com
> ```
>
> Example (cn-north-4): `hcloud obs config -i=<YourAK> -k=<YourSK> -e=obs.cn-north-4.myhuaweicloud.com`

## Workflow

1. **Confirm the bucket name** — ask the user which OBS bucket to inspect (and optionally a subdirectory prefix)
2. **Verify prerequisites** — `hcloud version`, `hcloud OBS ls -s -limit=1` to confirm obsutil credentials
3. **Run the count** — use the script `scripts/count_obs_directories.py` (primary) with the appropriate flags
4. **Return the count** — the script prints a single integer; relay that integer to the user
5. **Handle errors** — if the script fails (e.g. bucket not found, invalid AK/SK, missing credentials), the script
   prints a clear Chinese error hint on stderr with configuration guidance; relay that hint to the user

## Core Commands

### Count Immediate Subdirectories (Primary)

Returns the number of subdirectories directly under the bucket:

```bash
python3 scripts/count_obs_directories.py --bucket <bucket_name>
```

### Count Subdirectories Under a Prefix

Counts the subdirectories directly under a given directory prefix:

```bash
python3 scripts/count_obs_directories.py --bucket <bucket_name> --prefix <prefix>
```

### Count All Directories Recursively

Counts every directory at every nesting level under the bucket (or prefix):

```bash
python3 scripts/count_obs_directories.py --bucket <bucket_name> --recursive
```

### Force SDK Executor

If the CLI/obsutil path is unavailable, force the Python SDK:

```bash
python3 scripts/count_obs_directories.py --bucket <bucket_name> --executor sdk
```

### Direct CLI Command (for reference)

The underlying obsutil command the script uses for immediate counts is `hcloud OBS ls obs://<bucket_name>/ -d`.
The `Folder number: N` line at the end of the output is the immediate directory count. Prefer the
script commands above; use the raw obsutil command only for manual inspection.

## Parameter Confirmation

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `--bucket` | Yes | OBS bucket name | `my-bucket` |
| `--prefix` | No | Directory prefix to count under | `photos` |
| `--recursive` | No | Count all nested directories (all levels) | `--recursive` |
| `--region` | No | Huawei Cloud region (SDK fallback only) | `cn-north-4` |
| `--executor` | No | `auto` (default), `cli`, or `sdk` | `--executor sdk` |

## Reference Documents

- [CLI Installation Guide](references/cli-installation-guide.md)
- [IAM Policies](references/iam-policies.md)
- [Verification Method](references/verification-method.md)
- [Data Flow Diagram](references/dataflow-diagram.md)
- [Acceptance Criteria](references/acceptance-criteria.md)

## KooCLI Command Format Standard

The `hcloud OBS` module is backed by obsutil. The `-d` flag lists only directories (common prefixes) at the requested level:

| Feature | Description | Example |
|---------|-------------|---------|
| Service name | `OBS` (obsutil-backed) | `hcloud OBS ls` |
| Operation name | Lowercase obsutil command | `ls` |
| List directories only | `-d` flag limits output to common prefixes (directories) | `hcloud OBS ls obs://bucket/ -d` |
| Simple parameter | `-flag` / `-key=value` for obsutil options | `hcloud OBS ls -limit=100` |
| Credentials | obsutil config file (`.obsutilconfig`) | `-i=AK -k=SK -e=endpoint` |
