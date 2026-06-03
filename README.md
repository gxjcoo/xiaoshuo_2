# 小说章节同结构改编工具（逻辑骨架）

用于：长篇 `txt` 切章、对照参考章调用 LLM 做同结构改编、审计与修订闭环。  
**本仓库分支不含任何具体小说正文**，剧情与设定由你本地放入 `chapters/` 等目录。

## 项目概览

这是一个本地 Python 脚本型小说生产流水线，不是 Web 服务或桌面应用。核心能力是：

1. 将整本小说 `.txt` 切成编号章节 Markdown。
2. 读取参考章节 `N.md`，分析其文风、结构功能和事件推进方式。
3. 调用 LLM 规划并生成结构功能对应、实体表达可改的章节。
4. 通过审计规则检测结构贴合、表达差异、连贯性、文风、AI 痕迹等问题。
5. 在审计通过后写入输出章节，并维护长期故事上下文。

主入口是 `workflow/cli.py`，单章处理主链路在 `chapter_processor.py`。

## 主流程

```text
chapters/N.md
        |
        v
chapter_processor.process_chapter()
        |
        +--> ai_handler.analyze_writing_style()
        +--> ai_handler.plan_chapter_with_ai()
        +--> ai_handler.generate_chapter_content()
        |
        v
audit_pipeline.audit_and_revise_until_pass()
        |
        v
output_chapters/N.md
        |
        +--> runtime/chapter-xxxx.*
        +--> story_context.json
```

默认启用严格结构适配模式：结构功能以 `chapters/` 中的参考章抽取出的结构骨架为准，上一章衔接优先使用 input 原作上一章。如需实验性自由改编，可使用 `--no_strict_structure_adaptation`（旧参数 `--no_strict_plot_fidelity`、`--no_strict_source_plot` 仍兼容）。

---

## 主链路之外的辅助能力

| 模块 | 真实接入位置 | 作用 |
|------|--------------|------|
| `structured_types.py`（`SceneNode`、`ChapterOutline`） | `outline_extractor` → `chapter_processor.process_chapter` | 把参考章结构骨架抽成 AST 缓存到 `runtime/chapter-XXXX.structured_outline.json` |
| `audit_enhanced.AuditHistory` | `audit_pipeline.audit_and_revise_until_pass` | 审计分数 Plateau 检测，连续 3 轮变化 <2 时回退到历史最佳版本 |
| `ai_trace_enhanced.enhanced_ai_trace_analysis` | `ai_trace_rules.analyze_ai_trace`（仅当 combined_score≥60 时叠加扣分） | 句长/段长 CV、过渡词密度等统计特征 |

> 注：早期版本在 README 里描述过 `StoryKnowledgeBase` / `run_enhanced_audit` /
> `build_revision_prompt` 等接口，但实际从未接入主链路。已在收尾时移除，避免
> 「文档承诺 ≠ 实际行为」。结构化骨架的提示词构建当前仍走 `ai_handler` 里
> 已经在用的文本路径。

## 环境

```bash
pip install -r requirements.txt
```

复制环境变量模板（勿把真实 Key 提交到 Git）：

```bash
cp .env.example .env
# 编辑 .env 填入 API Key 等
```

## 开发与测试

单元测试覆盖不调用 LLM 的确定性逻辑（实体映射、参考相似度、`ai_trace_rules` 等），无需配置 API Key 即可运行。

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## 目录约定（运行时自建亦可）

| 路径 | 说明 |
| --- | --- |
| `chapters/` | 参考章：`1.md`、`2.md` …（自备或由切章生成） |
| `output_chapters/` | 生成输出（默认） |
| `chapters_out/` | `split_novel.py` 默认切章输出 |
| `current_focus.md` | 近几章临时焦点（可选；默认可不填） |
| `runtime/`、`story_context.json` | 运行态（生成时出现，已在 `.gitignore`） |

## 核心模块

