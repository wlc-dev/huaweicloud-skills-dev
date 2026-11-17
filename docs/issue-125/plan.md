# Issue #125 Plan — huawei-cloud-dds-list 实现方案

## 架构（沿用 database 域 list 类 skill 成熟模式，参照 huawei-cloud-dms-list）

```text
agent → python3 scripts/list_dds.py
        → 守卫（写意图/操作白名单/参数范围）
        → hcloud DDS ListInstances --cli-region=<region> [--name= --id= --mode= ...]
        → GET https://dds.<region>.myhuaweicloud.com/v3/{project_id}/instances
        → 解析 {"instances": [...], "total_count": N} → 自动翻页 → 渲染
(hcloud 缺失) → 回退 huaweicloudsdkdds v3 DdsClient.list_instances
```

## 模块设计（scripts/list_dds.py，纯标准库）

| 组件 | 职责 |
|------|------|
| `WRITE_INTENT_KEYWORDS` | create/delete/restart/resize/backup/update/modify/scale/… + DDS 操作名（CreateInstance 等）；CREATING/DELETING 等状态词不拦；动词按整词匹配（`checkpoint-demo`、`dds-copy-01` 不误拦），长操作名按去分隔符文本匹配 |
| `guard_write_intent` / `guard_operation` | argv 扫描 + 操作白名单（仅 ListInstances），命中 GuardError 退出 1，任何命令执行前 |
| `build_command` | 唯一 hcloud argv 构造：`DDS ListInstances --cli-region --limit --offset` + 实测参数（id/mode/name/datastore_type/subnet_id/vpc_id/project_id），fuzzy 时 name 前缀 `*` |
| `run_hcloud` / `extract_json` / `classify_hcloud_failure` | 子进程执行、JSON 提取、错误分类（缺凭据/403/[USE_ERROR]/通用） |
| `list_instances` | total_count 驱动自动翻页（limit≤100，max-pages 防死循环）；hcloud 缺失时一次性回退 SDK |
| `list_instances_via_sdk` | huaweicloudsdkdds v3（发布包仅提供 `v3` 模块，v2 仅作兜底）；AK/SK/project_id 只读白名单环境变量；v3 的 limit/offset 为 int 参数 |
| `render_*` | 默认名称列表；`--table` 9 列（类型列 Sharding→集群/ReplicaSet→副本集/Single→单节点，规格取 `groups[].nodes[].spec_code` 去重拼接、兼容旧形状 `flavor[]`，创建时间取 `created`、兼容 `created_at`，缺失 `-`）；`--json` 原始数组；CJK 按显示宽度对齐 |
| `main` | argparse；status 客户端过滤（实测无服务端参数）；空列表提示退出 0 |

## 步骤（TDD）

1. 脚手架：目录 + ensure_cli.sh/install_cli.sh + templates/test-vars.json。
2. RED→GREEN：tests/test_list_dds.py 覆盖守卫/命令构造/分页/错误分类/SDK 回退/
   渲染/main 输出路径（mock subprocess 与 fake SDK，无网络无凭据）。
3. references 五件套（iam-policies 以实测 dds:instance:listAll 为准）。
4. SKILL.md。
5. 全量单测 + bash -n 语法校验 + 自审查（五轴）→ 原子提交 → PR。

## 风险

- DDS ListInstances 无 status 服务端过滤 → 客户端过滤并在 SKILL.md/帮助注明。
- 环境无 DDS 实例 → 空列表路径以实测 {"instances":[],"total_count":0} 校验。
