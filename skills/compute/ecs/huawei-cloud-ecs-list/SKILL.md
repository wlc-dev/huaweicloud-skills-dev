---
name: huawei-cloud-ecs-list
description: |
  1. List Huawei Cloud ECS (Elastic Cloud Server) instances in a tenant region
     through KooCLI (hcloud ECS ListServersDetails — read-only GET
     /v1/{project_id}/cloudservers/detail), with an automatic fallback to the
     official huaweicloudsdkecs v2 SDK when hcloud is not installed.
  2. Output modes: full-field table (default, every returned field including
     名称/ID/状态/规格(vCPU/内存)/可用区/私网IP/公网IP), --json (raw response
     array), --names-only (compact instance-name + ID inventory), plus additive
     Markdown and plain-text TXT exports (--md-file / --output-md and
     --txt-file / --output-txt) that write Region + 查询时间 + 实例总数 + a
     multi-column inventory (名称/ID/状态/规格/vCPU/内存/可用区/私网IP/公网IP)
     to a .md / .txt file.
  3. Supports --status / --name server-side filtering (both are real
     ListServersDetails query parameters), region override, and automatic offset
     paging.
  4. Explicit error hints for empty instance lists (「当前区域无 ECS 实例」), 403 /
     insufficient IAM permission (「无权限访问 ECS，请检查 IAM 权限」), missing or
     invalid AK/SK credentials, hcloud not installed, and Markdown/TXT write
     failure (missing directory / no permission).
  5. Built-in write-intent guard: any mutating intent (create / delete / update /
     rebuild / resize / reboot / start / stop / attach / detach) or any operation
     other than ListServersDetails is rejected before execution — this skill is
     strictly read-only.
  6. Triggers include: "list ECS instances", "ECS instance list", "ECS 实例列表",
     "查询ECS实例", "云服务器列表", "ECS inventory", "list cloud servers",
     "华为云ECS列表", "把 ECS 列表导出成 md", "把 ECS 列表导出成 txt",
     "导出 ECS 实例清单".
  7. Offline unit tests (mocked hcloud subprocess) cover output modes, filters,
     paging, error scenarios, SDK fallback, the write-intent guard, and the
     Markdown + TXT reports (rendering / default name / explicit path / empty
     list / write failure).
tags: [huawei-cloud, ecs, compute, readonly, koo-cli]
---

# Huawei Cloud ECS Instance List

## Overview

Query the ECS instance list of a tenant region through KooCLI
`hcloud ECS ListServersDetails` (official read-only GET
`/v1/{project_id}/cloudservers/detail`, verified in the `huaweicloudsdkecs`
v2 client `_list_servers_details_http_info` metadata). The skill is aimed at
cloud resource inventory, daily operations patrol, and as a pre-query step for
other ECS skills that need a `server_id`.

Architecture:

```text
agent → python3 scripts/list_ecs.py → hcloud ECS ListServersDetails --cli-region=<region>
      → Huawei Cloud ECS OpenAPI (regional endpoint) → parsed JSON → table / --json / --names-only
                                                                  ↘ [--md-file] → Markdown report (.md)
                                                                  ↘ [--txt-file] → plain-text report (.txt)

(hcloud binary missing) → fallback: huaweicloudsdkecs v2 EcsClient.list_servers_details
```

Key properties:

- **Read-only by design** — the only API ever invoked is `ListServersDetails`
  (GET). A write-intent guard scans the user arguments and validates the
  operation name; mutating intents (create / delete / update / rebuild /
  resize / reboot / start / stop / attach / detach ...) are rejected with an
  explicit message before any command runs.
- **CLI first, SDK fallback** — KooCLI is the primary execution path; when the
  hcloud binary is absent, the script falls back to the official
  `huaweicloudsdkecs` v2 SDK (`list_servers_details`). Credentials are always
  read by the CLI profile / SDK environment — never handled by the script.
- **Full-field table output** — the default table renders the union of all
  fields returned by ListServersDetails, with `flavor` flattened into
  name/vcpus/ram, `addresses` split into private/public IPs, and the
  `OS-EXT-AZ:availability_zone` attribute surfaced as `availability_zone`.
