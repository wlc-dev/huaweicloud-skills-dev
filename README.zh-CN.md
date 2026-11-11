# 华为云 Skill 技能库

[English](README.md)

本仓库是面向华为云（Huawei Cloud）的 Skill 技能库，用于沉淀可被 AI Agent 直接发现、加载和执行的云上操作能力。每个技能以一份 `SKILL.md` 描述自身能力、触发方式与调用步骤，并辅以脚本、参考文档和模板，让开发者与 Agent 都能以统一方式完成查询、巡检、导出等任务。

## 项目定位

- **技能即能力单元**：一个技能聚焦一类云服务操作（如查询 ECS 实例、导出 OBS 对象清单），边界清晰、可独立安装。
- **文档驱动**：`SKILL.md` 是技能的唯一入口与事实来源，说明适用场景、前置条件、执行方式与错误处理。
- **面向 Agent 生态**：技能同时服务人类开发者与 AI Agent，可直接放入 Agent 的技能目录后被自动发现和调用。
- **只读优先**：多数技能为只读查询/导出能力，不修改云上资源；涉及写操作的技能会在文档中显式标注。

## 目录结构

技能按「类别 → 服务 → 技能」组织，标准层级为 `skills/<类别>/<服务>/<技能>/SKILL.md`：

```text
skills/
└── <类别>/
    └── <服务>/
        └── <技能>/
            ├── SKILL.md          # 技能说明（名称、描述、触发词、执行步骤）
            ├── references/       # 参考文档（API 说明、字段映射、示例）
            ├── scripts/          # 可执行脚本
            ├── templates/        # 输出/配置模板
            └── tests/            # 离线测试
```

部分技能按实际需要调整层级：公共技能放在 `skills/devtools/common/<技能>/`，个别按类别直挂的技能位于 `skills/<类别>/<技能>/`。

现有类别（共 11 个）：

| 类别 | 说明 | 典型服务 |
|------|------|----------|
| `ai` | 人工智能 | ModelArts |
| `bigdata` | 大数据 | CDM、CSS、MRS |
| `billing` | 计费 | BSS |
| `catalog` | 产品目录 | 产品与规格目录 |
| `compute` | 计算 | AS、BMS、CCE、CCI、ECS、FunctionGraph |
| `database` | 数据库 | DCS、DMS、DWS、GaussDB、RDS |
| `devtools` | 开发工具 | CodeArts、Common、CSE、Demo |
| `monitoring` | 监控运维 | AOM、CES、RMS |
| `network` | 网络 | APIG、CC、CDN、DNS、EIP、ELB、ER、NAT、VPC、VPCEP、VPN |
| `security` | 安全 | AAD、HSS、IAM、KMS、SCM、WAF |
| `storage` | 存储 | CBR、OBS、SFS |

仓库其他顶层目录：`docs/` 存放需求与设计文档，`notice/` 存放公告，`test/` 存放测试相关文件。

## 技能使用方式

1. **发现技能**：按类别浏览 `skills/<类别>/`，或按服务名定位到具体技能目录；每个技能目录顶部的 `SKILL.md` 即该技能的说明书。
2. **阅读 `SKILL.md`**：先看 frontmatter 中的 `name`、`description`、`tags` 与触发词，确认技能覆盖的操作范围、执行模式（CLI / SDK / API）及前置条件（如 AK/SK、区域）。
3. **安装到 Agent 环境**：将技能目录整体放入 Agent 的技能搜索路径（例如 `~/.agents/skills/` 或 `~/.hermes/skills/`），Agent 即可在匹配到触发场景时自动加载；也可在对话中直接点名技能目录。
4. **调用技能**：按 `SKILL.md` 给出的命令或脚本说明执行，例如运行 `scripts/` 下的脚本并传入区域、过滤条件、输出路径等参数；需要华为云命令行的场景按文档要求使用 `hcloud`（KooCLI）。
5. **消费输出**：技能的输出通常写入本地文件或直接返回结构化结果，不会回写云上资源；按文档说明查看生成结果。

`SKILL.md` 始终是使用技能的第一手依据：命令参数、错误分类、只读约束与安全提示均以其为准。

## 贡献指引

新增或修改技能时请遵循以下约定：

1. **目录规范**：在对应类别与服务下创建技能目录，命名为 `skills/<类别>/<服务>/huawei-cloud-<服务>-<功能>/`；公共技能放在 `skills/devtools/common/<技能>/`。
2. **必备文件**：技能根目录必须包含 `SKILL.md`，其 frontmatter 需提供 `name`、`description`（含触发词）与 `tags`；按需补充 `references/`、`scripts/`、`templates/`、`tests/`。
3. **能力边界**：一个技能只做一类事，读写操作需在文档中明确标注；默认遵循只读优先原则，禁止在仓库中提交任何 AK/SK、令牌或其它凭据。
4. **可验证性**：为脚本提供离线测试或可复现的验证方式，确保文档中的命令与参数与实现一致。
5. **文档与设计**：需求、方案与测试说明统一放入 `docs/`（如 `docs/issue-<编号>/`），并在提交中引用对应 Issue。
6. **提交要求**：一个需求对应一个 PR，基于仓库基线分支提交；不要改动与本次需求无关的技能目录；PR 描述中说明变更范围与验证方式。

更多文档规范与流程可参考 `docs/` 下的需求与设计文档。