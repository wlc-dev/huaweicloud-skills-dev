# Data Flow Diagram

```mermaid
flowchart TD
    A[User / Agent] -->|"python3 scripts/list_css_clusters.py<br/>--region --table --json<br/>--name --fuzzy --status --datastore-type<br/>--cluster-id"| B[Write-Intent Guard]
    B -->|"create/delete/restart/reboot/update/scale/shrink/snapshot<br/>or operation/action not read-only"| G[GuardError: 拦截写意图<br/>exit 1, 未执行任何命令]
    B -->|read-only| C{cluster-id given?}
    C -->|no| D1[build_list_command:<br/>hcloud CSS ListClustersDetails<br/>--cli-region --limit --offset<br/>+ --datastoreType]
    C -->|yes| D2[build_detail_command / build_volume_command:<br/>hcloud CSS ShowClusterDetail / ShowClusterVolumeUsage<br/>--cli-region --cluster_id]
    D1 --> E[subprocess.run hcloud]
    D2 --> E
    E -->|FileNotFoundError| F1[SDK fallback:<br/>huaweicloudsdkcss v1 CssClient]
    E -->|exit != 0| F2{classify failure}
    E -->|CSS error envelope on stdout, rc=0| F2
    F2 -->|"cli-ak / credential"| F3[ConfigError: 缺少 AK/SK]
    F2 -->|"401 / 403 / CSS.0051 / Forbidden"| F4[AuthError: 认证或权限不足]
    F2 -->|[USE_ERROR]| F5[ApiError: 参数错误提示]
    F2 -->|other| F6[ApiError]
    F1 -->|no SDK / no credentials| F3
    D1 --> H1[extract_clusters / extract_total]
    H1 -->|"batch empty or collected >= totalSize"| I[filter_clusters:<br/>--name --fuzzy --status]
    H1 -->|"len(batch) == limit"| D1
    I -->|empty| J["Region x 下暂无 CSS 集群<br/>exit 0"]
    I -->|"--json"| K[原始 JSON 数组]
    I -->|"--table"| L1[per-cluster ShowClusterVolumeUsage<br/>best-effort; 403 degrades to '-']
    L1 --> L2[cluster view:<br/>normal table + ⚠异常状态集群 + ⚠容量≥80%]
    I -->|default| L3[compact list:<br/>name / id / status + ⚠异常分区]
    D2 --> M1[detail = ShowClusterDetail]
    M1 --> M2[diskInfoList = ShowClusterVolumeUsage]
    M2 --> M3[node view:<br/>normal table + ⚠异常节点 + ⚠磁盘≥80%]
```

All API calls are `GET`. No write request is ever constructed; the only failure
modes are explicit errors with actionable hints.