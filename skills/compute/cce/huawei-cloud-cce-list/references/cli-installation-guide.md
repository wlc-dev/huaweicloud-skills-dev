# KooCLI Installation & Credential Guide

## Install KooCLI

Official quick start: https://support.huaweicloud.com/qs-hcli/hcli_02_003.html

```bash
# Linux/macOS
curl -sSL https://cn-north-4-res.huaweicloud.com/cli/latest/install.sh -o install.sh
bash install.sh
hcloud version
```

## Configure credentials (out-of-band only)

The skill script never reads, echoes, or stores AK/SK — authentication is fully
delegated to the active KooCLI profile. Configure it in your own terminal:

```bash
hcloud configure  # interactive; never paste AK/SK into an agent chat
```

Verify (read-only, no secrets echoed):

```bash
hcloud configure list
```

## SDK fallback (optional)

When hcloud is not installed, the script falls back to the official SDK:

```bash
pip install huaweicloudsdkcore huaweicloudsdkcce
```

The SDK reads credentials from the environment (`HUAWEI_ACCESS_KEY` /
`HUAWEI_SECRET_KEY`, or `HW_*` / `HWC_*` variants) — never from chat or literals.
The v3 ListClusters path is project-scoped
(`/api/v3/projects/{project_id}/clusters`); set `HUAWEI_PROJECT_ID` (or pass
`--project-id`) only when the SDK cannot resolve the project id from the
credentials via IAM.

## skill-quality-cli wrapper (mandatory)

Every `hcloud` call made while using this skill must be wrapped so telemetry is
collected and bare CLI calls are avoided:

```bash
skill-quality-cli run --skill-name huawei-cloud-cce-list -- hcloud CCE ListClusters --cli-region=cn-north-4
```

`skill-quality-cli` is provided by the agent runtime. To upgrade it manually run
`skill-quality-cli upgrade` (no auto-upgrade); set `SKILL_QUALITY_REPORT=0` to
disable telemetry reporting.

## Used by this skill

```bash
skill-quality-cli run --skill-name huawei-cloud-cce-list -- hcloud CCE ListClusters --cli-region=cn-north-4
```

If hcloud reports a credential problem, the script surfaces it as
`缺少 AK/SK 凭证` with this reference attached.