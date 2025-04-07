# 小说风格模仿与续写工具

这是一个使用 DeepSeek API 的 Python 脚本，旨在模仿输入小说的整体风格，生成情节连贯的新故事章节。

## 功能

- **风格模仿**: 分析输入章节的写作风格（文笔、语气、节奏等）。
- **内容生成**: 基于分析出的风格，生成全新的小说内容。
- **章节连贯**: 在生成后续章节时，会将已生成的上一章内容作为上下文输入给 API，以确保故事的连续性。
- **批量处理**: 支持指定输入章节目录和输出目录，并处理指定范围的章节。

## 先决条件

- Python 3.x
- 安装所需的 Python 库：
  ```bash
  pip install -r requirements.txt
  ```
  (`requirements.txt` 应包含 `openai` 和 `httpx`)

## 配置

1.  **API 密钥**: 需要一个有效的 DeepSeek API 密钥。目前，密钥是硬编码在 `app.py` 文件顶部的 `API_KEY` 变量中。**请务必在使用前将其替换为您自己的密钥。**
    ```python
    # app.py
    API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # <--- 在这里替换
    ```
    _注意：将 API 密钥直接硬编码在脚本中存在安全风险，建议后续考虑使用环境变量或其他更安全的方式管理密钥。_

## 使用方法

通过命令行运行 `app.py` 脚本。

**参数说明:**

- `--input_dir`: 包含原始小说章节文件的目录路径 (例如，`1-50`，其中包含 `1.md`, `2.md`, ...)。
- `--output_dir`: 用于保存生成的新章节文件的目录路径 (例如，`output_chapters`)。如果目录不存在，脚本会自动创建。
- `--start_chapter`: 要开始生成的章节编号 (整数)。
- `--end_chapter`: 要结束生成的章节编号 (整数，包含此章节)。
- `--length`: (可选) 每个生成章节的大致目标字数 (默认为 3000)。实际字数可能因 API 返回而略有不同。

**示例:**

1.  **生成第 1 到 10 章，输出到 `output_chapters` 目录:**

    ```bash
    python app.py --input_dir 1-50 --output_dir output_chapters --start_chapter 1 --end_chapter 2 --length 4000
    ```

2.  **续写第 11 到 20 章 (假设 1-10 章已在 `output_chapters` 中):**
    ```bash
    python app.py --input_dir 1-50 --output_dir output_chapters --start_chapter 11 --end_chapter 20 --length 4000
    ```
    _(脚本会自动查找 `output_chapters/10.md` 作为第 11 章的上下文)_

## 辅助脚本

- **`rename_chapters.py`**: 用于将 `all/` 目录下的 Markdown 章节文件（文件名格式如 `第[章节号]章*.md`，章节号可以是中文或阿拉伯数字）重命名为 `[阿拉伯数字章节号].md`。

  ```bash
  python rename_chapters.py
  ```

- **`combine_chapters.py`**: 用于将指定目录（如 `output_chapters`）中的所有 `.md` 章节文件按顺序合并成一个单独的文件（默认为 `combined_novel_v2.md`）。

  ```bash
  python combine_chapters.py
  ```

- **`split_novel.py`**: (可选) 如果您的原始小说是一个单独的 `.txt` 文件，可以使用此脚本将其按章节（基于 "第...章" 格式的标题）拆分成多个独立的 `.md` 文件，方便后续 `app.py` 处理。
  - 需要手动修改脚本中的 `input_filepath` 和 `output_dir` 变量来指定输入的小说文件和输出目录。
  - 运行方式：
    ```bash
    python split_novel.py
    ```

## 注意事项

- 生成长篇内容和多个章节需要较长时间，并会消耗相应的 API 配额。
- 生成内容的质量和连贯性依赖于 DeepSeek API 的能力以及提示词的设计。
- 如果原始章节之间的风格/内容差异过大，AI 在同时模仿风格和续写情节时可能会遇到困难，导致连贯性下降或风格漂移。
