---
name: huawei-cloud-demo-vpc-list
description: |
  演示技能：通过 KooCLI 只读查询华为云虚拟私有云（VPC）列表，用于验证 skill
  规范与安全基线。
  触发场景包括：VPC 列表、查询虚拟私有云、VPC 名称清单、网段盘点、VPC 清单导出前预查。
  输出模式：表格（默认）/ JSON / 名称清单；严格只读，凭据由 KooCLI profile 提供。
tags: [huawei-cloud, vpc, network, readonly, koo-cli]
---

# 华为云 VPC 列表查询（演示技能）

## 概述

本技能演示一个**符合华为云 skill 规范与安全基线**的最小只读技能：只调用一个
只读 OpenAPI（`GET /v1/{project_id}/vpcs`），用于验证目录结构、SKILL.md 结构、
references 五件套、只读守卫、凭据处理与离线单测是否齐备。

```text
智能体 → python3 scripts/list_vpc.py
      → hcloud VPC ListVpcs --cli-region=<region>
      → 华为云 VPC OpenAPI → JSON
      → 表格 / --json / --names-only
```

关键特性：

- **只读设计**：唯一可构造的调用是 `hcloud VPC ListVpcs --cli-region=<region>`（GET）；代码中不存在
  可发出写请求的路径。
- **写意图守卫**：参数解析前扫描变更类词汇（create / delete / update /
  associate / release / change 等），命中即退出码 1，且不执行任何命令。
- **凭据零接触**：脚本不读取、不打印、不落盘 AK/SK，认证交给 KooCLI profile 或
  `HUAWEICLOUD_SDK_AK/SK` 环境变量。
- **可离线验证**：`tests/` 用假 hcloud 替身覆盖输出模式、翻页、错误与守卫。

## 前置条件

1. 已安装 KooCLI（`hcloud`），见 `references/cli-installation-guide.md`。
2. 凭据已带外配置（`hcloud configure init` 或环境变量），**不要把 AK/SK 贴进对话**。
3. IAM 具备只读权限 `vpc:vpcs:list`，见 `references/iam-policies.md`。
4. Python 3.8+（仅标准库）。
5. 可访问 `vpc.<region>.myhuaweicloud.com`（443）。

## 工作流

1. 确认区域（默认 `cn-north-4`）。
2. 可选：`hcloud configure list` 做只读凭据自检。
3. 运行 `scripts/list_vpc.py`，选择输出模式与参数。
4. 读取结果；空列表与错误按 Edge Cases 处理。
5. 需要追溯时参考 `references/verification-method.md`。

## 核心命令

```bash
python3 scripts/list_vpc.py                      # 默认表格
python3 scripts/list_vpc.py --region cn-south-1  # 指定区域
python3 scripts/list_vpc.py --json               # 原始 JSON
python3 scripts/list_vpc.py --names-only         # 名称清单
python3 scripts/list_vpc.py --limit 10           # 缩小分页
```

等价 KooCLI 命令（脚本内部仅构造这一条）：

```bash
hcloud VPC ListVpcs --cli-region=cn-north-4 --limit=100
```

## 参数说明

| 参数 | 必填 | 说明 | 示例 |
| ---------- | ---------- | ---------- | --------- |
| `--region` / `-r` | 否 | 区域，默认 `cn-north-4` | `cn-south-1` |
| `--json` | 否 | 输出原始响应数组 | — |
| `--names-only` | 否 | 只输出名称清单 | — |
| `--limit` | 否 | 每页数量（1–2000，默认 100） | `10` |
| `--max-pages` | 否 | 最大翻页数（默认 20） | `3` |
| `--timeout` | 否 | 单次调用超时秒数（默认 30） | `20` |
| `--hcloud-bin` | 否 | hcloud 路径（离线测试用） | `tests/fake_hcloud.sh` |

## 只读守卫

命中变更词汇即拦截：打印「检测到写操作意图，已被守卫拦截」，退出码 1，不发出
任何调用。模式开关与数值参数不参与关键词判定；裸位置参数一律按错误处理，禁止
把 hcloud 子命令透传进来。

## 错误处理

| 场景 | 行为 |
| ---------- | --------- |
| 空列表 | 退出码 0，提示当前区域无 VPC |
| 403 / 权限不足 | 退出码 1，提示检查 `vpc:vpcs:list` |
| 缺凭据 / 凭据失效 | 退出码 1，提示带外配置 profile |
| hcloud 未安装 | 退出码 1，提示安装 KooCLI |
| 网络 / API 失败 | 退出码 1，附 stderr 前 200 字符 |
| `[USE_ERROR]` | 退出码 1，提示核对参数 |
| 写意图命中 | 退出码 1，守卫消息，无调用 |

## 安全说明

- 不硬编码任何 AK/SK、token；示例使用 `{region}` / `{project_id}` 占位符。
- 仅构造只读 GET 请求，不写本地文件、不改云端状态。
- 错误信息不回显环境变量值。
- 本技能不涉及计费操作；后续若扩展写操作，必须补成本确认与显式用户确认。

## 参考文档

| 文档 | 内容 |
| ---------- | --------- |
| `references/dataflow-diagram.md` | 数据流图与图例 |
| `references/cli-installation-guide.md` | KooCLI 安装与凭据配置 |
| `references/iam-policies.md` | 只读最小权限策略 |
| `references/verification-method.md` | 验证方法与记录 |
| `references/acceptance-criteria.md` | 验收清单 |