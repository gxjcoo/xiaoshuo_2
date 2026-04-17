# 小说处理项目说明

这是一个用于小说章节处理与生成的 Python 项目，当前包含两类常用能力：

- 章节拆分：把一个长篇 `txt` 按章节自动切分为多个 `md` 文件
- 章节生成主流程：基于输入章节，按设定生成输出章节（`app.py`）

## 1. 环境准备

建议使用 Python 3.10+（推荐 3.12）。

在项目根目录执行：

```bash
pip install -r requirements.txt
```

## 2. 项目主要文件

- `split_novel.py`：章节拆分脚本
- `app.py`：章节处理/生成主入口
- `1.txt`：示例原始小说文本
- `all/`：默认章节拆分输出目录
- `output_chapters/`：常见生成输出目录（按你的参数可调整）

## 3. 章节拆分（split_novel.py）

### 默认用法

```bash
python split_novel.py
```

默认行为：

- 读取：`1.txt`
- 输出到：`all/`
- 文件名为连续编号：`1.md`、`2.md`、`3.md`...

### 当前识别规则说明

脚本会识别类似以下章节标题（支持行首和行内）：

- `第1章 xxx`
- `第十二章 xxx`
- `第3回：xxx`
- `第4节 xxx`

并且已经避免把普通正文句子（如“第一回的结尾……”）误判为新章节。

### 自定义输入/输出（可改脚本末尾）

在 `split_novel.py` 末尾修改：

```python
if __name__ == "__main__":
    input_file = "1.txt"
    output_directory = "all"
    split_novel_to_chapters(input_file, output_directory)
```

## 4. 启动主流程（app.py）

### 基础运行

```bash
python app.py --input_dir 1-50 --output_dir output_chapters
```

### 第1章到第10章

```bash
python app.py --input_dir all --output_dir output_chapters --start_chapter 1 --end_chapter 10
```

### 常用参数

- `--chapter 10`：只处理第 10 章
- `--start_chapter 1 --end_chapter 20`：处理范围章节
- `--length 3000`：控制目标字数
- `--no_strict_source_plot`：关闭严格仿写（实验模式）

示例：

```bash
python app.py --input_dir 1-50 --output_dir output_chapters --chapter 1 --length 2500
```

## 5. 推荐工作流

1. 先用 `split_novel.py` 把 `txt` 切成章节 `md`
2. 检查切分结果（如 `all/1.md`、`all/2.md`）
3. 选择章节目录作为 `app.py` 的 `--input_dir`
4. 运行生成流程并检查 `--output_dir` 结果

## 6. 常见问题

- 输出结果乱码：通常是终端编码显示问题，文件本身一般正常
- 拆分数量异常：先检查原文章节标题格式是否规范
- 某一章未识别：可提供原文片段，按实际格式补充识别规则


https://matrix.tencent.com/ai-detect/ai_gen_txt