# Acceptance Criteria — huawei-cloud-demo-vpc-list

读取时机：评审 / 合并前逐项打勾。

## 功能

- [x] 默认表格输出包含 id / name / cidr / status / enterprise_project_id / created_at 六列
- [x] `--json` 输出原始 VPC 数组（下游可解析）
- [x] `--names-only` 仅输出名称清单
- [x] `--region` 覆盖区域，默认 `cn-north-4`
- [x] `--limit` 透传为 KooCLI `--limit`（1–2000）
- [x] `page_info.next_marker` 自动翻页，`--max-pages` 上限保护
- [x] 空列表退出码 0，并给出中文提示

## 安全

- [x] 唯一可构造调用为 `hcloud VPC ListVpcs`（GET `/v1/{project_id}/vpcs`）
- [x] 写意图守卫先于参数解析执行，命中即退出码 1，无任何调用
- [x] 无硬编码 AK/SK / token / endpoint 凭据；示例全部使用 `{region}` / `{project_id}` 占位符
- [x] 脚本不读取、不回显、不落盘凭据；错误信息只截取 stderr 前 200 字符
- [x] 不写本地文件、不改云端状态

## 规范

- [x] SKILL.md：YAML Frontmatter（name / description / tags / version）+ Overview / Prerequisites / Workflow / Core Commands / Parameter Confirmation / Edge Cases / Verification / References
- [x] `references/` 五件套：dataflow-diagram / cli-installation-guide / iam-policies / verification-method / acceptance-criteria
- [x] 数据流图含起始/结束节点、CLI Operations 与 Data Sources 子图、图例与数据流说明表
- [x] `i18n/zh-CN/SKILL_CN.md` 存在，Frontmatter 与中文描述齐备
- [x] `scripts/__init__.py` 存在（Python 脚本目录规范）
- [x] `templates/test-vars.json` 提供占位测试参数（不含真实凭据）
- [x] 3 个以上可执行示例命令

## 测试

- [x] `python3 -m unittest discover -s tests` 全绿（18 项）
- [x] 覆盖输出模式、翻页、错误分类、守卫拦截、参数越界
- [x] 离线可跑：不需要网络与真实凭据

## 已知范围外

- [ ] 真实账号端到端查询（本 PR 为测试提交，未接生产凭据）
- [ ] VPC 创建 / 删除 / 变更（需独立的写能力技能 + 成本确认）
- [ ] 子网、对等连接等其他 VPC 子资源（后续按需扩展）