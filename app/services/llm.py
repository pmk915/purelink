from __future__ import annotations

import httpx


class LLMProviderError(RuntimeError):
    pass


def generate_openai_compatible_chat_completion(
    *,
    api_base: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: float = 30.0,
) -> str:
    endpoint = f"{api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    try:
        response = httpx.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LLMProviderError(
            "LLM request timed out. Check LLM_API_BASE_URL, network access, and LLM_TIMEOUT_SECONDS."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise LLMProviderError(
            f"LLM provider returned HTTP {exc.response.status_code}. Check LLM_API_KEY and LLM_MODEL."
        ) from exc
    except httpx.HTTPError as exc:
        raise LLMProviderError(
            "LLM request failed. Check LLM_API_BASE_URL and provider network access."
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise LLMProviderError("LLM response is not valid JSON.") from exc

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMProviderError("LLM response does not contain choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise LLMProviderError("LLM response choice is invalid.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise LLMProviderError("LLM response message is invalid.")

    content = message.get("content")
    if isinstance(content, str):
        normalized = content.strip()
        if normalized:
            return normalized
        raise LLMProviderError("LLM response content is empty.")

    if isinstance(content, list):
        text_parts = [
            item.get("text", "").strip()
            for item in content
            if isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
            and item.get("text", "").strip()
        ]
        if text_parts:
            return "\n".join(text_parts)

    raise LLMProviderError("LLM response content is invalid.")
