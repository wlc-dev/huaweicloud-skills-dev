# Verification Method

## Offline unit tests (primary, CI-safe)

```bash
cd skills/bigdata/css/huawei-cloud-css-cluster-list
python3 -m unittest discover -s tests -v
```

- hcloud is replaced by a `subprocess.run` mock (`FakeRunner`) — no credentials,
  no network, deterministic.
- The SDK fallback is exercised with a fake `huaweicloudsdkcss.v1` module
  injected into `sys.modules` (a `FakeClient` returning `FakeResponse` objects) —
  it does not depend on the real SDK being installed.
- 85 cases cover: write-intent guard (read passes / create / delete / restart /
  reboot / scale / shrink / snapshot / separator-normalized variants / operation
  and action whitelists / `--status creating` allowed / `--name create-me`
  blocked), command construction, limit clamping, JSON extraction, CSS error
  envelope (`errCode` / `externalMessage`), failure classification (missing
  AK/SK, 403 / CSS.0051, `[USE_ERROR]`, generic), paging (`totalSize`,
  full-page fallback, dedupe, datastore type forwarding), SDK fallback
  (list/detail/volume), filtering (name exact/fuzzy, status numeric/abnormal),
  normalization, rendering (cluster view, abnormal section, capacity alert,
  node view) and every main() output mode including error paths.

## Syntax / structure checks

```bash
python3 -m py_compile scripts/list_css_clusters.py scripts/ensure_env.py
python3 -m py_compile tests/test_list_css_clusters.py
bash -n scripts/ensure_env.py 2>/dev/null || true
python3 -m json.tool templates/*.json >/dev/null 2>&1 || true
bash <creator>/scripts/validate-skill.sh -s skills/bigdata/css/huawei-cloud-css-cluster-list
```

## CLI-validity evidence (KooCLI 7.3.12, live `--help`)

```bash
hcloud CSS ListClustersDetails --help        # GET; --limit / --offset / --datastoreType
hcloud CSS ShowClusterDetail --help          # GET; --cluster_id
hcloud CSS ShowClusterVolumeUsage --help     # GET; --cluster_id
```

All three operations exist and are GET. The response shapes were cross-checked
against the local `huaweicloudsdkcss` v1 models and the KooCLI CSS API metadata
(`ListClustersDetailsResponse: clusters + totalSize`,
`ShowClusterVolumeUsage: diskInfoList[diskCapacity, diskUsed, percentage]`).

## Live verification (when credentials carry CSS read permission)

```bash
hcloud configure list                                                       # profile check
python3 scripts/list_css_clusters.py --region cn-north-4                    # compact list
python3 scripts/list_css_clusters.py --region cn-north-4 --table            # cluster view
python3 scripts/list_css_clusters.py --region cn-north-4 --json | python3 -m json.tool
python3 scripts/list_css_clusters.py --region cn-north-4 --status abnormal
python3 scripts/list_css_clusters.py --region cn-north-4 --table --cluster-id <valid-id>
python3 scripts/list_css_clusters.py --region cn-north-4 --table --cluster-id <bogus-id>  # expect rc=1 + clear hint
```

During the coding session the live call was executed and returned
`CSS.0051 (The current policy does not allow the css:cluster:list operation)` —
the 403/IAM path was therefore verified live (explicit hint, rc=1), while the
success path was verified with a fake hcloud that returns real-shaped responses
(compact list / table cluster view / node view / abnormal highlighting / JSON).
Functional live verification with a granted account is the QA stage's job.

## Rendering evidence (offline, real-shaped responses)

```bash
CSS_LIST_HCLOUD_BIN=/path/to/fake-hcloud python3 scripts/list_css_clusters.py --table
CSS_LIST_HCLOUD_BIN=/path/to/fake-hcloud python3 scripts/list_css_clusters.py --table --cluster-id <id>
```

The table shows normal rows first and then a `⚠ 异常状态集群` section, plus a
`⚠ 容量使用率 ≥80%` section; the node view shows normal nodes first and then a
`⚠ 异常节点` section.