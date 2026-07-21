"""统一 LLM 调用：DeepSeek / 豆包 Ark（OpenAI 兼容 chat 与可选 /responses）。"""

import httpx
import json
import time
import openai

from config import (
    LLM_PROVIDER,
    API_KEY,
    BASE_URL,
    API_HTTP_CONNECT_TIMEOUT,
    API_HTTP_READ_TIMEOUT,
    DEBUG_LLM_LOG,
    DEBUG_LLM_PREVIEW_CHARS,
    DOUBAO_USE_RESPONSES_API,
    DOUBAO_DISABLE_THINKING,
    MAX_OUTPUT_TOKENS,
)

# 模块级 HTTP 客户端单例，避免每次调用创建新连接
_http_client = None
_openai_client = None


def _get_openai_client():
    """获取复用的 OpenAI 客户端单例。"""
    global _http_client, _openai_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=httpx.Timeout(
            connect=API_HTTP_CONNECT_TIMEOUT,
            read=API_HTTP_READ_TIMEOUT,
            write=30.0,
            pool=10.0,
        ))
        _openai_client = openai.OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
            http_client=_http_client,
        )
    return _openai_client


def _preview_text(text, limit=600):
    if not isinstance(text, str):
        return ""
    cleaned = text.replace("\r", " ").replace("\n", "\\n")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "...(truncated)"


def _debug_log_request(model, messages, temperature, max_tokens, response_format=None, task_label=""):
    if not DEBUG_LLM_LOG:
        return
    if task_label:
        print(f"[LLM DEBUG] task={task_label}", flush=True)
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


def _looks_like_meta_reasoning(text):
    """识别"用户现在需要…"这类元推理开头，避免污染下游审计/生成流程。"""
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
        # MiMo-v2.5-pro 推理模型 reasoning_content 常见前缀
        "首先，用户要求",
        "首先，用户想要",
        "用户要求我",
        "用户想要我",
        "用户希望我",
    )
    if any(head.startswith(p) for p in bad_prefixes):
        return True
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
    if DEBUG_LLM_LOG:
        print(f"[LLM DEBUG] processing path={path_label} endpoint={BASE_URL.rstrip('/')}/chat/completions", flush=True)
    client = _get_openai_client()
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "timeout": timeout,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    # 豆包 doubao-seed 系列模型默认可能开启思考模式，通过 extra_body 关闭
    if LLM_PROVIDER == "doubao" and DOUBAO_DISABLE_THINKING:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    response = client.chat.completions.create(**kwargs)
    msg = response.choices[0].message
    content = (msg.content or "").strip()

    # 记录推理模型的 token 使用情况（调试用）
    if DEBUG_LLM_LOG and not content:
        if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
            print(f"[LLM DEBUG] content 为空，reasoning_content 长度={len(msg.reasoning_content)}", flush=True)
        if response.usage and hasattr(response.usage, 'completion_tokens_details'):
            details = response.usage.completion_tokens_details
            if details and hasattr(details, 'reasoning_tokens') and details.reasoning_tokens:
                print(f"[LLM DEBUG] reasoning_tokens={details.reasoning_tokens}, completion_tokens={response.usage.completion_tokens}", flush=True)

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
    # 豆包 doubao-seed 系列模型默认可能开启思考模式，通过 thinking 参数关闭
    if DOUBAO_DISABLE_THINKING:
        payload["thinking"] = {"type": "disabled"}

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
            raise RuntimeError("Ark /responses endpoint not available (404)")
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


def call_deepseek_api(messages, model, max_tokens=None, temperature=0.7, response_format=None, task_label=""):
    """调用 LLM 的通用函数（MiMo / DeepSeek / 豆包 Ark）。"""
    response_format = _effective_response_format(response_format)
    timeout = httpx.Timeout(
        connect=API_HTTP_CONNECT_TIMEOUT,
        read=API_HTTP_READ_TIMEOUT,
        write=API_HTTP_CONNECT_TIMEOUT,
        pool=API_HTTP_CONNECT_TIMEOUT,
    )
    
    # 如果未指定max_tokens，使用配置的默认值
    if max_tokens is None:
        max_tokens = MAX_OUTPUT_TOKENS

    retries = 6
    delay = 8
    max_delay = 120  # 最大重试延迟 2 分钟
    last_exception = None

    for attempt in range(retries):
        try:
            task = f"任务={task_label}，" if task_label else ""
            print(
                f"API 请求 ({task}尝试 {attempt + 1}/{retries}): 模型={model}, 温度={temperature}, "
                f"读超时={API_HTTP_READ_TIMEOUT}s",
                flush=True,
            )
            _debug_log_request(model, messages, temperature, max_tokens, response_format=response_format, task_label=task_label)
            print(
                f"  → 正在等待服务端返回：{task_label or '未标注任务'}。网络慢或模型排队时可能需一至数分钟，并非死机。",
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
                    except RuntimeError:
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
                # MiMo 和 DeepSeek 都使用 OpenAI 兼容接口
                path_label = "mimo.chat.completions" if LLM_PROVIDER == "mimo" else "openai.chat.completions"
                content = _call_openai_chat_api(
                    messages=messages,
                    model=model,
                    timeout=timeout,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format=response_format,
                    path_label=path_label,
                )

            if _looks_like_meta_reasoning(content):
                if DEBUG_LLM_LOG:
                    print("[LLM DEBUG] invalid meta-reasoning response detected, force retry", flush=True)
                    print(f"[LLM DEBUG] meta_preview={_preview_text(content, DEBUG_LLM_PREVIEW_CHARS)}", flush=True)
                raise RuntimeError('模型返回了元推理文本（如"用户现在需要…"），已判定为无效响应')

            return content

        except Exception as e:
            last_exception = e
            print(f"请求失败 (尝试 {attempt + 1}/{retries}): {str(e)}", flush=True)
            if attempt < retries - 1:
                print(f"将在 {delay} 秒后重试...", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, max_delay)
            else:
                print(f"已达到最大重试次数 ({retries})，请求失败。", flush=True)

    if last_exception:
        error_msg = f"所有 API 调用尝试均失败 ({retries} 次)。最后的错误: {str(last_exception)}"
        print(error_msg, flush=True)
        raise RuntimeError(error_msg) from last_exception
    return None
