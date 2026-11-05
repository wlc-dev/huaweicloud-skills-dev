# 任务拆解（task）：Issue #120 — huawei-cloud-nat-list

| # | 任务 | 产出 | 状态 |
|---|------|------|------|
| 1 | 需求理解 + API 事实核查（CLI 命令参考 / SDK 元数据） | plan.md §3 事实表 | ✅ |
| 2 | 需求文档 | docs/issue-120/spec.md | ✅ |
| 3 | 方案设计 | docs/issue-120/plan.md | ✅ |
| 4 | TDD：tests/test_list_nat_gateways.py（RED） | 测试文件 | ✅ |
| 5 | 实现 scripts/list_nat_gateways.py（GREEN） | 脚本 | ✅ |
| 6 | SKILL.md + references/ 5 份 + templates/test-vars.json | skill 文档 | ✅ |
| 7 | 新增测试全通过 + 相邻 skill 回归 | 测试输出 | ✅ |
| 8 | 五轴自审查（正确性/安全/性能/可维护性/测试） | 审查结论 | ✅ |
| 9 | 原子提交 + push feat/issue-120 | commits | ✅ |
| 10 | 建 PR（base master）+ Issue 评论 + A2A QA | PR #n | ✅ |
