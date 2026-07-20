# 工具脚本目录

本目录包含用于检查、修复和测试生成章节的辅助脚本。

## 检查脚本

| 脚本 | 用途 |
|------|------|
| `check_all_chapters.py` | 全面检查所有100章，检测标题格式、三尺青锋错误、重复文本、修订说明等问题 |

## 测试脚本

| 脚本 | 用途 |
|------|------|
| `test_dag_structure.py` | 测试DAG结构相关功能 |

## 状态检查脚本

| 脚本 | 用途 |
|------|------|
| `check_intent.py` | 检查生成意图 |
| `check_progress.py` | 检查生成进度 |
| `check_result.py` | 检查生成结果 |
| `fix_state.py` | 修复状态文件 |

## 日志与报告

| 文件 | 用途 |
|------|------|
| `chapter_check_report.txt` | 章节检查报告（由 `check_all_chapters.py` 生成） |
| `fix_log.txt` | 修复操作日志 |

## 使用方法

```bash
# 全面检查所有章节
python scripts/check_all_chapters.py

# 检查生成进度
python scripts/check_progress.py
```

## 注意事项

- 这些脚本主要用于开发调试和质量检查
- 修复脚本会直接修改 `output_chapters/` 中的文件，建议先备份
- 检查报告会保存在 `scripts/` 目录下
