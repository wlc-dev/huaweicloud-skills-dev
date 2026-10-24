# IAM Policies (least privilege, read-only)

The skill invokes exactly one Huawei Cloud OpenAPI (both execution paths):

- KooCLI: `GET /api/v3/projects/{project_id}/clusters` — `hcloud CCE ListClusters`
- SDK fallback: `huaweicloudsdkcce` v3 `CceClient.list_clusters` (same REST path)

## Required IAM action

| Action | Access level | API | Purpose |
| -------- | -------- | ----- | ------- |
| `cce:cluster:list` | list | GET /api/v3/projects/{project_id}/clusters | Query the cluster list |

Verify the exact action name through the official IAM authorization schema
(query the CCE service code):

```bash
hcloud IAM GetAuthorizationSchemaV5 --cli-region=cn-north-4 --service_code=cce
```

Also check the Huawei Cloud 《云容器引擎(CCE) 权限及授权项说明》 document and
confirm the standard `service:resource_type:action` naming
(`cce:cluster:list`).

If you prefer a system policy, assign **CCE ReadOnlyAccess** instead of the
custom policy below.

## Custom least-privilege policy (IAM 5.0)

```json
{
  "Version": "5.0",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cce:cluster:list"
      ],
      "Resource": "*"
    }
  ]
}
```

## 403 troubleshooting

If the script reports `无权限访问云容器引擎（CCE），请检查 IAM 权限（403）`:

1. Confirm the AK/SK belongs to a user / agency in the target project.
2. Grant `cce:cluster:list` (custom policy above) or the `CCE ReadOnlyAccess`
   system policy.
3. Re-run `python3 scripts/list_cce.py`.