import json

from config import CHAPTER_GENERATION_MODEL, CONTEXT_ANALYSIS_MODEL
from ai_handler import call_deepseek_api


def extract_domain_updates(chapter_content, current_context):
    """提取应写入 story_domain 的增量信息。"""
    context_json = json.dumps(current_context, ensure_ascii=False, indent=2)
    prompt = (
        "请从章节内容中提取可沉淀到故事领域文档的增量信息，输出 JSON。\n"
        "JSON 结构必须是：\n"
        "{\n"
        '  "glossary": [string],\n'
        '  "world": [string],\n'
        '  "characters": [string],\n'
        '  "voice": [string]\n'
        "}\n"
        "规则：\n"
        "- 只提取明确出现且长期有价值的信息。\n"
        "- 每条尽量短，避免重复。\n"
        "- 不要编造。\n\n"
        f"【当前上下文】\n{context_json}\n\n"
        f"【章节正文】\n{chapter_content[:9000]}"
    )
    messages = [
        {"role": "system", "content": "你是小说知识库维护助手，输出必须是合法 JSON。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=900,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    if not raw:
        return {"glossary": [], "world": [], "characters": [], "voice": []}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {"glossary": [], "world": [], "characters": [], "voice": []}

    def _clean_list(key):
        vals = parsed.get(key, [])
        if not isinstance(vals, list):
            return []
        return [v.strip() for v in vals if isinstance(v, str) and v.strip()]

    return {
        "glossary": _clean_list("glossary"),
        "world": _clean_list("world"),
        "characters": _clean_list("characters"),
        "voice": _clean_list("voice"),
    }
