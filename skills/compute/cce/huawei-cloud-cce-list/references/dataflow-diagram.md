# Data Flow Diagram

```mermaid
flowchart TD
    A[User / Agent] -->|"python3 scripts/list_cce.py<br/>--region --json --names-only<br/>--name --id"| B[Write-Intent Guard]
    B -->|"create/delete/update/upgrade/resize/hibernate<br/>or operation != ListClusters"| G[GuardError: 拦截写意图<br/>exit 1, 未执行任何命令]
    B -->|read-only| C[build_command:<br/>hcloud CCE ListClusters<br/>--cli-region]
    C --> D[subprocess.run hcloud]
    D -->|FileNotFoundError| F1{SDK fallback:<br/>huaweicloudsdkcce<br/>list_clusters}
    F1 -->|SDK unavailable| E1[ConfigError: 安装 KooCLI 或 SDK]
    F1 -->|items| F
    D -->|"exit != 0"| E2{classify failure}
    E2 -->|"cli-ak / credential"| E3[ConfigError: 缺少 AK/SK]
    E2 -->|"401 / 403 / Forbidden"| E4[AuthError: 无权限访问云容器引擎（CCE），请检查 IAM 权限]
    E2 -->|"other"| E5[ApiError]
    D -->|"[USE_ERROR] ... (exit 0)"| E6[ApiError: hcloud 参数错误<br/>指向 --help]
    D -->|JSON stdout| F2[extract_json / extract_clusters]
    F2 -->|"items empty"| H["当前区域（x）无云容器引擎（CCE）集群<br/>exit 0"]
    F2 -->|items| F[filter_clusters:<br/>client-side name/id]
    F -->|--names-only| J[集群名称清单]
    F -->|--json| K[原始 JSON 数组]
    F -->|default| L[完整字段表格<br/>名称/UID/别名/状态/类型/规格/版本/类别/计费模式]
```