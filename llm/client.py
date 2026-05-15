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