- **Additive Markdown / TXT export** — `--md-file [PATH]` / `--txt-file [PATH]`
  write archival reports (Region / 查询时间 / 实例总数 + a multi-column inventory
  `名称 | ID | 状态 | 规格 | vCPU | 内存 | 可用区 | 私网IP | 公网IP`, empty
  list → `共 0 个实例`, active filters listed) *in addition to* the stdout
  output, which stays exactly as before. Both can be stacked (and stacked with
  `--json` / `--names-only`); the Markdown report is a real Markdown table, the
  TXT report is plain text with ` | ` separators and no Markdown escaping. Each
  file is written through a temporary sibling and moved into place, so a failed
  write never leaves a half file.
- **Offline-testable** — every code path (paging, filters, error
  classification, guard, SDK fallback, Markdown + TXT rendering and file write)
  is covered by unit tests that mock the hcloud subprocess.

Out of scope: every mutating ECS action (create / delete / start / stop /
restart / resize flavor / rebuild / attach-detach volume / change image /
change password). Those require a dedicated write-capable skill and explicit
user confirmation.

## Prerequisites

1. **KooCLI (`hcloud`) installed** — see
   [references/cli-installation-guide.md](references/cli-installation-guide.md).
   Alternative: `pip install huaweicloudsdkecs` to enable the SDK fallback path.
2. **Active credential profile** — configure credentials out-of-band
   (`hcloud configure` in your terminal, or credential environment variables).
   Never paste AK/SK into chat; the script never reads, echoes, or stores
   secrets itself — authentication is delegated entirely to the hcloud profile
   / SDK environment.
3. **IAM permission** — read-only `ecs:servers:list`; least-privilege policy in
   [references/iam-policies.md](references/iam-policies.md).
4. **Python 3.8+** (standard library only — argparse / json / subprocess).
5. **Outbound HTTPS** access to `*.myhuaweicloud.com`.

## Workflow

1. **Confirm the target region** (default `cn-north-4`); every ECS call is
   region-scoped.
2. **Confirm hcloud readiness** (optional, read-only): `hcloud configure list`.
3. **Run the list script** with the desired output mode and filters.
4. **Read the result** — table for humans, `--json` for downstream tooling,
   `--names-only` for a compact inventory; add `--md-file` and/or `--txt-file`
   when the result must be archived / attached to a ticket (the stdout output is
   kept unchanged and each generated file path is printed).
5. **Handle the empty / error cases** per the Error Handling table below (the
   script prints an explicit hint for empty region, 403, missing AK/SK, and
   Markdown / TXT write failure).

## Core Commands

```bash
# Full-field table (default)
python3 scripts/list_ecs.py --region cn-north-4

# Raw JSON of every returned field
python3 scripts/list_ecs.py --json

# Compact instance-name + ID inventory
python3 scripts/list_ecs.py --names-only

# Filter by instance status (server-side ECS query parameter)
python3 scripts/list_ecs.py --status ACTIVE

# Filter by instance name (server-side ECS query parameter, fuzzy)
python3 scripts/list_ecs.py --name ecs-web

# Combine filters
python3 scripts/list_ecs.py --region cn-south-1 --status ACTIVE --names-only

# Also write a Markdown report to an explicit path (stdout output unchanged)
python3 scripts/list_ecs.py --md-file /tmp/ecs-inventory.md

# Default file name ecs-list-<region>-<YYYYMMDD>.md in the current directory
python3 scripts/list_ecs.py --md-file

# Alias + stacking: raw JSON on stdout AND the Markdown report on disk
python3 scripts/list_ecs.py --output-md report.md --json

# Also write a plain-text TXT report to an explicit path (stdout output unchanged)
python3 scripts/list_ecs.py --txt-file /tmp/ecs-inventory.txt

# Default TXT file name ecs-list-<region>-<YYYYMMDD>.txt in the current directory
python3 scripts/list_ecs.py --txt-file

# Stack everything: table on stdout + Markdown + TXT on disk
python3 scripts/list_ecs.py --md-file report.md --txt-file inventory.txt
```

Equivalent direct KooCLI command (the script wraps exactly this call, with
paging):

```bash
hcloud ECS ListServersDetails --cli-region=cn-north-4 --limit=100 --offset=0
```

## Parameter Confirmation

