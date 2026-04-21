# 小说章节仿写工具（逻辑骨架）

用于：长篇 `txt` 切章、对照参考章调用 LLM 仿写、审计与修订闭环。  
**本仓库分支不含任何具体小说正文**，剧情与设定由你本地放入 `input_chapters/`、`story_domain/` 等目录。

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

## 切章

```bash
python split_novel.py path/to/novel.txt -o chapters_out
```

## 仿写主流程

```bash
python app.py --input_dir input_chapters --output_dir output_chapters --start_chapter 1 --end_chapter 10
```

常用：`--chapter N`、`--length 3000`、`--no_strict_source_plot`（实验模式）。

## 辅助脚本

```bash
python combine_chapters.py input_chapters -o combined.md
python rename_chapters.py chapters_out
```

## 配置说明

- 提供商与模型：`config.py` + `.env`（`LLM_PROVIDER`、`DEEPSEEK_*`、`DOUBAO_*` 等）
- 审计门槛：见 `audit_rules.json`，可用环境变量覆盖（见 `config.py` 中 `AUDIT_*`）

## 常见问题

- **切章数为 0**：检查正文里是否为 `第N章 标题` 形式（章后须有空格或冒号再接标题）。
- **DeepSeek 连接失败**：增大 `API_MAX_RETRIES`、`API_HTTP_READ_TIMEOUT`；或换 `LLM_PROVIDER=doubao`。
- **换书后上下文串台**：删除本地 `story_context.json`、`runtime/`、`pruned_context_archive.json` 后重跑。
