# 小说章节同结构改编工具（逻辑骨架）

用于：长篇 `txt` 切章、对照参考章调用 LLM 做同结构改编、审计与修订闭环。  
**本仓库分支不含任何具体小说正文**，剧情与设定由你本地放入 `input_chapters/`、`story_domain/` 等目录。

## 项目概览

这是一个本地 Python 脚本型小说生产流水线，不是 Web 服务或桌面应用。核心能力是：

1. 将整本小说 `.txt` 切成编号章节 Markdown。
2. 读取参考章节 `N.md`，分析其文风、结构功能和事件推进方式。
3. 调用 LLM 规划并生成结构功能对应、实体表达可改的章节。
4. 通过审计规则检测结构贴合、表达差异、连贯性、文风、AI 痕迹等问题。
5. 在审计通过后写入输出章节，并维护长期故事上下文。

主入口是 `app.py`，单章处理主链路在 `chapter_processor.py`。

## 主流程

```text
input_chapters/N.md
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

默认启用严格结构适配模式：结构功能以 `input_chapters/` 中的参考章抽取出的结构骨架为准，上一章衔接优先使用 input 原作上一章，不把生成稿自动反写进 `story_domain/`。如需实验性自由改编，可使用 `--no_strict_structure_adaptation`（旧参数 `--no_strict_plot_fidelity`、`--no_strict_source_plot` 仍兼容）。

---

## 新增核心模块（可选使用）

项目新增了 4 个核心增强模块，解决原有流程中的痛点：

| 痛点 | 新增模块 | 解决的问题 |
|------|----------|-----------|
| 结构骨架格式不稳定 | `structured_types.py` + `outline_extractor.py` | 用 JSON Schema 强制结构化 AST |
| 审计反馈模糊（「连贯性不够」） | `audit_enhanced.py` | 具体位置 + 修改建议 + Plateau 检测 |
| 上下文容易忘记角色设定 | `StoryKnowledgeBase` (in `structured_types.py`) | 知识库 + 实体归一 |
| AI 痕迹只看表面词 | `ai_trace_enhanced.py` | 句子/段落长度分布统计分析 |

---

## 新功能快速上手

### 1. 提取结构化骨架（可选）

```python
from outline_extractor import (
    extract_structured_outline_from_reference,
    build_generation_prompt_from_outline,
)

outline = extract_structured_outline_from_reference(
    reference_text,
    chapter_number=1,
    strict_source_plot=True,
)
# outline.scenes 是结构化的场景列表
# outline.chapter_goal, outline.core_conflict...

# 然后可以用它构建生成提示词
prompt = build_generation_prompt_from_outline(
    outline,
    writing_style,
    story_context,
    domain_spec,
    chapter_number=1,
)
```

### 2. 使用增强审计（可选）

```python
from audit_enhanced import (
    run_enhanced_audit,
    build_revision_prompt,
    AuditHistory,
    format_audit_summary,
)

# 审计历史追踪，用于 Plateau 检测
history = AuditHistory()

# 运行增强审计
audit_result = run_enhanced_audit(
    generated_text,
    dimension_scores,
    pass_threshold=85.0,
    reference_text=reference_text,
    history=history,
)

# audit_result.feedback_items 是具体的修改建议
print(format_audit_summary(audit_result))

# 构建修订提示词
if audit_result.should_revise and not audit_result.plateau_detected:
    revise_prompt = build_revision_prompt(generated_text, audit_result)
```

### 3. 使用知识库管理上下文（可选）

```python
from structured_types import (
    StoryKnowledgeBase,
    CharacterState,
    Conflict,
    ItemInfo,
)

kb = StoryKnowledgeBase()

# 添加角色
kb.add_character(CharacterState(
    name="宝寿道长",
    aliases=["年轻道士", "他"],
    current_goal="赚够钱建道观",
    current_emotion="calm",
))

# 添加钩子
kb.add_hook("小熊似乎藏着什么秘密")

# 生成提示词用的上下文摘要
print(kb.to_context_prompt())

# 保存/加载
kb_json = kb.to_json()
kb2 = StoryKnowledgeBase.from_json(kb_json)
```

### 4. 增强 AI 痕迹检测（可选）

```python
from ai_trace_enhanced import (
    enhanced_ai_trace_analysis,
    format_ai_trace_report,
)

analysis = enhanced_ai_trace_analysis(generated_text)
print(format_ai_trace_report(analysis))

