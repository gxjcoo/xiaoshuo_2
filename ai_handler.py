import httpx
import json
import re
import time
import openai

# 从 config 模块导入配置
from config import (
    LLM_PROVIDER,
    API_KEY,
    BASE_URL,
    API_HTTP_CONNECT_TIMEOUT,
    API_HTTP_READ_TIMEOUT,
    STYLE_ANALYSIS_MODEL,
    CHAPTER_GENERATION_MODEL,
    CONTEXT_ANALYSIS_MODEL,
    CONTEXT_ANALYSIS_MAX_TOKENS,
    CONTEXT_ANALYSIS_TEMPERATURE,
    STYLE_ANALYSIS_MAX_TOKENS,
    STYLE_ANALYSIS_TEMPERATURE,
    CHAPTER_GENERATION_TEMPERATURE,
    MAX_CHAPTER_CONTENT_LENGTH,
    VOLUME_CHAPTER_SIZE,
    DEBUG_LLM_LOG,
    DEBUG_LLM_PREVIEW_CHARS,
    DOUBAO_USE_RESPONSES_API,
)

def _preview_text(text, limit=600):
    if not isinstance(text, str):
        return ""
    cleaned = text.replace("\r", " ").replace("\n", "\\n")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "...(truncated)"


def _debug_log_request(model, messages, temperature, max_tokens, response_format=None):
    if not DEBUG_LLM_LOG:
        return
    print(
        f"[LLM DEBUG] sending model={model} temperature={temperature} max_tokens={max_tokens} response_format={response_format}",
        flush=True,
    )
    if not isinstance(messages, list):
        print(f"[LLM DEBUG] messages={_preview_text(str(messages), DEBUG_LLM_PREVIEW_CHARS)}", flush=True)
        return
    for idx, msg in enumerate(messages, start=1):
        role = msg.get("role", "unknown") if isinstance(msg, dict) else "unknown"
        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
        if not isinstance(content, str):
            content = str(content)
        print(
            f"[LLM DEBUG] message[{idx}] role={role} content={_preview_text(content, DEBUG_LLM_PREVIEW_CHARS)}",
            flush=True,
        )


def _brief_style_for_generation(writing_style, max_chars=1100):
    """风格分析往往带 Markdown 条目，直接全文注入易诱发「分析腔/清单体」正文。"""
    if not isinstance(writing_style, str) or not writing_style.strip():
        return "（风格备忘缺失：保持口语、松紧交替，少用抽象收束句。）"
    s = writing_style.strip()
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 24].rstrip() + "\n…(备忘已截断；禁止模仿其中小标题、编号与排比结构。)"


def _reference_prose_snippet(text, max_chars=2600):
    """截取参考原文供对齐语感；避免只喂分析报告导致写法「像写论文」。"""
    if not isinstance(text, str) or not text.strip():
        return ""
    s = text.strip()
    if len(s) <= max_chars:
        return s
    head = s[: max_chars - 320]
    tail = s[-280:]
    return f"{head.rstrip()}\n\n…(参考原文中部已省略)…\n\n{tail.lstrip()}"


