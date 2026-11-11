# IAM 权限说明 — huawei-cloud-find-skills

> 本 Skill 是本地技能检索与安装工具，**不直接调用任何华为云 API**，因此不需要任何 IAM
> 凭证、委托或最小权限策略。

## 本 Skill 的权限

- **无需 IAM 权限**：不读写云资源，不发起云 API 调用。
- 仅访问公开网络资源（只读）：
  - `gitcode.com` API v5 — 技能索引；
  - `gitee.com` raw — 索引备份源；
  - `github.com` / `raw.githubusercontent.com` — 技能详情（SKILL.md）。
- 可选匿名质量遥测（`skill-quality-cli`）：仅上报技能名/类目/执行状态等元信息，
  **不携带凭证，也不需要 IAM**；设置 `export SKILL_QUALITY_REPORT=0` 可整体关闭。

## 关于被安装的子 Skill

本 Skill 只负责发现与安装其他华为云 Skill。被安装的子 Skill 如调用华为云 API，其权限
由该子 Skill 自己的 `references/iam-policies.md` 声明，**本文件不为任何子 Skill 代申请权限**。

## MFA

不需要 MFA：本 Skill 没有写操作、没有删除操作，也不访问受保护云资源。

## 最小权限策略（本 Skill）

以下策略不含任何 Allow 动作，等价于「不授予云 API 权限」，仅用于说明本 Skill 无需云权限：

```json
{
  "Version": "1.1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [],
      "Resource": ["*"]
    }
  ]
}
```