| Parameter | Required | Description | Example |
| ----------- | ---------- | ------------- | --------- |
| `--region` / `-r` | No | Huawei Cloud region (default `cn-north-4`) | `cn-south-1` |
| `--json` | No | Output the raw server array as JSON | — |
| `--names-only` | No | Output instance-name + ID inventory | — |
| `--status` | No | Filter by instance state — **server-side** ECS ListServersDetails parameter | `ACTIVE`, `BUILD`, `ERROR`, `SHUTOFF`, `REBUILD`, `RESIZE` |
| `--name` | No | Filter by instance name (server-side, fuzzy match) | `ecs-web` |
| `--page-size` | No | Page size for ListServersDetails (default 100) | `100` |
| `--operation` | No | hcloud ECS operation name; only `ListServersDetails` is allowed | `ListServersDetails` |
| `--md-file [PATH]` / `--output-md [PATH]` | No | **Additive** Markdown report. With `PATH` → write there; without a value → `ecs-list-<region>-<YYYYMMDD>.md` in the current directory; omitted → no file is created | `/tmp/inventory.md` |
| `--txt-file [PATH]` / `--output-txt [PATH]` | No | **Additive** plain-text TXT report. With `PATH` → write there; without a value → `ecs-list-<region>-<YYYYMMDD>.txt` in the current directory; omitted → no file is created | `/tmp/inventory.txt` |

Output-mode precedence: `--names-only` → `--json` → table (default).
The Markdown and TXT exports are **not** part of that precedence: they layer on
top of whatever stdout mode is active and never change the stdout output (only
the `已生成 ... 文件：<绝对路径>` hints are appended, one per requested file).

### Markdown report layout

```markdown
# Huawei Cloud ECS 实例清单

- **Region**: cn-north-4
- **查询时间**: 2026-10-20 14:36:10 CST
- **实例总数**: 2

## 实例清单

| 实例名称 | 实例 ID | 状态 | 规格 | vCPU | 内存 | 可用区 | 私网IP | 公网IP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ecs-web-01 | ecs-0001 | ACTIVE | s6.large.2 | 2 | 4096 | cn-north-4a | 192.168.0.10 | - |
| ecs-db-02 | ecs-0002 | SHUTOFF | s6.xlarge.2 | 4 | 8192 | cn-north-4b | 192.168.0.11 | 10.0.0.5 |
```

- The report is UTF-8. `查询时间` is the local time of the query; the file name
  uses `<YYYYMMDD>` of the same moment.
- The inventory table has a fixed column order — 实例名称 / 实例 ID / 状态 /
  规格 / vCPU / 内存 / 可用区 / 私网IP / 公网IP. `flavor` is flattened into
  规格/vCPU/内存 and `addresses` into 私网IP/公网IP, exactly like the stdout
  table. A multi-value field (e.g. several private IPs) is comma-joined; a
  missing value renders as `-`.
- Empty result → `共 0 个实例`（+ the filters actually sent, e.g.
  `共 0 个实例（过滤条件: status=ACTIVE）`), exit code 0 — same as the stdout
  behaviour for an empty region.
- On success the script prints `已生成 Markdown 文件：<绝对路径>` on stdout.
- Instance names appear in the report as returned by ECS; an instance without a
  name falls back to its ID.

### TXT report layout

```text
Huawei Cloud ECS 实例清单

Region: cn-north-4
查询时间: 2026-10-20 14:36:10 CST
实例总数: 2

实例清单

实例名称 | 实例 ID | 状态 | 规格 | vCPU | 内存 | 可用区 | 私网IP | 公网IP
ecs-web-01 | ecs-0001 | ACTIVE | s6.large.2 | 2 | 4096 | cn-north-4a | 192.168.0.10 | -
ecs-db-02 | ecs-0002 | SHUTOFF | s6.xlarge.2 | 4 | 8192 | cn-north-4b | 192.168.0.11 | 10.0.0.5
```

- The TXT report mirrors the Markdown report field-for-field (same fixed column
  set and the same `flavor` / `addresses` flattening), but is **plain text**:
  columns are joined with ` | ` and there is no Markdown escaping (a literal
  `|` in a value is kept as-is; embedded newlines are folded to a space so each
  instance stays on one line). Missing values render as `-`.
- The file is UTF-8. `查询时间` is the local time of the query; the file name
  uses `<YYYYMMDD>` of the same moment.
- Empty result → `共 0 个实例`（+ the filters actually sent, e.g.
  `共 0 个实例（过滤条件: status=ACTIVE）`), exit code 0 — same as the stdout
  behaviour for an empty region.
- On success the script prints `已生成 TXT 文件：<绝对路径>` on stdout.
- `--md-file` and `--txt-file` are independent; both may be given at once (each
  writes its own file, each prints its own hint).

## Write-Intent Guard

