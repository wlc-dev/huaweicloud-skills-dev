# Verification Method — huawei-cloud-demo-vpc-list

读取时机：交付前跑验证、或复核他人验证结论时阅读。

## 1. 离线验证（无凭据、无网络，必做）

```bash
cd skills/devtools/demo/huawei-cloud-demo-vpc-list
python3 -m unittest discover -s tests -v
```

判定标准：

| 检查 | 通过标准 |
| ---------- | --------- |
| 用例数量 | ≥ 15（当前 18） |
| 结果 | `OK`，无 failed / error |
| 覆盖点 | 表格 / JSON / 名称清单 / 空列表 / 翻页 / 403 / USE_ERROR / 缺 CLI / 守卫拦截 / 参数越界 |
| 凭据依赖 | 全程使用 `tests/fake_hcloud.sh`，不读取真实凭据 |

## 2. 结构与规范验证（必做）

| 检查 | 命令 | 通过标准 |
| ---------- | --------- | --------- |
| Frontmatter 完整 | `head -20 SKILL.md` | 含 `name` / `description` / `tags` / `version` |
| 引用文件存在 | 逐个 `ls references/*.md` | SKILL.md 里链接的 5 个文件均存在 |
| 数据流图有效 | `grep -c '```mermaid' references/dataflow-diagram.md` | ≥ 1，且含 CLI Operations / Data Sources 子图 |
| 无硬编码凭据 | `grep -rniE 'ak\s*=\s*[a-z0-9]{10,}|sk\s*=\s*[a-z0-9]{10,}' .` | 无命中 |
| 中文版同步 | `head -12 i18n/zh-CN/SKILL_CN.md` | Frontmatter 存在，description 为中文 |

## 3. 真实只读验证（有凭据时，推荐）

```bash
hcloud configure list                     # 确认 profile 就绪（不打印 SK）
python3 scripts/list_vpc.py --limit 5     # 表格输出
python3 scripts/list_vpc.py --json | head -20
python3 scripts/list_vpc.py --names-only
```

判定标准：

| 场景 | 期望 |
| ---------- | --------- |
| 账号有 VPC | 表格列出 id / name / cidr / status，退出码 0 |
| 账号无 VPC | 打印「当前区域（…）无虚拟私有云（VPC）」，退出码 0 |
| 缺权限 | 提示检查 `vpc:vpcs:list`，退出码 1 |
| 缺凭据 | 提示带外配置 profile，退出码 1 |

## 4. 只读性验证（必做）

```bash
python3 scripts/list_vpc.py delete            # 期望：守卫拦截，退出码 1
python3 scripts/list_vpc.py --update-vpc      # 期望：守卫拦截，退出码 1
grep -n 'ListVpcs' scripts/list_vpc.py        # 期望：仅 build_command() 一处构造调用
```

同时确认：技能目录内无任何 `subprocess` 调用点会拼出 `VPC Create* / Delete* /
Update*` 操作名。

## 5. 已验证记录

| 日期 | 范围 | 结果 |
| ---------- | --------- | --------- |
| 2026-11-09 | 离线单测 18 项（fake hcloud 替身） | OK |
| 2026-11-09 | 守卫拦截 `delete` / `--update-vpc` | 均退出码 1，无调用 |
| 2026-11-09 | 真实账号查询 | 未执行（本 PR 为测试提交，无生产凭据） |