# IAM Policies (least privilege, read-only)

The skill invokes exactly three Huawei Cloud OpenAPI operations:

- `GET /v1.0/{project_id}/clusters` — `hcloud CSS ListClustersDetails`
- `GET /v1.0/{project_id}/clusters/{cluster_id}` — `hcloud CSS ShowClusterDetail`
- `GET /v1.0/{project_id}/clusters/{cluster_id}/volume` — `hcloud CSS ShowClusterVolumeUsage`

## Required IAM actions

| Action | API | Purpose |
| -------- | ----- | ------- |
| `css:cluster:list` | GET /v1.0/{project_id}/clusters | List CSS clusters |
| `css:cluster:get` | GET /v1.0/{project_id}/clusters/{cluster_id} | Read cluster detail and per-node disk usage |

Both are read-only actions from the official CSS API permission table (the
`css:cluster:list` / `css:cluster:get` names are also the ones the API returns in
its 403 diagnostics, for example `CSS.0051 : ... does not allow the
css:cluster:list operation`). If you prefer a system policy, assign
**CSS ReadOnlyAccess** instead of the custom policy below.

## Custom least-privilege policy (IAM 5.0)

```json
{
  "Version": "5.0",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "css:cluster:list",
        "css:cluster:get"
      ],
      "Resource": "*"
    }
  ]
}
```

## 403 troubleshooting

If the script reports `无权限访问云搜索服务（CSS）` or `CSS.0051`:

1. Confirm the AK/SK belongs to a user / agency in the target region's project.
2. Grant `css:cluster:list` and `css:cluster:get` (custom policy above) or the
   `CSS ReadOnlyAccess` system policy.
3. Confirm the region argument matches the region where the clusters live.
4. Re-run `python3 scripts/list_css_clusters.py --region <region>`.

Note: disk-usage enrichment is best-effort. If `css:cluster:get` is missing while
`css:cluster:list` is granted, the cluster list still renders and usage columns
show `-` with a stderr hint.