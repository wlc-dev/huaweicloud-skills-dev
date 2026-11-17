# 方案设计（plan）：Issue #126 — RDS Markdown 导出新增本地排序

## 1. 任务类型与复杂度

- 类型：feature（存量技能功能增强）。
- 复杂度：简单-中等（单脚本 + 文档 + 单测，无新增依赖、无新增文件类型）。

## 2. 总体方案

沿用仓库 `skills/compute/ecs/huawei-cloud-ecs-export-sorted` 已验证的「本地排序 + 无效值末尾 +
稳定排序」模式，在 RDS 导出脚本内新增一层纯函数排序，链路：

```text
main() → guard_write_intent / guard_operation
       → resolve_sort_by(--sort-by)        # 失败即快速退出（不触达网络）
       → list_instances(region, status, name)   # KooCLI 优先，SDK 兜底，--status 客户端过滤
       → sort_instances(instances, sort_by)     # 新增：本地排序
       → render_markdown() → write_markdown()
```

新增函数只消费实例 dict 列表，不触达 hcloud / SDK 调用层，`build_command()` 保持不变。

## 3. 关键决策

| 决策 | 选项 | 选择 | 理由 |
| ---- | ---- | ---- | ---- |
| 排序位置 | 服务端 / 客户端 | 客户端 | `ListInstances` 无排序参数；须与客户端 `--status` 过滤共存 |
| 排序方向 | 升序 / 降序 / 可选 | 固定升序 | Issue 未要求降序，固定方向避免新增参数面 |
| 缺失字段 | 报错 / 排末尾 | 排末尾 | 与渲染层 `-` 语义一致，不因个别字段缺失中断导出 |
| 非法取值 | argparse `choices` / 显式校验 | 显式校验 | `choices` 退出码为 2，与技能「统一 exit 1」契约冲突 |
| 时间比较 | 直接比较 datetime / 转 epoch | 转 UTC epoch | `Z` / `+0800` / 无时区混用直接比较会抛 `TypeError` |
| 失败时机 | 排序时校验 / 解析后立即校验 | 解析后立即校验 | 非法取值不发起任何 API 调用，也不写文件 |

## 4. 实现要点

1. 常量 `SORTABLE_KEYS = ("name", "created")`；`SortError(RdsListError)` 复用技能统一 `exit 1`。
2. `resolve_sort_by(value)`：`None` / 空串 → `None`；大小写不敏感匹配；未知取值抛
   `SortError("--sort-by 仅支持 name 或 created（收到: %s）")`。
3. `sort_instances(instances, sort_by)`：`sort_by` 为空 → `list(instances)`（不改原列表、不重排）；
   否则按 `_sort_value()` 拆 valid / invalid，`valid.sort(...)` 稳定排序后拼接 `invalid`。
4. `_sort_value()`：
   - `name` → `name`（缺失回退 `id`）→ `(True, lower())`；都缺失 → `(False, None)`。
   - `created` → `_parse_created()` 转 UTC datetime → `(True, (0, epoch))`；
     不可解析 → `(True, (1, text.lower()))`；缺失 → `(False, None)`。
   - 元组首元素区分「已解析 / 文本回退」，避免 float 与 str 直接比较。
5. `_parse_created()`：去空白、`Z/z` → `+00:00`、首个空格 → `T`，`datetime.fromisoformat`；
   无时区按 UTC 处理，统一 `astimezone(utc)`。
6. ⚠️ 守卫：`READ_ONLY_VALUE_FLAGS` 加入 `--sort-by`；`scrub_read_only_values()` 额外剥离
   `--flag=value` 的内联取值，使 `--sort-by=created` 同样不被误判（此前 `--output=...` 也有同类
   误判面）。
7. `main()`：新增 `--sort-by` 参数（`dest="sort_by"`），在 `list_instances()` 前完成校验，
   排序后传给 `render_markdown()`；空结果提示仅在传参时追加 `sort-by=<x>`。

## 5. 测试策略（离线、确定性）

| 层 | 用例 |
| -- | ---- |
| `sort_instances()` | 无参保序且返回副本 / name 大小写不敏感升序 / id 回退 / 缺失末尾 / created 多种时间格式 / 不可解析文本回退 / 稳定排序 / 输入不被修改 / 非法取值 |
| 守卫 | `--sort-by created`、`--sort-by=created` 均不触发写意图；`--operation DeleteInstance` 仍被拦截 |
| `main()` | name 排序行序 / created 排序行序 / 非法取值退出 1 且不调用 hcloud、不生成文件 / 无参保序 |
| 回归 | 既有 100+ 用例全量通过（`python3 -m unittest discover -s tests -v`） |

## 6. 验证方式

```bash
cd skills/database/rds/huawei-cloud-rds-export-markdown
python3 -m unittest discover -s tests -v
python3 scripts/list_rds_export_markdown.py --sort-by invalid   # 期望 exit 1 + 明确报错
```