# KooCLI Installation & Credential Guide

读取时机：首次使用本技能、或 hcloud 未安装 / 凭据未配置时阅读。

## 1. 安装 KooCLI

```bash
# Linux / macOS 一键安装（官方脚本）
curl -sSL https://cn-north-4-hdn-koocli.obs.cn-north-4.myhuaweicloud.com/cli/latest/hcloud_install.sh -o ./hcloud_install.sh
bash ./hcloud_install.sh
rm -f ./hcloud_install.sh

# 校验
hcloud --version
```

安装失败时按官方文档替换下载地址（不同 region 的 OBS 域名不同）。

## 2. 配置凭据（带外完成，勿在对话中传 AK/SK）

```bash
hcloud configure init
# 依次输入：Access Key ID / Secret Access Key / 默认 region（如 cn-north-4）
# 输入内容不会回显，也不会被本技能读取或落盘
```

非交互环境（CI / 容器）用环境变量提供：

```bash
export HUAWEICLOUD_SDK_AK="{access_key_id}"
export HUAWEICLOUD_SDK_SK="{secret_access_key}"
export HUAWEICLOUD_SDK_REGION="cn-north-4"
```

> ⚠️ 上例中的花括号是**占位符**，不要提交真实值；不要把 AK/SK 写进脚本、
> 配置模板或 PR 描述。

## 3. 只读自检

```bash
hcloud configure list          # 查看当前 profile（不打印 SK）
hcloud VPC ListVpcs --cli-region=cn-north-4 --limit=1
```

## 4. 常见问题

| 现象 | 处理 |
| ---------- | --------- |
| `command not found: hcloud` | 重装 KooCLI，或把安装目录加入 `PATH` |
| `401 / APIGW.0301` | 凭据无效或过期 → 重新 `hcloud configure init` |
| `403 / VPC.0002` | IAM 缺少 `vpc:vpcs:list` → 按 `iam-policies.md` 授权 |
| `[USE_ERROR]` | 参数名/格式不符 → `hcloud VPC ListVpcs --help` 核对 |
| 区域无资源 | 换 `--region` 或确认账号在该 region 有 VPC |

## 5. 版本说明

脚本只依赖 `hcloud <Service> <Operation> --cli-region=...` 这一稳定调用形态，
KooCLI 2.x / 3.x 均可使用；不依赖任何已废弃参数。