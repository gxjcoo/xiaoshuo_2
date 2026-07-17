"""参考章文风分析。"""

from config import (
    STYLE_ANALYSIS_MODEL,
    STYLE_ANALYSIS_MAX_TOKENS,
    STYLE_ANALYSIS_TEMPERATURE,
    MAX_CHAPTER_CONTENT_LENGTH,
)

from .client import call_deepseek_api


def analyze_writing_style(text_sample):
    """使用 AI 分析文本的语言风格"""
    print("正在分析原始章节的语言风格...")

    if not text_sample:
        print("错误: 提供的文本样本为空，无法分析风格。")
        return "未能分析出风格，原始文本可能为空。"

    limited_sample = text_sample[:MAX_CHAPTER_CONTENT_LENGTH]

    prompt = (
        f"请对以下**参考原文**（用于同结构改编的风格参照）做全面分析，使后续输出在语气、节奏与笔法上与原作同调；"
        f"分析服务于「同结构改编」而非「另写新故事」。分析需涵盖以下几个关键维度：\n\n"
        f"1. **语言风格细节**：\n"
        f"   - 语气和基调：文本的情感色彩和总体氛围（庄重、轻松、紧张、诙谐等）\n"
        f"   - 句法结构：句子长短、复杂度，常用句式模式，有无特殊断句或排版特点\n"
        f"   - 词汇选择：专业术语、俚语、方言、成语使用频率，是否有特定词汇偏好\n"
        f"   - 修辞手法：常用的修辞技巧（比喻、夸张、拟人等）及其具体表现方式\n"
        f"   - 叙述视角：视角选择（第一/三人称等）及视角转换模式\n"
        f"\n2. **叙事结构特点**：\n"
        f"   - 章节组织：章节长度、内部段落结构、章节间的过渡方式\n"
        f"   - 情节节奏：快慢变化、紧张与舒缓的交替模式\n"
        f"   - 叙事技巧：闪回、伏笔、悬念等技巧的使用频率和方式\n"
        f"\n3. **对话与内心独白**：\n"
        f"   - 对话风格：对话的长短、节奏、口语化程度\n"
        f"   - 内心独白：内心活动的表达方式和频率\n"
        f"   - 角色语言：不同角色的语言特点区分\n"
        f"\n4. **环境与氛围描写**：\n"
        f"   - 场景描写：场景细节的呈现方式和详略取舍\n"
        f"   - 氛围营造：通过何种感官描写和语言手段营造氛围\n"
        f"\n5. **主题与情感基调**：\n"
        f"   - 核心主题：文本传达的核心思想或情感\n"
        f"   - 情感表达：喜怒哀乐等情感的表达方式和强度\n\n"
        f"原始文本样本：\n\n{limited_sample}\n\n"
        f"请提供详细分析，确保捕捉到原文的独特风格特征；分析应足够具体，能指导**同结构改编**时的遣词与节奏（不要求复用原实体名）。\n\n"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是一位精通文学分析的专家，擅长从参考文本中提取同结构改编所需的语言风格、叙事节奏与表达习惯；"
                "你的输出将用于「同结构改编」而非创作新故事大纲。"
            ),
        },
        {"role": "user", "content": prompt},
    ]

    try:
        style_analysis = call_deepseek_api(
            messages,
            STYLE_ANALYSIS_MODEL,
            max_tokens=STYLE_ANALYSIS_MAX_TOKENS,
            temperature=STYLE_ANALYSIS_TEMPERATURE,
            task_label="参考章文风分析",
        )

        if not style_analysis:
            print("警告: 调用 AI 分析风格失败。返回默认风格描述。")
            return "未能分析出风格，将使用默认风格。中性叙事风格，具体特征需根据原文分析。"

        print("风格分析完成。")
        return style_analysis

    except Exception as e:
        print(f"分析风格时发生错误: {e}")
        return "未能分析出风格，将使用默认风格。中性叙事风格，具体特征需根据原文分析。"
