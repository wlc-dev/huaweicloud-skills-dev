# Verification Method

## Offline unit tests (primary, CI-safe)

```bash
cd skills/network/vpc/huawei-cloud-vpc-list
python3 -m unittest discover -s tests -v
```

- hcloud is replaced by a `subprocess.run` mock (`FakeRunner`) — no credentials,
  no network, deterministic.
- The SDK fallback is tested via a `list_vpcs_via_sdk` mock (no real SDK
  import, no network), plus live regression tests that construct the real
  `ListVpcsRequest` and `VpcRegion` when `huaweicloudsdkvpc` is installed
  (skipped otherwise).
- Cases cover: write-intent guard, command construction (filters forwarded
  server-side), JSON extraction, failure classification (missing AK/SK / 403 /
  generic / `[USE_ERROR]` with rc=0), marker paging (next_marker / full page /
  empty), SDK fallback (success / missing credentials / missing project id /
  unavailable), rendering, and all main() output modes.

## Live verification (when credentials exist)

```bash
hcloud configure list                                            # profile check
hcloud VPC ListVpcs --cli-region=cn-north-4 --limit=1            # API sanity
python3 scripts/list_vpc.py --region cn-north-4                  # full flow
python3 scripts/list_vpc.py --json | python3 -m json.tool >/dev/null  # JSON validity
python3 scripts/list_vpc.py --names-only
python3 scripts/list_vpc.py --id <vpc-id>                        # server-side filter
python3 scripts/list_vpc.py --enterprise-project-id 0
```

## API / parameter provenance

Verified against the installed official SDK `huaweicloudsdkvpc`, no endpoint or
parameter was inferred from naming patterns:

- `huaweicloudsdkvpc` v2 `vpc_client._list_vpcs_http_info` declares
  `method = GET`, `resource_path = /v1/{project_id}/vpcs`.
- `ListVpcsRequest` real query parameters are exactly: `limit` (int), `marker`
  (str), `id` (str), `enterprise_project_id` (str). `limit` range 0–2000;
  `marker` is the resource id from which paging starts (empty = first page);
  `enterprise_project_id` accepts `0` (default enterprise project) or
  `all_granted_eps`.
- The response object is `ListVpcsResponse` with the `vpcs` list of `Vpc`
  objects; KooCLI prints the response `page_info.next_marker` for paging. The
  typed SDK response does not surface `page_info`, so the SDK fallback
  continues from the last returned VPC id when a full page is returned.
- `Vpc` fields: `id`, `name`, `cidr`, `description`, `routes`, `status`
  (`CREATING` / `OK`), `enterprise_project_id`, `tenant_id`, `created_at`,
  `updated_at`, `block_service_endpoint_states`,
  `enable_network_address_usage_metrics`.
- Region catalog `huaweicloudsdkvpc.v2.region.vpc_region.VpcRegion` maps
  `cn-north-4 → https://vpc.cn-north-4.myhuaweicloud.com`.
- IAM action `vpc:vpcs:list` (VPC service, `vpcs` resource) is the
  least-privilege read-only permission for this call.

## Environment note

If the development environment does not have the `hcloud` binary installed, the
KooCLI path cannot be executed live; its command/parameter shape is derived from
the official SDK request model and the KooCLI
`hcloud <Service> <Operation> --cli-region=<region>` format standard. The SDK
fallback path is import-verified against the installed `huaweicloudsdkvpc`.