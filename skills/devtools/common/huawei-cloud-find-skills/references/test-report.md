# 功能测试报告 — huawei-cloud-find-skills

> 生成时间：2026-11-11
> 测试区域：不涉及云区域（本技能为技能发现/安装元技能，不调用 hcloud）
> 测试方式：本地离线回归测试 + 结构校验 + 命令前置检查

## 测试范围

本技能不包含 `hcloud` 命令、不依赖 AK/SK，也不创建任何云资源。功能测试聚焦于：

1. `scripts/search-skills.py` 的检索、排序、覆盖分组、双源回退与缓存；
2. `scripts/install_cli.sh` 的可选 CLI 安装语义（best-effort 默认 + `--strict`）；
3. `SKILL.md` / `references` 中示例命令照原样可执行。

## 测试结果汇总

| 指标 | 值 |
|------|-----|
| 离线回归用例（scripts/test_search_skills.py） | 12 |
| ✅ 通过 | 12 |
| ❌ 失败 | 0 |
| 结构校验（validate-skill.sh） | PASS 29 / FAIL 0 / WARN 5 |
| 冒烟（test-cli-commands.sh） | 无可执行 hcloud 用例（PASS=0, live_skipped=true） |

## 回归用例覆盖

`python3 -m unittest scripts/test_search_skills.py -v`（标准库 + fixture 索引，无网络依赖）覆盖：

- CCE 等「名称不体现、但 services 覆盖目标服务」技能的覆盖标注与分组（上游 #1047 关联场景）；
- 排序与 `-c` 类目过滤、缺 `services`/`type` 时按名称回退；
- 无结果提示与用法校验；
- 双源回退与本地缓存（命中缓存不再发起网络请求）。

## 文档命令审计

| 文档命令 | 结果 |
|----------|------|
| `bash scripts/install_cli.sh` | ✅ 退出 0（当前平台无可信包时打印可读告警并继续，CLI 仅用于可选遥测）；`--strict` 时失败退出 1；校验和不匹配始终退出 1 |
| `python3 scripts/search-skills.py -k "<keyword>"` | ✅ 退出 0，输出命中列表；网络/解析失败非零并给出 stderr 原因 |
| `python3 scripts/search-skills.py -c "<category>"` | ✅ 退出 0，输出列表或无结果提示（无结果也是成功） |
| `python3 scripts/search-skills.py`（缺参数） | ✅ 非零退出 + 用法提示（stderr），不发起网络请求 |
| `npx skills add ... --skill <name> -y` | 依赖本机 Node/npx；安装前已加 `command -v npx` 快速失败检查 |

## 结论

✅ 离线回归全部通过；本技能无 hcloud 可执行用例，真实只读云调用不适用（`live_skipped=true`，如实标注）。