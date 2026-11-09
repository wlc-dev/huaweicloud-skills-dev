# Permission Policies — Huawei Cloud VPC (read-only)

读取时机：为账号 / 委托管理员配置最小权限时阅读本文件。

本技能只发起一个只读请求：

- `hcloud VPC ListVpcs` — `GET /v1/{project_id}/vpcs`

## Query Operations

| API Action | Access level | REST API | Purpose |
| ---------- | ---------- | ---------- | --------- |
| `vpc:vpcs:list` | list | `GET /v1/{project_id}/vpcs` | 查询 VPC 列表（技能唯一调用） |

## Mutation Operations

本技能**不具备**任何变更能力（写意图在参数解析前即被拦截），因此不申请变更类
权限。若需创建/删除 VPC，请使用具备写能力的独立技能，并遵守规范 §9.3 的成本
确认与显式用户确认流程。

| API Action | Access level | Purpose |
| ---------- | ---------- | --------- |
| 无 | — | 技能不发起写操作 |

## Minimum Privilege Policy JSON

```json
{
  "Version": "1.1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "vpc:vpcs:list"
      ],
      "Resource": ["*"]
    }
  ]
}
```

## Notes

- 系统策略等价物：**VPC ReadOnlyAccess**（粒度过宽，建议优先使用上面的自定义策略）。
- 不需要 MFA / 高危授权；所有调用均为只读 GET。
- 凭据由 KooCLI profile 或环境变量提供，技能代码不读取 AK/SK 值。