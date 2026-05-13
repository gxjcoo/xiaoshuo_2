# 小说改编工具 - 核心改进总结

这不是「加个 Web UI」这种锦上添花的改进，而是解决了四个核心痛点。

---

## 📦 新增文件

| 文件 | 功能 |
|------|------|
| `structured_types.py` | 结构化类型定义：SceneNode, ChapterOutline, AuditFeedbackItem, StoryKnowledgeBase |
| `audit_enhanced.py` | 增强审计系统：可操作的 diff 反馈，plateau 检测 |
| `ai_trace_enhanced.py` | 增强 AI 痕迹检测：统计分布对比，而不只看表面规则 |
| `ai_handler.py` (更新) | 增加 `extract_structured_outline_from_reference` 和 `build_generation_prompt_from_outline` |

---

## 🎯 四个核心改进

### 1️⃣ 结构骨架：从文本 → 结构化 AST (P0)

**之前的问题：**
- 骨架是一段自然语言文本，格式不固定
- 解析不稳定，提取结果每次都不一样

**现在的方案：**
```python
# ChapterOutline 包含 SceneNode 列表
SceneNode = {
    node_type: "scene" | "dialogue" | "action" | ...,
    purpose: "这个场景的功能是什么",
    emotional_beat: "tension" | "humor" | ...,
    location: "...",
    characters: ["..."],
}
```

**如何使用：**
```python
from structured_types import ChapterOutline
from ai_handler import extract_structured_outline_from_reference

outline = extract_structured_outline_from_reference(reference_text, 1)
# outline.scenes 是结构化的场景列表
```

---

### 2️⃣ 审计反馈：从模糊评分 → 可操作的 diff (P0)

**之前的问题：**
- 「剧情连贯性不够」→ LLM 不知道怎么改
- 容易死循环：越改越差
- 没有 plateau 检测

**现在的方案：**
```python
AuditFeedbackItem = {
    feedback_type: "insert" | "rewrite" | "delete",
    dimension: "continuity" | "character_consistency",
    severity: "critical" | "major" | "minor",
    reason: "为什么需要改",
    location: "第 5 段后",
    target_text: "要改的原文",
    suggestion: "具体怎么改",
}
```

**如何使用：**
```python
from audit_enhanced import (
    run_enhanced_audit,
    build_revision_prompt,
    AuditHistory,
)

history = AuditHistory()
audit_result = run_enhanced_audit(generated_text, dimension_scores, history=history)

# audit_result.feedback_items 是具体的修改建议
prompt = build_revision_prompt(generated_text, audit_result)  # 生成修订提示词
```

---

### 3️⃣ 上下文管理：从摘要 → 知识库 (P1)

**之前的问题：**
- `story_context.json` 里 `protagonist_info.name` 还是 "Unknown"
- 没有实体归一（"宝寿道长" vs "年轻道士" vs "他"）
- 没有冲突追踪
- 没有角色状态机

**现在的方案：**
```python
StoryKnowledgeBase = {
    characters: {
        "宝寿道长": CharacterState {
            aliases: ["年轻道士", "他"],
            current_goal: "赚够钱建道观",
            current_emotion: "calm",
            relationships: { "小熊": "师徒" },
        }
    },
    active_conflicts: [Conflict {...}],
    key_items: {...},
    pending_hooks: [...],
}
```

**如何使用：**
```python
from structured_types import StoryKnowledgeBase, CharacterState

kb = StoryKnowledgeBase()
kb.add_character(CharacterState(name="宝寿道长"))
kb.add_hook("小熊似乎藏着什么秘密")
print(kb.to_context_prompt())  # 生成适合 LLM 的提示词
```

---

### 4️⃣ AI 痕迹检测：从规则 → 统计分布 (P1)

**之前的问题：**
- 只检测「这一刻」、「总之」等表面词汇
- 换个提示词就绕过了
- 检测不到更深层的模式：句子长度太均匀、段落长度太均匀等

**现在的方案：**
```python
# 检测统计分布：
# - 句子长度变异系数 (CV)：人类 > 0.5，AI 经常 < 0.4
# - 段落长度变异系数：人类 > 0.7，AI 经常 < 0.5
# - 过渡词密度
# - 情绪表达词汇密度
# - 对话比例
```

**如何使用：**
```python
from ai_trace_enhanced import (
    enhanced_ai_trace_analysis,
    format_ai_trace_report,
)

analysis = enhanced_ai_trace_analysis(generated_text)
print(format_ai_trace_report(analysis))
```

---

## 🚀 下一步：集成到主流程

这些新模块是向后兼容的，你可以逐步集成：

1. **第一步（可选）：** 在 `chapter_processor.py` 中加入结构化骨架提取的 fallback
2. **第二步（推荐）：** 用 `AuditHistory` 替换原来的简单循环
3. **第三步（长期）：** 逐步迁移到 `StoryKnowledgeBase`

---

## 💡 为什么这些是「核心改进」，而不是「锦上添花」

| 维度 | 之前 | 现在 |
|------|------|------|
| 骨架稳定性 | ❌ 每次提取都不一样 | ✅ 结构化，JSON Schema 强制 |
| 审计反馈 | ❌ 模糊评分 | ✅ 可操作的 diff |
| 上下文记忆 | ❌ 容易忘记角色设定 | ✅ 知识库，实体归一 |
| AI 痕迹检测 | ❌ 表面规则 | ✅ 统计分布分析 |

这些改进直接解决了「LLM 生成不稳定」、「审计死循环」、「生成到后面忘了前面」等核心痛点。
