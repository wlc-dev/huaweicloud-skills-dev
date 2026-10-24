# Verification Method

## Offline unit tests (primary, CI-safe)

```bash
cd skills/compute/cce/huawei-cloud-cce-list
python3 -m unittest discover -s tests -v
```

- hcloud is replaced by a `subprocess.run` mock (`FakeRunner`) — no credentials,
  no network, deterministic.
- The SDK fallback is tested via a `list_clusters_via_sdk` mock (no real SDK
  import, no network), plus live regression tests that exercise the real
  `huaweicloudsdkcce` package when installed: imports resolve, the
  `ListClustersRequest` signature matches what the fallback sends, and
  credentials + project id are wired from environment variables.
- Cases cover: write-intent guard (read passes / create / delete / upgrade /
  resize / hibernate / normalized variants / operation whitelist), command
  construction, JSON extraction, failure classification (missing AK/SK / 403 /
  generic / `[USE_ERROR]` with rc=0), client-side name/id filtering, SDK
  fallback (success / unavailable), rendering, and all main() output modes.

## Live verification (when credentials exist)

```bash
hcloud configure list                                          # profile check
hcloud CCE ListClusters --cli-region=cn-north-4                # API sanity
python3 scripts/list_cce.py --region cn-north-4                # full flow
python3 scripts/list_cce.py --json | python3 -m json.tool >/dev/null  # JSON validity
python3 scripts/list_cce.py --names-only
python3 scripts/list_cce.py --name <substring>                 # client-side filter
python3 scripts/list_cce.py --id <uid>                         # client-side filter
```

## API / parameter provenance

Verified against the installed official SDK `huaweicloudsdkcce`, no endpoint or
parameter was inferred from naming patterns:

- `huaweicloudsdkcce` v3 `cce_client._list_clusters_http_info` declares
  `method = GET`, `resource_path = /api/v3/projects/{project_id}/clusters`,
  `response_type = ListClustersResponse`.
- `ListClustersRequest` real query parameters: `detail`, `status`, `type`,
  `version` — there is **no** name/id query parameter and **no** paging
  (limit/marker) parameter, so `--name` / `--id` are applied client-side by the
  script and the full list is returned in one call.
- Response shape: `ListClustersResponse(kind, api_version, items)` — a
  Kubernetes-style list `{"kind": "List", "apiVersion": "v3", "items": [...]}`.
- `Cluster(kind, api_version, metadata, spec, status)`:
  - `metadata` (ClusterMetadata): `name`, `uid`, `alias`, `annotations`,
    `labels`, `creation_timestamp`, `update_timestamp`, `timezone`.
  - `spec` (ClusterSpec): `category`, `type`, `flavor`, `version`,
    `billing_mode`, `description`, among others.
  - `status` (ClusterStatus): `phase`, `reason`, `endpoints`, `is_locked`,
    `conditions`, among others.
- Region catalog `huaweicloudsdkcce.v3.region.cce_region.CceRegion` maps each
  region to `https://cce.<region>.myhuaweicloud.com`.
- IAM action `cce:cluster:list` (service code `cce`) — confirm through
  `hcloud IAM GetAuthorizationSchemaV5 --cli-region=cn-north-4 --service_code=cce`
  and the official 《CCE 权限及授权项说明》 document.

## Environment note

The development environment did not have the `hcloud` binary installed, so the
KooCLI path could not be executed live; its command/parameter shape is derived
from the official SDK request model and the KooCLI
`hcloud <Service> <Operation> --cli-region=<region>` format standard. The SDK
fallback path was import-verified against the installed `huaweicloudsdkcce`.