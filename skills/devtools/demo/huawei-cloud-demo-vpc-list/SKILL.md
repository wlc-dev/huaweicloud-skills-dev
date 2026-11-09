---
name: huawei-cloud-demo-vpc-list
description: |
  1. Demo skill：通过 KooCLI 只读查询华为云虚拟私有云（VPC）列表，用于验证
     skill 规范与安全基线（GET /v1/{project_id}/vpcs — hcloud VPC ListVpcs --cli-region=<region>）。
  2. 触发词（Triggers include）："VPC 列表"、"查询虚拟私有云"、"VPC 名称清单"、
     "VPC 网段盘点"、"list VPC"、"VPC list"、"query VPC"；需要核对 VPC 名称 /
     网段 / 状态清单，或作为其他技能预查 VPC id 的前置步骤；不承接任何写操作。
  3. 输出模式：默认表格（id / name / cidr / status / enterprise_project_id /
     created_at），--json 原始数组，--names-only 名称清单。
  4. 严格只读：写意图守卫在参数解析阶段拦截 create / delete / update /
     associate 等变更词汇，唯一可执行的 API 为 ListVpcs（GET）。
  5. 凭据由 KooCLI profile 或环境变量提供，脚本从不读取、回显或落盘 AK/SK；
     region 默认 cn-north-4，可用 --region 覆盖并支持 marker 自动翻页。
  6. 前置条件：KooCLI（hcloud）已安装并完成凭据配置，IAM 具备
     vpc:vpcs:list 只读权限，Python 3.8+（仅标准库）。
tags: [huawei-cloud, vpc, network, readonly, koo-cli]
---

# Huawei Cloud VPC List (Demo)

## Overview

Demo skill：演示一个**符合华为云 skill 规范与安全基线**的最小只读技能。它调用
唯一一个华为云 OpenAPI，用于验证 SKILL.md 结构、references 五件套、只读守卫、
凭据处理与离线单测是否齐备。

```text
agent → python3 scripts/list_vpc.py
      → hcloud VPC ListVpcs --cli-region=<region>
      → Huawei Cloud VPC OpenAPI (vpc.<region>.myhuaweicloud.com) → JSON
      → table / --json / --names-only
```

Key properties:

- **只读设计** — 唯一可构造的调用是 `hcloud VPC ListVpcs --cli-region=<region>`（GET
  `/v1/{project_id}/vpcs`）；`build_command()` 之外没有第二处调用点。
- **写意图守卫** — 参数解析前扫描 argv 中的变更词汇（create / delete / update /
  associate / release / change …），命中即退出码 1，且不执行任何命令。
- **凭据零接触** — 脚本不读取、不打印、不缓存 AK/SK；认证完全交给 KooCLI
  profile 或 `HUAWEICLOUD_SDK_AK/SK` 环境变量。
- **可离线验证** — `tests/` 用假 hcloud 可执行文件覆盖表格、JSON、名称清单、
  空列表、403、缺 CLI 与守卫拦截，不需要真实账号。

## Prerequisites

1. **KooCLI（hcloud）已安装** — 见 `references/cli-installation-guide.md`。
2. **凭据已配置（带外完成）** — 在终端执行 KooCLI configure，或设置
   `HUAWEICLOUD_SDK_AK` / `HUAWEICLOUD_SDK_SK` / `HUAWEICLOUD_SDK_REGION`。
   **不要把 AK/SK 贴进对话**，脚本本身不接触凭据值。
3. **IAM 权限** — 只读 `vpc:vpcs:list`，最小权限策略见
   `references/iam-policies.md`。
4. **Python 3.8+** — 仅使用标准库（argparse / json / subprocess / shlex）。
5. **出网** — 可访问 `vpc.<region>.myhuaweicloud.com`（443）。

## Workflow

1. 确认目标 region（默认 `cn-north-4`）。
2. 确认凭据就绪（可选，只读）：运行 KooCLI 的 `configure list` 子命令查看当前 profile。
3. 运行 `scripts/list_vpc.py`，按需选输出模式与过滤参数。
4. 读取结果：表格给人看，`--json` 给下游工具，`--names-only` 给出名称清单。
5. 空列表与错误按下方 Edge Cases 处理（脚本给出中文提示与退出码）。

## Core Commands

```bash
# 默认表格（region 默认 cn-north-4）
python3 scripts/list_vpc.py

# 指定 region
python3 scripts/list_vpc.py --region cn-south-1

# 原始 JSON（下游编排用）
python3 scripts/list_vpc.py --json

# 名称清单
python3 scripts/list_vpc.py --names-only

# 缩小分页大小（调试用）
python3 scripts/list_vpc.py --limit 10

# 离线自检：指向假 hcloud，不产生任何真实调用
python3 scripts/list_vpc.py --hcloud-bin tests/fake_hcloud.sh
```

等价的 KooCLI 命令（脚本内部只构造这一条，并自动处理 marker 翻页）：

```bash
hcloud VPC ListVpcs --cli-region=cn-north-4 --limit=100
```

## KooCLI Command Format

```text
hcloud <Service> <Operation> --cli-region=<region> [--key=value ...]
```

- Service 使用 KooCLI 服务名（本技能为 `VPC`），Operation 使用 PascalCase（`ListVpcs`）。
- 每条真实调用必须带 `--cli-region`；本技能由 `--region` 参数映射为 `--cli-region`。
- 本技能只构造 `hcloud VPC ListVpcs --cli-region=<region>` 一条命令，脚本自动处理 `--limit` 与 marker 翻页。