| 文件 | 职责 |
| --- | --- |
| `workflow/cli.py` | 工作流命令行入口，解析章节范围并批量调用处理流程 |
| `chapter_processor.py` | 单章处理编排：读参考章、生成、审计、落盘、写 runtime |
| `ai_handler.py` | 兼容入口（转发到 `llm/` 包）；实现见 `llm/client.py`、`llm/chapter_generate.py` 等 |
| `audit_pipeline.py` | 兼容入口（转发到 `audit/` 包）；实现见 `audit/pipeline.py` 等 |
| `ai_trace_rules.py` | 确定性 AI 痕迹规则检测，如句式同构、说明腔、对话同腔化 |
| `context_manager.py` | 维护 `story_context.json`，管理长期上下文、伏笔、核心角色和物品 |
| `domain_spec_loader.py` | 加载 `current_focus.md` |
| `config.py` | 配置中心，读取 `.env` 并定义模型、路径、审计和上下文参数 |

---

## 辅助模块

| 文件 | 职责 |
| --- | --- |
| `audit/` | 审计子包：`metrics`、`evaluators`、`revisers`、`pipeline`；`audit_pipeline.py` 为兼容转发 |
| `llm/` | LLM 子包：`client`（统一 API）、`prompts`、`titles`、`outline_extract`、`style_analysis`、`chapter_plan`、`hooks`、`chapter_generate`、`context_analysis`；`ai_handler.py` 为兼容转发 |
| `structured_types.py` | 结构骨架 AST 类型：`SceneNode` / `ChapterOutline` |
| `outline_extractor.py` | 从参考章抽取结构化骨架（JSON Schema 模式） |
| `audit_enhanced.py` | `AuditHistory`：审计分数 Plateau 检测 |
| `ai_trace_enhanced.py` | 基于句长/段长 CV 等统计特征的 AI 痕迹辅助评分 |

## 数据与运行产物

- `current_focus.md`：近几章临时重点；项目默认依赖参考章结构骨架、上下章锚点和运行态上下文，不再读取人工维护的长期意图文件。
- `story_context.json`：运行态故事上下文，记录最近剧情、伏笔、核心角色/道具等。
- `runtime/chapter-xxxx.style.md`：参考章风格分析缓存，重跑同章时默认复用。
- `runtime/chapter-xxxx.intent.md`：本章规划快照。
- `runtime/chapter-xxxx.outline.json`：由参考章抽取的结构骨架，用于排查“骨架抽错”还是“生成跑偏”。
- `runtime/chapter-xxxx.context.json`：生成时上下文快照。
- `runtime/chapter-xxxx.trace.json`：审计分数、参考文件、输出文件等追踪信息。

## 切章

```bash
python split_novel.py path/to/novel.txt -o chapters_out
```

## 同结构改编主流程

```bash
python -m workflow.cli run --input_dir chapters --output_dir output_chapters --start 1 --end 10
```

常用：`--chapter N`、`--length 3000`、`--no_strict_source_plot`（实验模式）、`--no_entity_rewrite`（关闭实体改写）、`--only <task>`（仅执行指定任务）、`--resume`（恢复中断的工作流）。

### 实体改写（默认开启）

`--entity_rewrite` 已升级为默认开启的「全局换名降重层」：

- 自动扫描参考章里的**角色名、地名、事件名、物件/动物名**，调用 LLM 生成同风格新名。
- 维护项目级词典 `runtime/global_entity_map.json`，**同一原名跨章永远映射到同一新名**，避免章节间「同人异名」。
- 正式运行前会默认预扫目标章节及下一章，把跨章衔接预览里首次出现的实体也提前纳入映射；调试时可用 `--no_entity_prescan` 关闭。
- 在所有 LLM 调用前先把参考原文、上一章衔接、下一章预览、风格备忘、骨架、意图都替换为新名；写盘前再做一次硬清洗。
- 审计阶段检测残留时会先硬替换、再扣分，并把残留明细注入修订 prompt。

关闭方式（仍想沿用原作实体名时）：

```bash
python -m workflow.cli run --no_entity_rewrite
# 或在 .env 中设置
ENTITY_REWRITE=0
```

