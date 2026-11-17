# 任务拆解（task）：Issue #126

| # | 任务 | 产出 | 状态 |
| - | ---- | ---- | ---- |
| 1 | 需求理解与 Spec 对齐（Issue 评论 201303333） | 需求边界 / 回归点确认 | ✅ |
| 2 | 文档方案 | `docs/issue-126/spec.md`、`plan.md`、`task.md` | ✅ |
| 3 | TDD RED：新增排序 / 守卫 / 非法取值用例 | `tests/test_list_rds_export_markdown.py` 新增用例失败 | ✅ |
| 4 | 实现 `SORTABLE_KEYS` / `SortError` / `resolve_sort_by()` / `sort_instances()` | 脚本函数层 | ✅ |
| 5 | 守卫白名单：`--sort-by` 入 `READ_ONLY_VALUE_FLAGS` + 内联 `=` 取值剥离 | 守卫不误判 `--sort-by created` | ✅ |
| 6 | `main()` 接线：参数、快速校验、排序、空结果提示 | CLI 行为 | ✅ |
| 7 | SKILL.md 同步：描述 / 参数表 / 示例 / 守卫说明 / Edge Cases / Testing | 文档 | ✅ |
| 8 | 五轴自审查 + 全量单测 | 审查结论 + 测试全绿 | ✅ |
| 9 | 提交推送 / PR / Issue 评论 / A2A QA | PR #172 + Issue 评论 + A2A | ✅ |

## 验证命令

```bash
cd skills/database/rds/huawei-cloud-rds-export-markdown
python3 -m unittest discover -s tests -v
python3 scripts/list_rds_export_markdown.py --help
```

## 备注

- 不新增技能、不新增长期分支；分支沿用平台预置 `feat/issue-126`。
- `build_command()` 与分页 / 渲染 / 写文件逻辑均未改动。