# analysis["combined_score"] 是综合得分（0-100，越高越像 AI）
# analysis["statistical_details"] 包含句子长度 CV、段落长度 CV 等
```

## 环境

```bash
pip install -r requirements.txt
```

复制环境变量模板（勿把真实 Key 提交到 Git）：

```bash
cp .env.example .env
# 编辑 .env 填入 API Key 等
```

## 目录约定（运行时自建亦可）

| 路径 | 说明 |
| --- | --- |
| `input_chapters/` | 参考章：`1.md`、`2.md` …（自备） |
| `output_chapters/` | 生成输出（默认） |
| `chapters_out/` | `split_novel.py` 默认切章输出 |
| `story_domain/` | 领域圣经模板（可填） |
| `author_intent.md` / `current_focus.md` | 意图模板（可填） |
| `runtime/`、`story_context.json` | 运行态（生成时出现，已在 `.gitignore`） |

## 核心模块

| 文件 | 职责 |
| --- | --- |
| `app.py` | 命令行入口，解析章节范围并批量调用处理流程 |
| `chapter_processor.py` | 单章处理编排：读参考章、生成、审计、落盘、写 runtime |
| `ai_handler.py` | LLM 调用封装，负责风格分析、章节规划、正文生成、标题生成、上下文分析 |
| `audit_pipeline.py` | 审计评分与修订闭环，结合规则审计和 AI 痕迹检测 |
| `ai_trace_rules.py` | 确定性 AI 痕迹规则检测，如句式同构、说明腔、对话同腔化 |
| `context_manager.py` | 维护 `story_context.json`，管理长期上下文、伏笔、核心角色和物品 |
| `domain_spec_loader.py` | 加载 `story_domain/*.md`、`author_intent.md`、`current_focus.md` |
| `knowledge_sync.py` | 实验模式下从生成章节提取可沉淀到领域文档的增量信息 |
| `config.py` | 配置中心，读取 `.env` 并定义模型、路径、审计和上下文参数 |

---

## 新增模块（增强功能）

| 文件 | 职责 | 优先级 |
| --- | --- | --- |
| `structured_types.py` | 结构化类型：SceneNode, ChapterOutline, AuditFeedbackItem, StoryKnowledgeBase | P0 |
| `outline_extractor.py` | 结构化骨架提取 + 生成提示词构建 | P0 |
| `audit_enhanced.py` | 增强审计：可操作的 diff 反馈 + Plateau 检测 | P0 |
| `ai_trace_enhanced.py` | 增强 AI 痕迹检测：统计分布对比 | P1 |

## 数据与运行产物

- `story_domain/`：世界观、角色、术语、文风等长期设定资料，生成时会注入提示词。
- `author_intent.md`：作者长期意图。
- `current_focus.md`：近几章重点。
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
python app.py --input_dir input_chapters --output_dir output_chapters --start_chapter 1 --end_chapter 10
```

常用：`--chapter N`、`--length 3000`、`--no_strict_structure_adaptation`（实验模式）、`--force_reanalyze`（忽略缓存重分析）、`--analyze_only`（只生成分析工件）。

只分析参考章、生成 runtime 工件但不写正文：

```bash
python app.py --input_dir input_chapters --chapter 1 --analyze_only
```

## 辅助脚本

```bash
python combine_chapters.py input_chapters -o combined.md
python rename_chapters.py chapters_out
```

- `split_novel.py`：按 `第N章 标题`、`第N章：标题` 等格式切章，输出 `1.md`、`2.md`。
- `combine_chapters.py`：按自然序合并目录内 `.md` 章节。
- `rename_chapters.py`：将 `第十二章xxx.md` 这类文件名转换成 `12.md`。

## 配置说明

- 提供商与模型：`config.py` + `.env`（`LLM_PROVIDER`、`DEEPSEEK_*`、`DOUBAO_*` 等）
- 审计门槛：见 `audit_rules.json`，可用环境变量覆盖（见 `config.py` 中 `AUDIT_*`）
- 参考相似度与结构骨架贴合：见 `audit_rules.json` 中 `reference_similarity`、`plot_fidelity_min_score`；也可用 `.env` 中 `REFERENCE_SIMILARITY_*`、`PLOT_FIDELITY_MIN_SCORE` 设置默认值。
- `.env` 可能包含真实 API Key，已被 `.gitignore` 忽略，不要提交。

## 当前工作区提示

当前仓库可能包含本地运行产物，例如 `output_chapters/`、`runtime/`、`story_context.json`、`all/`。这些通常与具体书稿或本地运行状态有关，换书或重跑前应确认是否需要保留。

## 常见问题

- **切章数为 0**：检查正文里是否为 `第N章 标题` 形式（章后须有空格或冒号再接标题）。
- **DeepSeek 连接失败**：增大 `API_MAX_RETRIES`、`API_HTTP_READ_TIMEOUT`；或换 `LLM_PROVIDER=doubao`。
- **换书后上下文串台**：删除本地 `story_context.json`、`runtime/`、`pruned_context_archive.json` 后重跑。

---

## 向后兼容性说明

所有新增模块都是**向后兼容**的：

- `app.py` 原有主流程完全不变，不用改现有代码
- 新增模块（`structured_types.py`、`outline_extractor.py`、`audit_enhanced.py`、`ai_trace_enhanced.py`）可以独立使用
- 原有 `audit_pipeline.py`、`ai_trace_rules.py` 继续工作

你可以**逐步集成**新功能，不需要一次性重构所有代码！
