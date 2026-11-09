# KooCLI Installation & Credential Guide

## Install KooCLI

Official quick start: https://support.huaweicloud.com/qs-hcli/hcli_02_003.html

```bash
# Linux/macOS
curl -sSL https://cn-north-4-res.hcccloud.com/cli/latest/install.sh -o install.sh
bash install.sh
hcloud version
```

Confirm the CSS service and the three read-only operations are available:

```bash
hcloud CSS ListClustersDetails --help
hcloud CSS ShowClusterDetail --help
hcloud CSS ShowClusterVolumeUsage --help
```

## Configure credentials (out-of-band only)

The script never reads, echoes or stores AK/SK — authentication is fully
delegated to the active KooCLI profile. Configure it in your own terminal:

```bash
hcloud configure  # interactive; never paste AK/SK into an agent chat
```

Verify (read-only, no secrets echoed):

```bash
hcloud configure list
```

## Used by this skill

```bash
hcloud CSS ListClustersDetails --cli-region=cn-north-4 --limit=10 --offset=1
hcloud CSS ShowClusterDetail --cli-region=cn-north-4 --cluster_id=<cluster-id>
hcloud CSS ShowClusterVolumeUsage --cli-region=cn-north-4 --cluster_id=<cluster-id>
```

If hcloud reports a credential problem, the script surfaces it as
`缺少 AK/SK 凭证` with this reference attached.

## SDK fallback

When hcloud is absent, the script uses the official `huaweicloudsdkcss` v1 SDK.
Install the SDK dependencies out-of-band:

```bash
python3 scripts/ensure_env.py
```

The SDK path reads AK/SK only from whitelisted environment variables
(`HUAWEICLOUD_SDK_AK` / `HUAWEICLOUD_SDK_SK`, `CLOUD_SDK_AK` / `CLOUD_SDK_SK`, or
the `HUAWEI_*` / `HW_*` / `HWC_*` aliases) and an optional
`HUAWEICLOUD_SDK_PROJECT_ID`. Set them in your shell profile; never paste them
into chat.