- The script scans flag names plus the `--operation` value for mutating
  vocabulary (`create`, `delete`, `update`, `rebuild`, `resize`, `reboot`,
  `start`, `stop`, `attach`, `detach`, `server-action`, and ECS operation names
  such as `CreateServers`, `DeleteServers`, `BatchStartServers`).
- The values of read-only filter flags (`--status`, `--name`, `--region`,
  `--page-size`) and of the local output flags (`--md-file`, `--output-md`,
  `--txt-file`, `--output-txt`) are **not** scanned: they are query / file-path
  data and may legitimately contain write-looking words (e.g. the ECS status
  value `REBUILD`, an instance named `restart-me`, or a report path such as
  `ecs-delete-report.md` / `ecs-start-report.txt`).
- `--md-file` / `--txt-file` take an *optional* value, so a flag following one is
  still scanned — `--txt-file --create-server` cannot hide a mutating flag.
- Any hit raises `GuardError`, prints `[错误] 检测到写操作意图 ... 已被守卫拦截`, and
  exits with code 1 **before** a single hcloud command is executed. The guard
  runs on the raw argv *before* argparse, so a mutating flag such as
  `--create-server` is reported as a guard violation rather than an
  "unrecognized argument" error.
- Only `hcloud ECS ListServersDetails` (GET) — or the SDK `list_servers_details`
  call in the fallback path — is ever constructed by `build_command()`; there
  is no code path that can issue a mutating ECS API call.

## KooCLI Command Format Standard

```text
hcloud <Service> <Operation> --cli-region=<region> [--key=value ...]
```

- **Service name** — exact KooCLI title-case service name: `ECS`.
- **Operation name** — PascalCase: `ListServersDetails`.
- **Region parameter** — `--cli-region=<value>`, e.g. `--cli-region=cn-north-4`
  (required for every concrete ECS call).
- **Simple parameter** — `--key=value`, e.g. `--limit=100`, `--offset=20`,
  `--status=ACTIVE`, `--name=ecs-web`.
- **REST path (official SDK `_http_info`)** —
  `GET /v1/{project_id}/cloudservers/detail` (`huaweicloudsdkecs` v2
  `_list_servers_details_http_info`); project_id is resolved by KooCLI from the
  credential profile.

## Error Handling

| Scenario | Behavior |
| ---------- | --------- |
| Empty instance list | Exit 0, prints `当前区域（<x>）无 ECS 实例` (+ active filters) |
| 403 / insufficient IAM permission | Exit 1, `无权限访问 ECS，请检查 IAM 权限` hint |
| Missing / invalid AK-SK | Exit 1, explicit hint to configure hcloud credentials out-of-band (never in chat) |
| hcloud not installed | Exit 1 after SDK fallback also unavailable, hint to install KooCLI or `pip install huaweicloudsdkecs` |
| Network / API failure | Exit 1 with the hcloud stderr excerpt |
| KooCLI usage error (`[USE_ERROR] ...`, even with exit code 0) | Exit 1, explicit `hcloud 参数错误` hint pointing to `hcloud ECS ListServersDetails --help` |
| Write intent detected | Exit 1, `GuardError` message, no command executed |
| Markdown report cannot be written (missing directory / no permission / path is a directory) | Exit 1, `[错误] 无法写入 Markdown 文件 <绝对路径>: <原因>`, no half file left behind (the report is written via a temp sibling and moved into place) |
| TXT report cannot be written (missing directory / no permission / path is a directory) | Exit 1, `[错误] 无法写入 TXT 文件 <绝对路径>: <原因>`, no half file left behind (the report is written via a temp sibling and moved into place) |
| Empty instance list **with** `--md-file` / `--txt-file` | Exit 0, stdout hint unchanged; the report is still written and contains `共 0 个实例` (+ active filters) |

Exit codes: `0` success / empty region; `1` config, auth, guard, API, or Markdown-write error.

## Edge Cases

