# Data Flow Diagram — huawei-cloud-demo-vpc-list

读取时机：需要理解技能内部数据流向（参数 → KooCLI → 输出）时阅读本图。

```mermaid
flowchart TD
  INPUT([/"用户: 查询 VPC 列表"/]) --> GUARD["Step 1: 写意图守卫<br/>扫描 argv"]
  GUARD -->|命中变更词汇| BLOCK(["返回: 错误 / 退出码 1"])
  GUARD -->|只读参数| PARSE["Step 2: 参数解析<br/>region / limit / 模式"]
  PARSE --> CRED["Step 3: 凭据就绪<br/>（KooCLI profile 或 env）"]
  CRED --> CALL["Step 4: hcloud VPC ListVpcs<br/>--cli-region / --limit / --marker"]
  CALL --> PARSEJSON["Step 5: JSON 提取与错误分类"]
  PARSEJSON -->|page_info.next_marker| CALL
  PARSEJSON --> RENDER["Step 6: 渲染输出"]
  RENDER --> OUTPUT([/"表格 / JSON / 名称清单"/])

  subgraph CLI["CLI Operations"]
    CLI1["hcloud VPC ListVpcs"]
    CLI2["hcloud configure list（只读自检，可选）"]
  end

  subgraph DATA["Data Sources"]
    ENV[/"环境变量：HUAWEICLOUD_SDK_AK / SK / REGION"/]
    REFS["references/：IAM 策略、安装指南"]
    SCRIPT["scripts/list_vpc.py"]
  end

  ENV -.-> CRED
  REFS -.-> PARSE
  SCRIPT -.-> GUARD
  CALL --- CLI1
  CLI2 -.-> CRED
```

## Legend

| Symbol | Meaning |
| ---------- | --------- |
| `([/ ... /])` | 起点 / 终点（用户输入与最终输出） |
| `[ ... ]` | 处理步骤 |
| `[/ ... /]` | 环境变量等数据源 |
| `-->` | 主数据流 |
| `-.->` | 参考 / 查找类数据流 |
| subgraph | 命令或数据来源分组 |

## Data Flow Description

| Step | Input | Process | Output |
| ---------- | --------- | --------- | --------- |
| 1 | 用户命令行参数 | 写意图守卫扫描，命中即拦截 | 拦截消息（退出码 1）或放行 |
| 2 | 只读参数 | argparse 解析 region / limit / 输出模式 | 调用参数集 |
| 3 | KooCLI profile / 环境变量 | 由 hcloud 自身完成鉴权（脚本不接触凭据） | 已认证的 CLI 上下文 |
| 4 | 调用参数集 | 构造并执行 `hcloud VPC ListVpcs` | 原始 JSON（stdout） |
| 5 | 原始输出 | 截取 JSON、分类错误、读取 `page_info.next_marker` | VPC 数组 + 翻页标记 |
| 6 | VPC 数组 | 表格 / JSON / 名称清单渲染 | 终端输出（无文件写入） |