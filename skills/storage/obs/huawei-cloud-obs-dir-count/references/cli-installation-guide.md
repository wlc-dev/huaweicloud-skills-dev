# CLI Installation Guide

This skill requires **hcloud (KooCLI)** and the **obsutil** tool (bundled with KooCLI's OBS module or installed standalone).

## Table of Contents

- [Install hcloud](#install-hcloud)
- [Install obsutil](#install-obsutil)
- [Configure OBS Credentials (obsutil)](#configure-obs-credentials-obsutil)
- [Verify Installation](#verify-installation)
- [Troubleshooting](#troubleshooting)

---

## Install hcloud

### Linux (x86_64)

```bash
curl -O https://obs-community-tool.obs.cn-north-1.myhuaweicloud.com/hcloudcli/latest/hcloudcli-linux-amd64.tar.gz
tar -xzf hcloudcli-linux-amd64.tar.gz
chmod +x hcloud
sudo mv hcloud /usr/local/bin/
```

### Linux (ARM64)

```bash
curl -O https://obs-community-tool.obs.cn-north-1.myhuaweicloud.com/hcloudcli/latest/hcloudcli-linux-arm64.tar.gz
tar -xzf hcloudcli-linux-arm64.tar.gz
chmod +x hcloud
sudo mv hcloud /usr/local/bin/
```

### macOS

```bash
brew install hcloudcli
```

### Windows (PowerShell)

```powershell
Invoke-WebRequest -Uri "https://obs-community-tool.obs.cn-north-1.myhuaweicloud.com/hcloudcli/latest/hcloudcli-windows-amd64.zip" -OutFile "hcloudcli.zip"
Expand-Archive hcloudcli.zip
# Add hcloud.exe to PATH
```

### Node.js / npm (alternative)

```bash
npm install -g @huaweicloud/hcloud
```

---

## Install obsutil

The `hcloud OBS` module is backed by obsutil. With a recent KooCLI the bundled obsutil works out of the box; if it is missing, install standalone obsutil.

### Linux (x86_64)

```bash
curl -O https://obs-community-tool.obs.cn-north-1.myhuaweicloud.com/obsutil/current/obsutil_linux_amd64.tar.gz
tar -xzf obsutil_linux_amd64.tar.gz
chmod +x obsutil_linux_amd64_*/obsutil
sudo mv obsutil_linux_amd64_*/obsutil /usr/local/bin/
```

### Linux (ARM64)

```bash
curl -O https://obs-community-tool.obs.cn-north-1.myhuaweicloud.com/obsutil/current/obsutil_linux_arm64.tar.gz
tar -xzf obsutil_linux_arm64.tar.gz
chmod +x obsutil_linux_arm64_*/obsutil
sudo mv obsutil_linux_arm64_*/obsutil /usr/local/bin/
```

---

## Configure OBS Credentials (obsutil)

> **Important:** OBS credentials do **not** inherit from the KooCLI account credentials. The `hcloud OBS ls` command reads AK/SK/endpoint from the obsutil config file (`~/.obsutilconfig`).

**Never ask the user to paste AK/SK directly into the conversation.** Instruct them to run the following in their own terminal:

```bash
hcloud obs config -i=<YourAK> -k=<YourSK> -e=obs.<Region>.myhuaweicloud.com
```

Example (cn-north-4):

```bash
hcloud obs config -i=<YourAK> -k=<YourSK> -e=obs.cn-north-4.myhuaweicloud.com
```

Common Endpoints:

| Region | Endpoint |
|--------|----------|
| cn-north-4 | `obs.cn-north-4.myhuaweicloud.com` |
| cn-east-3 | `obs.cn-east-3.myhuaweicloud.com` |
| cn-south-1 | `obs.cn-south-1.myhuaweicloud.com` |
| cn-southwest-2 | `obs.cn-southwest-2.myhuaweicloud.com` |

AK/SK can be obtained from the Huawei Cloud console "My Credentials" page.

---

## Verify Installation

```bash
hcloud version
hcloud OBS ls -s -limit=1
```

A successful run prints `Bucket number: N` with bucket names prefixed by `obs://`.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `Please set ak, sk and endpoint in the configuration file!` | obsutil credentials not configured — run `hcloud obs config` as above |
| `InvalidAccessKeyId` | Wrong AK/SK or expired key — reconfigure credentials |
| `command not found: hcloud` | hcloud not in PATH — install or add to PATH |
| `command not found: obsutil` | obsutil not installed — install standalone obsutil or upgrade KooCLI |
| `NoSuchBucket` | The bucket does not exist or the AK/SK has no access to it — verify bucket name and IAM policy |