| Scenario | Handling |
| ---------- | --------- |
| `SHUTOFF` / `ERROR` instances | Reported with their state, not treated as failure |
| `--status` filter | Forwarded to the ECS server as a real query parameter (the value is database-side); a database that accepts `REBUILD`/`RESIZE` etc. is not blocked by the guard |
| Large instance count | Automatic `offset` paging (`count` aware, full-page fallback, max 100 pages) |
| Extra response fields | Table columns are built from the union of returned fields — new fields appear automatically |
| Field missing on an instance | Rendered as `-` in the table |
| Nested `flavor` / `addresses` / `image` | Flattened into name/vcpus/ram / privateIps+publicIps / image_id for the table |
| Non-JSON hcloud output | `ApiError` with the raw excerpt (first 200 chars) |
| hcloud absent, SDK installed | Transparent fallback to `huaweicloudsdkecs` list_servers_details, same output modes |
| `--md-file` / `--txt-file` without a path | Default `ecs-list-<region>-<YYYYMMDD>.md` / `.txt` in the current working directory; the absolute path is printed |
| `--md-file` / `--txt-file` path contains `delete` / `start` / `stop` ... | Not a cloud operation — the path is exempt from the write-intent guard, so `ecs-delete-report.md` / `ecs-start-report.txt` are written normally |
| `--md-file` / `--txt-file` combined with `--json` / `--names-only` | Both outputs are produced: the stdout mode is unchanged and the report is written as well |
| `--md-file` and `--txt-file` both given | Independent — each writes its own report and prints its own `已生成 ... 文件：` hint |
| Report path already exists | Overwritten atomically (temp file + rename) — no partially written file is ever observable |
| Report path parent directory missing | Not auto-created; `无法写入 Markdown 文件` / `无法写入 TXT 文件` + exit 1 (create the directory first) |
| Instance name contains a pipe character or a newline | Escaped in the Markdown table cell (`\|`, newlines folded to a space) |
| User asks to create/delete/start/stop/rebuild | Out of scope — blocked by the write-intent guard; a write-capable skill with explicit user confirmation is required |

## Testing

Offline unit tests with a mocked hcloud subprocess (no credentials, no network):

```bash
python3 -m unittest discover -s tests -v
```

Coverage: write-intent guard (read passes / create / delete / rebuild / resize /
reboot / start / stop / attach / operation whitelist / filter values not
blocked / `--md-file` and `--txt-file` path values not blocked / a flag after
`--md-file` or `--txt-file` still scanned), command construction (status and name are real server-side params),
JSON extraction, failure classification (missing AK/SK, 403, generic,
`[USE_ERROR]` with rc=0), server-side status/name forwarding, paging (count /
full-page / empty), SDK fallback (success and unavailable; request construction
matches the real `ListServersDetailsRequest` signature), SDK field remapping
(`access_i_pv4` → `accessIPv4`, `os_ext_a_zavailability_zone` →
`OS-EXT-AZ:availability_zone`), rendering (table with flavor/IP/AZ fields /
names / summary lines / fallbacks), all main() output modes including empty,
filter, and error paths, and the Markdown report: `render_markdown`
(Region / 查询时间 / 实例总数 / multi-column table with the fixed
名称·ID·状态·规格·vCPU·内存·可用区·私网IP·公网IP header / comma-joined
multi-value IPs / `-` for missing values / empty-list message / filters / pipe
and newline escaping / ID fallback), `default_markdown_name`, `format_query_time`,
`write_markdown_file` (UTF-8 round-trip, overwrite, missing directory and
unwritable target → `OutputError` with no half file and no temp sibling), and
`main()` with `--md-file` / `--output-md` (explicit path, default file name,
region-sensitive default name, alias, write words in the path, empty list,
write failure, stacking with `--json` / `--names-only`, no file without the
flag, guard still wins over the report). The TXT export is covered in parallel:
`render_txt` (Region / 查询时间 / 实例总数 / fixed 名称·ID·状态·规格·vCPU·内存·可用区·私网IP·公网IP
header / ` | ` separators / comma-joined multi-value IPs / `-` for missing
values / newline folding with literal pipes / empty-list message / filters / ID
fallback), `default_txt_name`, `write_txt_file` (UTF-8 round-trip, overwrite,
missing directory / unwritable target → `OutputError` with no half file), and
`main()` with `--txt-file` / `--output-txt` (explicit path, default file name,
region-sensitive default name, alias, write words in the path, empty list, write
failure, stacking with `--json` / `--names-only` and with `--md-file`, no file
without the flag, guard still wins over the report).

## Reference Documents

| Document | Content |
| ---------- | --------- |
| [references/iam-policies.md](references/iam-policies.md) | Least-privilege read-only IAM policy |
| [references/cli-installation-guide.md](references/cli-installation-guide.md) | KooCLI installation and credential configuration |
| [references/verification-method.md](references/verification-method.md) | How the skill and its tests were verified |
| [references/dataflow-diagram.md](references/dataflow-diagram.md) | Mermaid data flow diagram |
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | Acceptance criteria checklist |