def extract_plot_outline_from_reference(reference_chapter_text, chapter_number, strict_source_plot=True):
    """从参考章抽取结构骨架，供生成阶段使用，避免直接贴原文导致高相似。"""
    if not isinstance(reference_chapter_text, str) or not reference_chapter_text.strip():
        return ""

    ref_text = _reference_prose_snippet(reference_chapter_text, max_chars=6200)
    prompt = (
        f"请把第 {chapter_number} 章参考原文抽取成“结构功能骨架”，输出 JSON。\n"
        "目标：后续作者会基于骨架做同结构改编，不会看到原文全文。\n"
        "必须保留事件功能、冲突功能、因果位置和结尾功能，但不要复写原文句子，也不要把原文实体名视为必须保留。\n\n"
        "JSON 字段：\n"
        "{\n"
        '  "chapter_goal": string,\n'
        '  "scene_beats": [string],\n'
        '  "character_motives": [string],\n'
        '  "must_keep_facts": [string],\n'
        '  "causal_chain": [string],\n'
        '  "ending_state": string,\n'
        '  "do_not_change": [string]\n'
        "}\n\n"
        "规则：\n"
        "- scene_beats 按原文事件顺序列 5-10 条，每条只写事实，不写原文修辞。\n"
        "- must_keep_facts 只放改变结构功能会出错的信息点，避免把可改名的人名/地名当成硬约束。\n"
        "- 不要摘抄连续 12 个字以上的原文表达。\n"
        "- 不要输出正文、标题、修辞点评或 Markdown。\n"
        f"- 当前模式：{'严格结构适配' if strict_source_plot else '结构主干适配'}。\n\n"
        f"【参考原文】\n{ref_text}"
    )
    messages = [
        {"role": "system", "content": "你是小说结构拆解编辑，只抽取叙事功能、事件功能和因果位置，不复写原文句子。输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=1600,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return raw.strip()
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        return raw.strip()


def _slim_context_for_generation(current_context, writing_chapter_number=None):
    """生成侧瘦身：完整 JSON 易诱发按 pending_hooks/设定清单扩写。

    writing_chapter_number: 本次正在生成的章节号；用于消解 last_generated_chapter 被误读为「下一章」。
    """
    if not isinstance(current_context, dict):
        return {}
    pi = current_context.get("protagonist_info") or {}
    ws = current_context.get("world_setting") or {}
    slim_pi = {}
    if isinstance(pi, dict):
        slim_pi = {
            "name": pi.get("name"),
            "description": (pi.get("description") or "")[:220],
            "status_summary": (pi.get("status_summary") or "")[:300],
        }
        items = pi.get("key_items_abilities")
        if isinstance(items, list):
            slim_pi["key_items_abilities"] = [str(x)[:90] for x in items[:5]]
        rel = pi.get("key_relationships")
        if isinstance(rel, dict):
            keys = list(rel.keys())[:6]
            slim_pi["key_relationships"] = {k: str(rel[k])[:110] for k in keys}
    slim_ws = {}
    if isinstance(ws, dict):
        slim_ws = {
            "description": (ws.get("description") or "")[:220],
            "location": (ws.get("location") or "")[:220],
        }
        el = ws.get("key_elements")
        if isinstance(el, list):
            slim_ws["key_elements"] = [str(x)[:100] for x in el[:6]]
    hooks = current_context.get("pending_hooks") or []
    if isinstance(hooks, list):
        hooks = [str(h)[:120] for h in hooks[-8:]]
    else:
        hooks = []
    out = {
        "last_generated_chapter": current_context.get("last_generated_chapter", 0),
        "protagonist_info": slim_pi,
        "world_setting": slim_ws,
        "recent_plot_summary": (current_context.get("recent_plot_summary") or "")[:450],
        "pending_hooks": hooks,
    }
    if writing_chapter_number is not None:
        out["本次须输出的章节号"] = int(writing_chapter_number)
        out["_说明"] = (
            "last_generated_chapter 仅表示 story_context.json 里上次落盘更新过的章节号，"
            "重跑同一章时可能与「本次须输出的章节号」相同；标题与正文中的章号必须与「本次须输出的章节号」一致，禁止自增成下一章。"
        )
    return out


def _chapter_completion_max_tokens(target_length):
    """中文正文约 1.5–2 token/字；target_length 为期望字数时不可把 max_tokens 当字数用。"""
    try:
        n = int(target_length)
    except Exception:
        n = 3000
    return max(2048, int(n * 2.2) + 512)


def _normalize_title_subtitle(text, max_len=18):
    """清洗副标题文本，避免过长或包含不适合作为标题的符号。"""
    if not isinstance(text, str):
        return ""
    s = text.strip()
    s = re.sub(r"^#+\s*", "", s)
    s = re.sub(r"^第\s*\d+\s*[章节回]\s*", "", s)
    s = s.replace("：", " ").replace(":", " ")
    s = re.sub(r"[`*_~\[\]\(\){}<>|\\\/]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .。!！?？,，;；-—")
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def _fallback_subtitle_from_content(chapter_content):
    """AI 取题失败时，用正文首句兜底生成副标题。"""
    if not isinstance(chapter_content, str):
        return "未命名"
    lines = [ln.strip() for ln in chapter_content.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return "未命名"
    first = lines[0]
    first = re.split(r"[。！？!?；;]", first)[0]
    first = _normalize_title_subtitle(first, max_len=16)
    return first or "未命名"


def _fallback_subtitle_from_reference(reference_chapter_text, chapter_number):
    """从参考原文章节首行提取副标题作为兜底。"""
    if not isinstance(reference_chapter_text, str) or not reference_chapter_text.strip():
        return ""
    lines = [ln.strip() for ln in reference_chapter_text.splitlines() if ln.strip()]
    if not lines:
        return ""

    first_line = lines[0]
    m = re.match(
        r"^#?\s*第\s*[零〇一二三四五六七八九十百千万两\d]+\s*[章节回]\s*(.*)$",
        first_line,
    )
    if m:
        subtitle = _normalize_title_subtitle(m.group(1), max_len=18)
        if subtitle:
            return subtitle

    # 若首行不规范，尝试在前几行里找“第X章/回/节 标题”
    search_pool = " ".join(lines[:5])
    m2 = re.search(
        r"第\s*[零〇一二三四五六七八九十百千万两\d]+\s*[章节回]\s*(?:[:：]\s*|\s+)([^\n\r]{1,30})",
        search_pool,
    )
    if m2:
        subtitle = _normalize_title_subtitle(m2.group(1), max_len=18)
        if subtitle:
            return subtitle
    return ""


def generate_title_from_chapter_content(chapter_number, chapter_content, reference_chapter_text=""):
    """根据章节正文生成更贴合内容的副标题。"""
    snippet = (chapter_content or "")[:2600]
    if not snippet.strip():
        ref_subtitle = _fallback_subtitle_from_reference(reference_chapter_text, chapter_number)
        return f"第{chapter_number}章 {ref_subtitle or '未命名'}"

    prompt = (
        f"请基于以下小说正文内容，为第{chapter_number}章拟一个中文章节副标题。\n"
        "要求：\n"
        "1) 只输出副标题文本，不要输出“第X章”、井号、引号、解释。\n"
        "2) 8-16个汉字为宜，尽量具体，贴合本章核心冲突/转折。\n"
        "3) 不要使用“故事继续/新的开始/风云再起”等空泛套话。\n\n"
        f"正文片段：\n{snippet}"
    )
    messages = [
        {"role": "system", "content": "你是网络小说编辑，擅长根据章节内容拟标题，要求具体、有记忆点。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        CHAPTER_GENERATION_MODEL,
        max_tokens=80,
        temperature=0.4,
    )
    subtitle = _normalize_title_subtitle(raw or "", max_len=18)
    if not subtitle:
        subtitle = _fallback_subtitle_from_reference(reference_chapter_text, chapter_number)
    if not subtitle:
        subtitle = _fallback_subtitle_from_content(chapter_content)
    return f"第{chapter_number}章 {subtitle}"


def _looks_like_meta_reasoning(text):
    """识别“用户现在需要…”这类元推理开头，避免污染下游审计/生成流程。"""
    if not isinstance(text, str):
        return False
    s = text.strip()
    if not s:
        return False
    head = s[:120]
    bad_prefixes = (
        "用户现在需要",
        "用户需要我",
        "我现在需要",
        "首先得",
        "首先先",
        "先看",
        "我们先",
    )
    if any(head.startswith(p) for p in bad_prefixes):
        return True
    # 常见“思维过程”提示词
    if ("对吧" in head or "先理清楚" in head) and ("用户" in head):
        return True
    return False


def _debug_log_response(path_label, model, content, extra=""):
    if not DEBUG_LLM_LOG:
        return
    preview = _preview_text(content or "", DEBUG_LLM_PREVIEW_CHARS)
    size = len(content or "")
    suffix = f" {extra}" if extra else ""
    print(f"[LLM DEBUG] path={path_label} model={model} chars={size}{suffix}", flush=True)
    print(f"[LLM DEBUG] preview={preview}", flush=True)


def _call_openai_chat_api(messages, model, timeout, max_tokens=None, temperature=0.7, response_format=None, path_label="openai.chat.completions"):
    with httpx.Client(timeout=timeout) as http_client:
        if DEBUG_LLM_LOG:
            print(f"[LLM DEBUG] processing path={path_label} endpoint={BASE_URL.rstrip('/')}/chat/completions", flush=True)
        client = openai.OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
            http_client=http_client,
        )
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format
        response = client.chat.completions.create(**kwargs)
        content = (response.choices[0].message.content or "").strip()
        _debug_log_response(path_label, model, content)
        return content


def _extract_text_from_ark_response(data):
    """从 Ark /responses 返回中尽量提取纯文本。"""
    if isinstance(data, dict):
        if isinstance(data.get("output_text"), str) and data.get("output_text", "").strip():
            return data["output_text"].strip()

        output = data.get("output")
        if isinstance(output, list):
            chunks = []
            reasoning_chunks = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "reasoning":
                    summary = item.get("summary")
                    if isinstance(summary, list):
                        for s in summary:
                            if isinstance(s, dict):
                                t = s.get("text") or s.get("summary_text")
                                if isinstance(t, str) and t.strip():
                                    reasoning_chunks.append(t.strip())
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        text = c.get("text")
                        if isinstance(text, str) and text.strip():
                            chunks.append(text.strip())
            if chunks:
                return "\n".join(chunks).strip()
            # 兜底：当模型只返回 reasoning summary 且被截断时，至少返回可用文本
            if reasoning_chunks:
                return "\n".join(reasoning_chunks).strip()
    return ""


def _call_ark_responses_api(messages, model, timeout, max_tokens=None, temperature=0.7):
    """调用豆包 Ark /responses 接口。"""
    input_payload = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        input_payload.append({
            "role": role,
            "content": [{"type": "input_text", "text": content}],
        })

    payload = {
        "model": model,
        "input": input_payload,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_output_tokens"] = int(max_tokens)

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    endpoint = f"{BASE_URL.rstrip('/')}/responses"
    if DEBUG_LLM_LOG:
        print(f"[LLM DEBUG] processing path=ark.responses endpoint={endpoint}", flush=True)

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(endpoint, headers=headers, json=payload)
        if resp.status_code == 404:
            # 某些 Ark 环境未开通 /responses，回退到 OpenAI 兼容 chat.completions
            raise FileNotFoundError("Ark /responses endpoint not available")
        resp.raise_for_status()
        data = resp.json()
        text = _extract_text_from_ark_response(data)
        if text:
            _debug_log_response("ark.responses", model, text, extra=f"status={resp.status_code}")
            return text
        raise RuntimeError(f"Ark 返回中未提取到文本: {str(data)[:600]}")


def _effective_response_format(response_format):
    """豆包 Ark 多数 chat.completions 模型不支持 response_format=json_object，会返回 400。"""
    if response_format is None:
        return None
    if LLM_PROVIDER != "doubao":
        return response_format
    if isinstance(response_format, dict) and response_format.get("type") == "json_object":
        if DEBUG_LLM_LOG:
            print(
                "[LLM DEBUG] doubao: 不传 response_format=json_object，改由提示词约束+解析 JSON",
                flush=True,
            )
        return None
    return response_format


def call_deepseek_api(messages, model, max_tokens=None, temperature=0.7, response_format=None):
    """调用 LLM 的通用函数（DeepSeek / 豆包 Ark）。"""
    response_format = _effective_response_format(response_format)
    timeout = httpx.Timeout(
        connect=API_HTTP_CONNECT_TIMEOUT,
        read=API_HTTP_READ_TIMEOUT,
        write=API_HTTP_CONNECT_TIMEOUT,
        pool=API_HTTP_CONNECT_TIMEOUT,
    )

    retries = 3
    delay = 5
    last_exception = None

    for attempt in range(retries):
        try:
            print(
                f"API 请求 (尝试 {attempt + 1}/{retries}): 模型={model}, 温度={temperature}, "
                f"读超时={API_HTTP_READ_TIMEOUT}s",
                flush=True,
            )
            _debug_log_request(model, messages, temperature, max_tokens, response_format=response_format)
            print(
                "  → 等待服务端响应中（网络慢或模型排队时可能需一至数分钟，并非死机）…",
                flush=True,
            )

            if LLM_PROVIDER == "doubao":
                if DOUBAO_USE_RESPONSES_API:
                    try:
                        content = _call_ark_responses_api(
                            messages=messages,
                            model=model,
                            timeout=timeout,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                    except FileNotFoundError:
                        if DEBUG_LLM_LOG:
                            print("[LLM DEBUG] ark.responses unavailable, fallback -> chat.completions", flush=True)
                        content = _call_openai_chat_api(
                            messages=messages,
                            model=model,
                            timeout=timeout,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            response_format=response_format,
                            path_label="ark.chat.completions(fallback)",
                        )
                else:
                    content = _call_openai_chat_api(
                        messages=messages,
                        model=model,
                        timeout=timeout,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        response_format=response_format,
                        path_label="ark.chat.completions",
                    )
            else:
                content = _call_openai_chat_api(
                    messages=messages,
                    model=model,
                    timeout=timeout,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format=response_format,
                    path_label="openai.chat.completions",
                )

            # 审计前/生成前防污染：拦截“元推理”文本并触发立即重试
            if _looks_like_meta_reasoning(content):
                if DEBUG_LLM_LOG:
                    print("[LLM DEBUG] invalid meta-reasoning response detected, force retry", flush=True)
                    print(f"[LLM DEBUG] meta_preview={_preview_text(content, DEBUG_LLM_PREVIEW_CHARS)}", flush=True)
                raise RuntimeError("模型返回了元推理文本（如“用户现在需要…”），已判定为无效响应")

            return content

        except Exception as e:
            last_exception = e
            print(f"请求失败 (尝试 {attempt + 1}/{retries}): {str(e)}", flush=True)
            if attempt < retries - 1:
                print(f"将在 {delay} 秒后重试...", flush=True)
                time.sleep(delay)
                delay *= 2
            else:
                print(f"已达到最大重试次数 ({retries})，请求失败。", flush=True)

    if last_exception:
        print(f"所有 API 调用尝试均失败。最后的错误: {str(last_exception)}", flush=True)
    return None

def analyze_writing_style(text_sample):
    """使用 AI 分析文本的语言风格"""
    print("正在分析原始章节的语言风格...")
    
    # 限制发送到 API 的样本大小
    if not text_sample:
        print("错误: 提供的文本样本为空，无法分析风格。")
        return "未能分析出风格，原始文本可能为空。"
        
    limited_sample = text_sample[:MAX_CHAPTER_CONTENT_LENGTH]

    # 使用针对风格分析优化的提示词
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
        {"role": "user", "content": prompt}
    ]
    
    try:
        # 使用通用 API 调用函数
        style_analysis = call_deepseek_api(
            messages, 
            STYLE_ANALYSIS_MODEL, 
            max_tokens=STYLE_ANALYSIS_MAX_TOKENS, 
            temperature=STYLE_ANALYSIS_TEMPERATURE
        )
        
        if not style_analysis:
            print("警告: 调用 AI 分析风格失败。返回默认风格描述。")
            return "未能分析出风格，将使用默认风格。文本应当保持轻松幽默的基调，使用生动形象的比喻和适度的夸张手法。"
            
        print("风格分析完成。")
        return style_analysis
        
    except Exception as e:
        print(f"分析风格时发生错误: {e}")
        return "未能分析出风格，将使用默认风格。文本应当保持轻松幽默的基调，使用生动形象的比喻和适度的夸张手法。"


def plan_chapter_with_ai(
    current_context,
    target_chapter_number,
    previous_chapter_content=None,
    next_chapter_preview="",
    author_intent_text="",
    current_focus_text="",
    reference_chapter_text="",
    strict_source_plot=False,
):
    """生成本章意图规划（短文本），用于约束正文生成焦点。"""
    context_json = json.dumps(current_context, ensure_ascii=False, indent=2)
    previous_tail = (previous_chapter_content or "")[-1200:]
    next_head = (next_chapter_preview or "")[:1600]
    ref_snip = ""
    strict_head = ""
    if strict_source_plot and (reference_chapter_text or "").strip():
        ref_snip = _reference_prose_snippet(reference_chapter_text, max_chars=4200)
        strict_head = (
            "【模式：严格结构适配，表达与实体去同构】\n"
            "本章意图必须能从「本章参考原文节选」中推导：只拆解已有场景功能、冲突功能与信息点，写成可执行改编点；"
            "不得新增参考原文里不存在的关键结构功能、不得改因果位置与结局功能。"
            "不要摘抄原文句子，不要把原文段落节奏写成计划。\n"
            "若与【作者长期意图】【近期焦点】或 JSON 上下文冲突，一律以参考原文为准，其余仅作语气参考。\n\n"
            f"【本章参考原文节选（意图规划唯一情节依据）】\n```\n{ref_snip}\n```\n\n"
        )
    prompt = (
        f"{strict_head}"
        f"【章节号】你正在为第 {target_chapter_number} 章列写作意图；不得把对象误写成第 {target_chapter_number + 1} 章。\n\n"
        f"你是小说章节规划师。请为第 {target_chapter_number} 章输出一份简洁可执行的写作意图。\n\n"
        f"输出要求：\n"
        f"1) 只输出纯文本，不要 Markdown 表格。\n"
        f"2) 控制在 8 条以内，每条一句话。\n"
        f"3) 至少包含：主线推进、角色变化、关键冲突、伏笔/回收点。\n"
        f"4) 不得与既有设定冲突，不得新增未铺垫的大设定。\n"
        f"5) 用自然语言短句列出即可，不要写成正文片段或带编号的小标题目录。\n\n"
        f"【当前上下文】\n{context_json}\n\n"
        f"【上一章结尾（衔接用，可选）】\n{previous_tail if previous_tail else '无'}\n\n"
        f"【下一章开头（本章结尾硬约束，可选）】\n{next_head if next_head else '无'}\n\n"
        f"【作者长期意图（可选）】\n{author_intent_text if author_intent_text else '无'}\n\n"
        f"【近期焦点（可选）】\n{current_focus_text if current_focus_text else '无'}\n"
    )
    system_msg = "你擅长把「同结构改编」任务拆成可执行写作点：只拆解参考里的结构功能，不发明新主线，也不复刻原文表达和实体体系。"
    if strict_source_plot and ref_snip:
        system_msg += " 当前为严格结构适配：意图必须与参考原文场次功能一一对应，不得添加参考中不存在的关键功能，但表达结构和实体体系要为后续改编留出距离。"
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]
    plan_text = call_deepseek_api(messages, CHAPTER_GENERATION_MODEL, max_tokens=800, temperature=0.3)
    if not plan_text:
        return ""
    return plan_text.strip()


def analyze_hooks_and_volume_update(current_context, chapter_content, chapter_number):
    """提取本章 hooks 变更，并在分卷节点产出卷摘要。"""
    context_slice = {
        "pending_hooks": current_context.get("pending_hooks", [])[-20:],
        "recent_chapter_summaries": current_context.get("recent_chapter_summaries", [])[-8:],
        "last_generated_chapter": current_context.get("last_generated_chapter", 0),
    }
    volume_boundary = (chapter_number % VOLUME_CHAPTER_SIZE == 0)
    prompt = (
        "你是小说连载状态维护助手。请基于当前章节与既有未回收线索，输出 JSON。\n"
        "字段要求：\n"
        '1) "new_hooks": 本章新增且应保留到后文的线索数组（字符串）\n'
        '2) "resolved_hooks": 本章明确回收/兑现的旧线索数组（字符串）\n'
        '3) "volume_summary": 仅当到达分卷边界时输出该卷摘要，否则输出空字符串\n'
        "规则：\n"
        "- 只提取文本中明确存在的线索，不要脑补。\n"
        "- 用短语表达线索，避免整句复述。\n"
        f"- 当前章节号: {chapter_number}，分卷边界: {'是' if volume_boundary else '否'}。\n\n"
        f"【当前状态片段】\n{json.dumps(context_slice, ensure_ascii=False, indent=2)}\n\n"
        f"【本章内容】\n{chapter_content[:7000]}"
    )
    messages = [
        {"role": "system", "content": "你擅长抽取连载线索状态并维护分卷摘要，输出必须是合法 JSON 对象。"},
        {"role": "user", "content": prompt},
    ]
    result_text = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=1200,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    if not result_text:
        return {"new_hooks": [], "resolved_hooks": [], "volume_summary": ""}

    try:
        parsed = json.loads(result_text)
        if not isinstance(parsed, dict):
            return {"new_hooks": [], "resolved_hooks": [], "volume_summary": ""}
        return {
            "new_hooks": [x for x in parsed.get("new_hooks", []) if isinstance(x, str) and x.strip()],
            "resolved_hooks": [x for x in parsed.get("resolved_hooks", []) if isinstance(x, str) and x.strip()],
            "volume_summary": parsed.get("volume_summary", "").strip() if isinstance(parsed.get("volume_summary", ""), str) else "",
        }
    except Exception:
        return {"new_hooks": [], "resolved_hooks": [], "volume_summary": ""}

def generate_chapter_content(
    current_context,
    writing_style,
    target_length,
    previous_chapter_content=None,
    next_chapter_preview="",
    target_chapter_number=None,
    domain_text="",
    chapter_plan_text="",
    author_intent_text="",
    current_focus_text="",
    audit_requirements_text="",
    reference_chapter_text="",
    reference_plot_outline="",
    strict_source_plot=False,
    prev_chapter_end="",
    next_chapter_start="",
):
    """使用 AI 生成新的章节内容。

    domain_text: 领域圣经（DDD），静态设定与统一说法。
    reference_chapter_text: 输入目录参考章原文（仅用于标题兜底；生成阶段不直接注入正文片段）。
    reference_plot_outline: 从参考章提取的结构功能骨架，用于代替原文片段以降低相似度。
    strict_source_plot: 结构功能以参考章为准，衔接上一章优先原作（由调用方传入 previous 内容）。
    """
    if target_chapter_number is None:
        chapter_number = current_context.get("last_generated_chapter", 0) + 1
    else:
        chapter_number = target_chapter_number

    # 构建当前故事背景摘要
    rolling_summaries = current_context.get("recent_chapter_summaries", [])
    if isinstance(rolling_summaries, list) and rolling_summaries:
        rolling_text = "\n".join(
            f"- 第{item.get('chapter', '?')}章：{(item.get('summary', '') or '')[:160]}"
            for item in rolling_summaries[-8:]
            if isinstance(item, dict)
        ).strip()
    else:
        rolling_text = ""

    slim_ctx = _slim_context_for_generation(current_context, writing_chapter_number=chapter_number)
    chapter_number_guard = (
        f"【章节编号（硬约束）】\n"
        f"你必须写且仅写「第 {chapter_number} 章」：第一行标题必须是 `# 第{chapter_number}章`（阿拉伯数字与「章」之间无空格亦可）加空格加副题。\n"
        f"禁止因 JSON 中出现 last_generated_chapter、滚动摘要或其它字段而自行把章号加一（例如已记录到第 1 章却仍要求你写第 1 章时，不得写成第 2 章）。\n\n"
    )
    current_context_summary = (
        f"{chapter_number_guard}"
        "【故事状态（生成侧已压缩，勿逐条扩写成目录式正文）】\n"
        f"{json.dumps(slim_ctx, ensure_ascii=False, indent=2)}\n"
        f"最近章节滚动记忆：\n{rolling_text if rolling_text else '无'}\n"
        f"分卷摘要：{(current_context.get('volume_summaries') or [])[-2:]}"
    )

    style_brief = _brief_style_for_generation(writing_style)
    next_head = (next_chapter_preview or "")[:1800].strip()
    reference_block = ""
    if reference_plot_outline:
        reference_block = (
            "【本章结构功能骨架（由参考章抽取；生成正文只能依据这些结构功能，不得复刻参考原文表达或实体体系）】\n"
            f"```json\n{reference_plot_outline}\n```\n\n"
        )
    elif reference_chapter_text:
        # 兜底：只有骨架抽取失败时才给极短事实片段，避免生成阶段大段接触原文。
        fallback_ref = _reference_prose_snippet(reference_chapter_text, max_chars=900)
        reference_block = (
            "【本章参考结构兜底片段（骨架抽取失败时使用；只取事件功能，禁止沿用句式、实体名和段落推进）】\n"
            f"```\n{fallback_ref}\n```\n\n"
        )

    if strict_source_plot:
        strict_plot_contract = (
            "【同结构改编｜结构功能以骨架为真值，表达与实体必须拉开距离】\n"
            "1) 主事件功能、场景功能、因果位置、人物登场/退场功能与冲突结果功能须与结构骨架一致；不是续写新书、不是扩写无关支线。\n"
            "2) 允许更换人物名、地点名、事件名、动物/物件名和局部承接方式；不得写入骨架中不存在的关键结构功能。\n"
            "3) 禁止沿用参考原文的连续句式、段落推进、开头落点、结尾收束方式和实体体系；同一功能事件必须换一种现场展开。\n"
            "4) 若领域圣经、作者长期意图、近期焦点、JSON 上下文或本章意图与结构骨架冲突，一律以结构骨架为准。\n"
            "5) 不得新增改变本章结构功能的支线或替换结局功能。\n\n"
        )
    else:
        strict_plot_contract = (
            "【同结构改编（实验模式：上一段衔接可能来自已生成 output）】\n"
            "本章主干仍以结构骨架为真：不得仅凭 output 衔接或 JSON 上下文编造冲突的新主线、新结局功能或重要结构节点。\n"
            "允许：语气、对白颗粒、感官扩写、镜头入口变化、实体名更换；禁止：贴着参考原文句式或实体体系洗稿。\n\n"
        )

    # 获取核心角色和道具
    core_characters = current_context.get('core_characters', [])
    core_items = current_context.get('core_items', [])
    core_elements = f"核心角色：{', '.join(core_characters) if core_characters else '无'}, 核心道具：{', '.join(core_items) if core_items else '无'}"

    ddd_block = ""
    if domain_text:
        ddd_block += (
            f"【领域圣经 DDD（静态设定）】\n"
            f"以下为世界观的术语与硬约束；**若与上方本章参考原文的情节、场次或因果冲突，以参考原文为准**；"
            f"仅在不冲突时遵守本节，且不得与参考合读时自相矛盾。\n\n"
            f"{domain_text}\n\n"
        )

    # --- 核心创作要求 (共同部分) ---
    # 严格结构适配时结构骨架已是「节拍表」；再叠长条规则 + 两阶段契约，易诱发清单腔、工整句，抬高平台 AI 率。
    if strict_source_plot:
        production_hard_rules = (
            f"【成文忌口（同结构改编专用，从简）】\n"
            f"- 句长错落，少排比；对话两人以上时口气要能区分。\n"
            f"- 少用段尾万能收束（总之/不禁/这一刻/他明白）；少连续内心说明书。\n"
            f"- 系统提示用打断、半句、动作混进戏里，不要连发同一腔调通知框。\n"
            f"- 结构功能跟着骨架走，但实体名、镜头、承接、句式要换，不要贴原文段落。\n"
            f"- 禁止连续 12 个字以上与参考原文相同；避免复用参考章的实体体系、开头句、结尾句和标志性比喻。\n\n"
        )
    else:
        production_hard_rules = (
            f"【产出侧结构硬约束（必须执行）】\n"
            f"1. **事件密度**：每 500-700 字须有一次不可逆变化（冲突升级/关系变化/代价落地/任务状态跃迁其一），"
            f"禁止用大段「解释世界/复盘策略/施工流水账」代替剧情。\n"
            f"2. **解释上限**：连续解释/判断型段落最多 2 段，其后必须插入动作、意外或人物交锋。\n"
            f"3. **角色声纹**：至少两名核心角色在句长、语气词或口癖上稳定可区分，禁止全员书面腔。\n"
            f"4. **开篇信息节奏（尤其无上一章时）**：前 700 字禁止用内心独白/旁白连续「打卡」交代穿越原因、系统功能表、世界观词条；"
            f"设定只通过当下动作、半截对话、被打断的念头漏出，一次只漏一点。\n"
            f"5. **反同构**：开头用动作或异常切入；结尾落在新变量或新压力，不用「总之/这一刻/他明白」式抽象收束。\n"
            f"6. **拒绝清单体**：禁止把「本章意图/待回收线索」写成编号小节或目录句；系统与建设必须长在戏里，不要说明书顺序。\n"
            f"7. **句式**：禁止连续三句长度与节奏几乎相同的陈述；每 400-600 字用环境声、动作或他人插话打断说明腔。\n"
            f"8. **写前自检（脑内即可，禁止输出）**：本段有没有发生新变化？是不是在解释代替戏剧？\n\n"
        )

    if strict_source_plot:
        implicit_two_phase_contract = ""
    else:
        implicit_two_phase_contract = (
            f"【隐式两阶段写作契约（强制）】\n"
            f"你必须先在内部完成“结构计划”，再写正文；但结构计划属于隐式推理，不得出现在输出中。\n"
            f"阶段A（内部静默规划，不输出）：\n"
            f"- 先为本章规划 4-7 个叙事节拍（每个节拍必须有事件变化）\n"
            f"- 标注每个节拍的冲突点、信息释放点、角色声纹策略\n"
            f"- 规划开头入口和结尾落点，确保不与近章同构\n"
            f"阶段B（仅输出正文）：\n"
            f"- 严格按阶段A的节拍写作，但语言自然，不要像提纲复述\n"
            f"- 禁止输出任何计划痕迹：如“节拍1/阶段A/结构计划/写作意图/自检”等字样\n"
            f"- 最终输出只能是章节标题+正文，不得包含解释、注释、清单、表格\n\n"
        )

    core_requirements = (
        f"{reference_block}"
        f"{strict_plot_contract}"
        + (
            "【下一章开头硬约束（用于避免断章冲突）】\n"
            "本章结尾必须能自然接入下列下一章开头；不得改变下一章开头已经确定的追问对象、冲突对象、人物关系和误会指向。\n"
            "如果下一章开头揭示某句喊话并非冲着主角，就不能在本章结尾写成主角已被明确抓捕或定罪。\n"
            f"```\n{next_head}\n```\n\n"
            if next_head else ""
        )
        + f"【语言风格备忘（非提纲；禁止模仿下列编号、小标题或分析腔落笔）】\n{style_brief}\n\n"
        f"{current_context_summary}\n\n"
        f"{core_elements}\n\n"
        f"{ddd_block}"
        f"【作者长期意图】\n{author_intent_text if author_intent_text else '无'}"
        f"{'（严格模式下若与参考原文冲突则忽略）' if strict_source_plot else ''}\n\n"
        f"【近期焦点】\n{current_focus_text if current_focus_text else '无'}"
        f"{'（严格模式下若与参考原文冲突则忽略）' if strict_source_plot else '（优先于长期意图）'}\n\n"
        f"【审计规则前置约束（写作时必须遵守）】\n{audit_requirements_text if audit_requirements_text else '无'}\n\n"
        f"【本章意图（须融化进场景；不得脱离结构骨架编造新主线）】\n"
        f"{chapter_plan_text if chapter_plan_text else '无（仍须严格按结构骨架的功能节点与场次写）'}\n\n"
        f"{implicit_two_phase_contract}"
        f"{production_hard_rules}"
        f"【核心创作要求】：\n"
        f"1. **风格**：同结构改编也要像真人落笔；幽默从处境里长出来，不要为搞笑而堆梗。\n"
        f"2. **连贯**：人物反应符合参考中的当下压力；设定与领域圣经一致且不与参考冲突。\n"
        f"3. **标题**：第 {chapter_number} 章单行标题，格式 `# 第{chapter_number}章 …` 置于最前。\n"
        f"4. **字数**：约 {target_length} 字；允许语意跳跃，不必写满「说明」才算完成。\n"
        f"5. **表达**：对话/叙述/内心交替出现，但内心勿承担世界观说明书职能。\n"
        f"6. **系统/UI**：用打断、误触、半句播报或动作衔接，避免连发同一腔调提示框。\n\n"
    )

    # 构建提示指令
    prompt_instruction = ""

    # 根据是否有前文构建不同的提示指令
    if previous_chapter_content:
        print(f"正在同结构改编第 {chapter_number} 章（带上一段衔接）…")
        previous_ending = previous_chapter_content[-2000:]  # 可调整长度
        cont_note = ""
        if strict_source_plot:
            cont_note = (
                "【衔接说明】下列「上一章节选」来自 input 原作上一章（若曾回退则为 output，仍以本章参考为情节真值）。\n"
            )
        else:
            cont_note = "【衔接说明】上一段可能来自 output；本章情节仍以 input 参考为准，不得据衔接段新编主线。\n"
        prompt_instruction = (
            core_requirements +
            f"【同结构改编衔接（仅连贯口语气与镜头，不另起故事）】：\n"
            f"{cont_note}"
            f"1. 正文从下列节选自然接入，时间线连续；不得引入参考结构中尚未出现的重大新功能节点。\n"
            f"   上一章节选：\n   ```\n   {previous_ending}\n   ```\n"
            f"2. 情绪与信息推进须落在本章结构骨架已有的功能节点上，不得写成「续写下一本书」。\n"
            f"3. 角色反应功能与参考一致，但实体名、动作细节、对白颗粒应改编。\n"
            f"4. 禁止为拉长篇幅而插入与参考结构无关的重要支线。\n"
        )
    else:
        print(f"正在同结构改编第 {chapter_number} 章（无上一段衔接）…")
        prompt_instruction = (
            core_requirements +
            f"【同结构改编开篇】：\n"
            f"1. 仅覆盖本章 input 参考中的结构功能与场次功能，不得改主线因果位置，也不是创作全新开篇故事。\n"
            f"{'2. 不得跳过参考中的关键功能场次，但可以更换实体名和局部承接。' if strict_source_plot else '2. 勿整段复述，可作对白、实体和感官改编。'}\n"
            f"3. 从现场与动作进入，少用说明书式内心。\n"
            f"4. 结尾若出现追喊、追杀、误会、拦路等钩子，必须与下一章开头的真实指向一致。\n"
        )

    # 双向衔接约束（如果提供了前后章锚点）
    bidirectional_contract = ""
    if prev_chapter_end or next_chapter_start:
        bidirectional_contract = "【双向衔接硬约束（必须遵守）】\n"
        if prev_chapter_end:
            bidirectional_contract += (
                f"上一章结尾的真实内容如下（本开头必须与之自然衔接，时间线和情绪不可断裂）：\n"
                f"```\n{prev_chapter_end}\n```\n"
            )
        if next_chapter_start:
            bidirectional_contract += (
                f"下一章开头的真实内容如下（本结尾钩子必须与之匹配，对象/指向/事件不可矛盾）：\n"
                f"```\n{next_chapter_start}\n```\n"
            )
        bidirectional_contract += (
            "核心规则：\n"
            "1. 开头：必须从上章结尾自然接入，不可「强行切换场景」或「跳时间线」。\n"
            "2. 结尾：生成钩子的对象/事件/指向必须与下一章开头一致。"
            " 例如：下一章开头是「妖道追杀」，本章结尾就应当是「妖道出现」，而不是「主角被抓」。\n\n"
        )

    prompt = prompt_instruction + bidirectional_contract
    messages = [
        {
            "role": "system",
            "content": (
            "你是一位小说同结构改编作家：依据结构骨架输出同一功能链的新正文，语气有松有紧、句子有长有短，拒绝范文腔。"
            "不是自由续写、不是扩写新故事线、不是同人另起炉灶；提示中的分析/意图是备忘，禁止把提示结构映射成新章节大纲。"
            "若含「领域圣经 DDD」，不与结构骨架冲突时遵守；冲突时以结构骨架为准。"
            "必须主动避开参考原文的实体体系、句式骨架、段落推进、开头和结尾表达。"
            "禁止用「心里咯噔一下/不禁/这一刻/显然」等万能情绪套话收束段落。"
            + (
                    " 当前为严格结构适配：本章结构骨架即功能真值，可以换实体、表达和镜头承接，不可改结构功能。"
                    if strict_source_plot
                    else " 当前为同结构改编实验模式：衔接可能非原作，但本章主干仍以结构骨架为准。"
                )
            ),
        },
        {"role": "user", "content": prompt},
    ]

    # ... (后续的 API 调用逻辑保持不变)
    try:
        print(f"API 请求 (尝试 1/3): 模型={CHAPTER_GENERATION_MODEL}, 温度={CHAPTER_GENERATION_TEMPERATURE}")
        new_content = call_deepseek_api(
            messages,
            CHAPTER_GENERATION_MODEL,
            max_tokens=_chapter_completion_max_tokens(target_length),
            temperature=CHAPTER_GENERATION_TEMPERATURE,
        )
        if not new_content:
            return None

        # 清洗误泄露的“计划/提纲/自检”内容，确保只保留章节成文
        leakage_markers = (
            "阶段A", "阶段B", "结构计划", "节拍", "写作意图", "自检",
            "仅内部", "隐式推理", "提纲", "PLAN", "CHECKLIST"
        )
        lines = (new_content or "").splitlines()
        cleaned_lines = []
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                cleaned_lines.append(ln)
                continue
            if any(marker in stripped for marker in leakage_markers):
                continue
            cleaned_lines.append(ln)
        new_content = "\n".join(cleaned_lines).strip()
        
        if not new_content.startswith("# "):
            print("警告：生成的内容未按预期以 '# ' 开头。可能缺少标题。尝试在开头添加默认标题。")
            first_sentence = new_content.split('\n')[0]
            potential_title = f"第{chapter_number}章 {first_sentence[:20]}"
            new_content = f"# {potential_title}\n\n{new_content}"
            print(f"已添加临时标题：# {potential_title}")

        # 统一用“正文内容拟题”替换标题，避免沿用参考原文章节名
        content_lines = new_content.splitlines()
        body_lines = content_lines
        if content_lines and content_lines[0].strip().startswith("#"):
            body_lines = content_lines[1:]
            if body_lines and not body_lines[0].strip():
                body_lines = body_lines[1:]
        body_text = "\n".join(body_lines).strip()
        generated_title = generate_title_from_chapter_content(
            chapter_number,
            body_text,
            reference_chapter_text=reference_chapter_text,
        )
        new_content = f"# {generated_title}\n\n{body_text}" if body_text else f"# {generated_title}\n"

        return new_content
    except Exception as e:
        
        print(f"生成新章节内容时发生错误: {e}")
        return None


def analyze_context_with_ai(current_context, chapter_content):
    """使用 AI 分析章节内容以更新上下文的核心部分"""
    print("正在调用 AI 分析章节以更新上下文...")
    # 提取需要 AI 更新的部分 (只传递相关的上下文)
    context_to_update = {
        "protagonist_info": current_context.get("protagonist_info", {}),
        "world_setting": current_context.get("world_setting", {})
    }
    current_context_json = json.dumps(context_to_update, ensure_ascii=False, indent=2)

    # 优化后的提示词
    prompt = (
        f"你是一个精通小说内容理解和信息提取的作家。你的任务是根据提供的【本章节内容】，更新【当前故事背景信息 (JSON)】中的 `protagonist_info` 和 `world_setting` 部分。\n\n"
        f"【重要分析规则】:\n"
        f"1. **超精准内容提取**: 只提取章节中明确出现的信息，不要推断、不要想象、不要创造未在文本中明确存在的内容。\n"
        f"2. **语言风格识别**: 特别注意原文语言风格的幽默感、诙谐表达和口语化特点，这是原作的核心风格特征。\n"
        f"3. **情节逻辑关联**: 精确捕捉事件发生的顺序和逻辑关系，确保剧情发展线索清晰连贯。\n"
        f"4. **人物特征聚焦**: 准确记录每个角色的独特言行举止、性格特点和对话风格，不要模板化处理人物。\n"
        f"【关键更新字段】:\n"
        f"1. `protagonist_info.status_summary`: 提取主角当前状态、心态和境遇的关键信息\n"
        f"2. `protagonist_info.key_items_abilities`: 主角拥有或获得的物品、能力或技能\n"
        f"3. `protagonist_info.key_relationships`: 主角与其他角色的关系发展\n"
        f"4. `world_setting.location`: 当前故事发生的具体地点和环境描述\n"
        f"5. `world_setting.key_elements`: 世界观中的规则、设定和重要背景元素\n\n"
        f"【精准判断准则】:\n"
        f"- 宁可少提取也不要过度推断\n"
        f"- 宁可保留已有内容也不要用不确定信息覆盖\n"
        f"- 确保每条记录的信息都能在原文中找到对应段落\n\n"
        f"--- 当前故事背景信息 (JSON) ---\n{current_context_json}\n\n"
        f"--- 本章节内容 ---\n{chapter_content[:6000]}\n\n" # 限制输入长度
        f"--- 请严格按照上述规则，输出【完整且有效的 JSON 对象】，结构如下示例：---\n"
        f"{{\n"
        f'  "protagonist_info": {{...内容...}},\n' # 省略号表示内容，不是字面的...
        f'  "world_setting": {{...内容...}}\n'
        f"}}"
    )

    messages = [
        {"role": "system", "content": "你是一个极其精准的信息提取和故事分析专家。你擅长捕捉小说的独特风格、细节和人物特征，能够准确区分原文明确包含的信息与推测内容。请记住：原文中没有明确的内容就不要添加，保持对原始文本的绝对忠实。"},
        {"role": "user", "content": prompt}
    ]
    
    try:
        # 使用通用 API 调用函数，并要求 JSON 对象格式
        updated_data_text = call_deepseek_api(
            messages, 
            CONTEXT_ANALYSIS_MODEL, 
            max_tokens=CONTEXT_ANALYSIS_MAX_TOKENS, 
            temperature=CONTEXT_ANALYSIS_TEMPERATURE,
            response_format={"type": "json_object"}
        )
        
        if not updated_data_text:
            print("警告: 调用 AI 分析上下文失败。跳过 AI 上下文更新。")
            return None
            
        # 尝试解析AI返回的JSON
        updated_data = json.loads(updated_data_text)
        
        # 验证返回的数据结构是否基本正确
        if isinstance(updated_data, dict) and ("protagonist_info" in updated_data or "world_setting" in updated_data):
            print("AI 上下文分析完成，成功解析更新数据。")
            return updated_data
        else:
            print("警告: AI 返回的 JSON 结构不符合预期。跳过 AI 上下文更新。")
            print(f"AI Raw Response Snippet: {str(updated_data_text)[:500]}...") # 打印部分原始响应以便调试
            return None
            
    except json.JSONDecodeError as e:
        print(f"警告: 解析 AI 返回的 JSON 时出错: {e}。跳过 AI 上下文更新。")
        print(f"AI Raw Response Snippet: {str(updated_data_text)[:500] if updated_data_text else 'None'}...") # 打印部分原始响应以便调试
        return None
    except Exception as e:
        print(f"警告: 调用 AI 分析上下文时发生错误: {e}。跳过 AI 上下文更新。")
        return None