如发现自动扫描漏掉某个角色，可手编 `runtime/global_entity_map.json` 的 `characters` 字段直接补条目，后续章节自动生效。

**推荐工作流**：直接运行工作流，实体映射会自动生成和维护：

```bash
# 运行工作流
python -m workflow.cli run --start 1 --end 10
```

全局映射表带有来源章节标记（`first_seen_chapter`），方便反查某个新名是哪一章首次引入的。

只分析参考章、生成 runtime 工件但不写正文：

```bash
python -m workflow.cli run --input_dir chapters --chapter 1 --only style_analysis
```

## 辅助脚本

```bash
python combine_chapters.py chapters -o combined.md
python rename_chapters.py chapters_out
```

- `split_novel.py`：按 `第N章 标题`、`第N章：标题` 等格式切章，输出 `1.md`、`2.md`。
- `combine_chapters.py`：按自然序合并目录内 `.md` 章节。
- `rename_chapters.py`：将 `第十二章xxx.md` 这类文件名转换成 `12.md`。

## 工具脚本（scripts/）

`scripts/` 目录包含用于检查、修复和测试生成章节的辅助脚本：

```bash
# 全面检查所有章节质量
python scripts/check_all_chapters.py

# 批量修复已知问题（三尺青锋错误、重复文本、标题格式等）
python scripts/fix_all_issues.py

# 检查生成进度
python scripts/check_progress.py
```

| 脚本 | 用途 |
|------|------|
| `check_all_chapters.py` | 全面检查所有章节，检测标题格式、三尺青锋错误、重复文本、修订说明等问题 |
| `fix_all_issues.py` | 批量修复所有已知问题 |
| `test_dag_structure.py` | 测试DAG结构相关功能 |
| `check_intent.py` | 检查生成意图 |
| `check_progress.py` | 检查生成进度 |
| `check_result.py` | 检查生成结果 |
| `fix_state.py` | 修复状态文件 |

详细说明见 `scripts/README.md`。

## 配置说明

- 提供商与模型：`config.py` + `.env`（`LLM_PROVIDER`、`MIMO_*`、`DEEPSEEK_*`、`DOUBAO_*` 等）
- **MiMo（默认）**：小米大模型，使用 OpenAI 兼容接口。Token Plan 的 Base URL 为 `https://token-plan-cn.xiaomimimo.com/v1`，模型为 `mimo-v2.5-pro`。
- **DeepSeek**：设置 `LLM_PROVIDER=deepseek`。
- **豆包**：设置 `LLM_PROVIDER=doubao`，使用火山方舟 Ark 接口。
- 审计门槛：见 `audit_rules.json`，当前总分阈值默认 `68`；规则审计与结构贴合审计同时空响应时不会正式落盘。
- 参考相似度与结构骨架贴合：见 `audit_rules.json` 中 `reference_similarity`、`plot_fidelity_min_score`；也可用 `.env` 中 `REFERENCE_SIMILARITY_*`、`PLOT_FIDELITY_MIN_SCORE` 设置默认值。
- LLM 调试日志默认关闭；需要排查接口返回时可在 `.env` 中设置 `DEBUG_LLM_LOG=1`。
- `.env` 可能包含真实 API Key，已被 `.gitignore` 忽略，不要提交。

## 当前工作区提示

当前仓库可能包含本地运行产物，例如 `output_chapters/`、`runtime/`、`story_context.json`、`all/`。这些通常与具体书稿或本地运行状态有关，换书或重跑前应确认是否需要保留。

## 常见问题

- **切章数为 0**：检查正文里是否为 `第N章 标题` 形式（章后须有空格或冒号再接标题）。
- **DeepSeek 连接失败**：增大 `API_MAX_RETRIES`、`API_HTTP_READ_TIMEOUT`；或换 `LLM_PROVIDER=doubao`。
- **换书后上下文串台**：删除本地 `story_context.json`、`runtime/`、`pruned_context_archive.json` 后重跑。