## Parameter Confirmation

| Parameter | Required | Description | Example |
| ----------- | ---------- | ------------- | --------- |
| `--region` / `-r` | No | 区域，默认 `cn-north-4` | `cn-south-1` |
| `--json` | No | 输出原始响应数组 | — |
| `--names-only` | No | 只输出名称清单 | — |
| `--limit` | No | 每页数量（1–2000，默认 100） | `10` |
| `--max-pages` | No | 最大翻页数（默认 20，防无限循环） | `3` |
| `--timeout` | No | 单次 hcloud 调用超时秒数（默认 30） | `20` |
| `--hcloud-bin` | No | hcloud 可执行文件路径（默认 `hcloud`，离线测试用） | `tests/fake_hcloud.sh` |

输出模式优先级：`--names-only` → `--json` → 表格（默认）。

## Read-Only Guard

- 扫描除 `--region` / `--hcloud-bin` / `--limit` / `--max-pages` / `--timeout`
  值以外的全部 argv，命中 `create` / `delete` / `update` / `modify` /
  `associate` / `disassociate` / `attach` / `detach` / `bind` / `unbind` /
  `release` / `change` / `restart` 等变更词汇即拦截。
- 命中时打印 `[错误] 检测到写操作意图 ... 已被守卫拦截`，退出码 1，
  **在任何 hcloud 调用之前**结束。
- 模式开关（`--json` / `--names-only`）与数值参数不参与关键词判定，避免误拦；
  其余个位置参数一律按参数错误处理（退出码 1），不做透传。
- 只有 `build_command()` 能拼出 `hcloud VPC ListVpcs --cli-region=<region>`，代码中不存在可发出
  写请求的路径。

## Verification

```bash
# 1) 离线单测（无需凭据/网络）
cd skills/devtools/demo/huawei-cloud-demo-vpc-list
python3 -m unittest discover -s tests -v

# 2) 真实只读查询（需已配置凭据）
python3 scripts/list_vpc.py --region cn-north-4 --limit 10

# 3) 守卫自检：应报错且不发出任何请求
python3 scripts/list_vpc.py --region cn-north-4 delete
# [错误] 检测到写操作意图 ... 退出码 1
```

验收口径见 `references/acceptance-criteria.md`，成功/失败判定见
`references/verification-method.md`。

## Error Handling

| Scenario | Behavior |
| ---------- | --------- |
| 空列表 | 退出码 0，打印 `当前区域（<region>）无虚拟私有云（VPC）` |
| 403 / IAM 权限不足 | 退出码 1，提示检查 `vpc:vpcs:list` 权限 |
| 缺凭据 / 凭据无效 | 退出码 1，提示带外配置 KooCLI profile（勿在对话里传 AK/SK） |
| hcloud 未安装 | 退出码 1，提示安装 KooCLI（见 cli-installation-guide.md） |
| 网络 / API 失败 | 退出码 1，附 hcloud stderr 前 200 字符 |
| KooCLI 参数错误（`[USE_ERROR]`，即便 rc=0） | 退出码 1，提示核对操作参数 |
| 输出非 JSON | 退出码 1，附原始输出片段 |
| 写意图命中 | 退出码 1，守卫消息，无任何调用 |

退出码：`0` 成功 / 空列表；`1` 配置、鉴权、守卫或 API 错误。

## Edge Cases

| Scenario | Handling |
| ---------- | --------- |
| 非 `OK` 状态的 VPC | 原样展示状态（`CREATING`、`DOWN` 等），不视为失败 |
| 超过一页 | 依据响应 `page_info.next_marker` 自动翻页，到 `--max-pages` 停止 |
| 返回字段缺失 | 表格单元格渲染 `-` |
| 名称含空格 / 竖线 | 表格按列宽对齐，竖线在单元格内不转义（纯文本表格） |
| hcloud 输出混有 warning 前缀 | 从首个 `{` 到最后一个 `}` 提取 JSON |
| 用户要求创建 / 删除 VPC | 超出范围，被守卫拦截；需要写能力技能与显式确认 |

## Security Notes

- **不硬编码任何 AK/SK、token、endpoint 凭据**；示例中账号信息一律用
  `{region}` / `{project_id}` 占位符。
- 脚本只构造只读 GET 请求；不写本地文件、不改云端状态、无副作用。
- 错误信息只截取 stderr 前 200 字符，不回显环境变量值。
- 本技能不涉及计费操作，无需 `## Cost Confirmation`；若后续扩展写操作，
  必须补成本确认与显式用户确认（规范 §9.3）。

## Reference Documents

| Document | Content |
| ---------- | --------- |
| [references/dataflow-diagram.md](references/dataflow-diagram.md) | Mermaid 数据流图、图例与数据流说明表 |
| [references/cli-installation-guide.md](references/cli-installation-guide.md) | KooCLI 安装、凭据配置、区域设置 |
| [references/iam-policies.md](references/iam-policies.md) | 只读最小权限策略（vpc:vpcs:list） |
| [references/verification-method.md](references/verification-method.md) | 成功/失败判定方法与验证记录 |
| [references/acceptance-criteria.md](references/acceptance-criteria.md) | 验收清单 |
| [i18n/zh-CN/SKILL_CN.md](i18n/zh-CN/SKILL_CN.md) | 中文版 SKILL.md |