"""LLM provider factory — configurable between Ollama, OpenAI, and custom endpoints."""

import logging
import requests
import concurrent.futures
import urllib3
from typing import Any
from app.config import settings

# Suppress InsecureRequestWarning for self-signed certs on internal servers
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("audit.llm")

_llm_available: bool | None = None

# Max seconds to wait for a single LLM call
LLM_CALL_TIMEOUT = 120


class CustomLlamaCppLLM:
    """Wrapper for llama.cpp server that uses prompt-style API at /v1/chat/completions."""

    def __init__(self, base_url: str, model: str = "mistral", temperature: float = 0.1):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.endpoint = f"{self.base_url}/chat/completions"

    def invoke(self, messages: Any) -> Any:
        """Send prompt to llama.cpp and return response in LangChain-compatible format."""
        from langchain_core.messages import AIMessage

        # Convert LangChain messages to a single prompt string
        if isinstance(messages, list):
            parts = []
            for m in messages:
                if hasattr(m, "content"):
                    role = getattr(m, "type", "user")
                    if role == "human":
                        role = "user"
                    elif role == "system":
                        role = "system"
                    elif role == "ai":
                        role = "assistant"
                    parts.append(f"[{role}] {m.content}")
                elif isinstance(m, tuple):
                    parts.append(f"[{m[0]}] {m[1]}")
                elif isinstance(m, dict):
                    parts.append(f"[{m.get('role', 'user')}] {m.get('content', '')}")
            prompt = "\n".join(parts)
        elif isinstance(messages, str):
            prompt = messages
        else:
            prompt = str(messages)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": 4096,
        }

        logger.info(f"🔗 Calling llama.cpp: {self.endpoint} (prompt_len={len(prompt)})")
        resp = requests.post(
            self.endpoint,
            json=payload,
            timeout=LLM_CALL_TIMEOUT,
            verify=False,  # Self-signed cert on internal server
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract content from llama.cpp response
        content = ""
        if "choices" in data and data["choices"]:
            choice = data["choices"][0]
            if "message" in choice:
                content = choice["message"].get("content", "")
            elif "text" in choice:
                content = choice["text"]

        timings = data.get("timings", {})
        gen_ms = timings.get("total_generation_ms", 0)
        logger.info(f"🔗 llama.cpp responded: {len(content)} chars, {gen_ms:.0f}ms generation")

        return AIMessage(content=content)


def is_llm_available() -> bool:
    """Check if the configured LLM provider is reachable. Retries on each call if previously unavailable."""
    global _llm_available
    # Only cache positive results; retry if previously unavailable
    if _llm_available is True:
        return True

    # Pattern-only mode — skip LLM entirely for fast results
    if settings.LLM_PROVIDER == "pattern":
        _llm_available = False
        logger.info("Running in pattern-only mode (no LLM)")
        return False

    if settings.LLM_PROVIDER == "openai":
        if settings.OPENAI_BASE_URL and settings.OPENAI_API_COMPAT == "llamacpp":
            # Custom llama.cpp server (prompt-based API)
            try:
                resp = requests.post(
                    settings.OPENAI_BASE_URL.rstrip('/') + "/chat/completions",
                    json={"model": settings.OPENAI_MODEL, "prompt": "test", "max_tokens": 1},
                    timeout=10,
                    verify=False,
                )
                _llm_available = resp.status_code == 200
            except Exception as e:
                logger.warning(f"llama.cpp endpoint health check failed: {e}")
                _llm_available = False
            logger.info(f"llama.cpp endpoint: {settings.OPENAI_BASE_URL} available={_llm_available}")
        elif settings.OPENAI_BASE_URL:
            # Standard OpenAI-compatible API (Groq, Together, OpenRouter, etc.)
            try:
                resp = requests.get(
                    settings.OPENAI_BASE_URL.rstrip('/') + "/models",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    timeout=10,
                )
                _llm_available = resp.status_code == 200
            except Exception as e:
                logger.warning(f"OpenAI-compatible endpoint health check failed: {e}")
                _llm_available = False
            logger.info(f"OpenAI-compatible endpoint: {settings.OPENAI_BASE_URL} available={_llm_available}")
        else:
            _llm_available = bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-key-here")
    else:
        try:
            resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3)
            _llm_available = resp.status_code == 200
        except Exception:
            _llm_available = False

    if not _llm_available:
        logger.warning(f"LLM provider '{settings.LLM_PROVIDER}' is not available. Using pattern-based analysis.")
    return _llm_available


def reset_llm_check():
    """Reset the LLM availability cache (useful after starting Ollama)."""
    global _llm_available
    _llm_available = None


def get_llm():
    """Return the configured LLM instance."""
    if settings.LLM_PROVIDER == "openai":
        if settings.OPENAI_BASE_URL and settings.OPENAI_API_COMPAT == "llamacpp":
            # llama.cpp server with prompt-based API
            logger.info(f"Creating llama.cpp LLM: model={settings.OPENAI_MODEL} base_url={settings.OPENAI_BASE_URL}")
            return CustomLlamaCppLLM(
                base_url=settings.OPENAI_BASE_URL,
                model=settings.OPENAI_MODEL,
                temperature=0.1,
            )
        else:
            # Standard OpenAI-compatible API (OpenAI, Groq, Together, OpenRouter)
            from langchain_openai import ChatOpenAI
            kwargs = {
                "model": settings.OPENAI_MODEL,
                "api_key": settings.OPENAI_API_KEY,
                "temperature": 0.1,
            }
            if settings.OPENAI_BASE_URL:
                kwargs["base_url"] = settings.OPENAI_BASE_URL
            logger.info(f"Creating OpenAI-compatible LLM: model={settings.OPENAI_MODEL} base_url={settings.OPENAI_BASE_URL or 'api.openai.com'}")
            return ChatOpenAI(**kwargs)
    else:
        from langchain_ollama import ChatOllama
        logger.info(f"Creating Ollama LLM: model={settings.OLLAMA_MODEL} base_url={settings.OLLAMA_BASE_URL}")
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0.1,
            timeout=LLM_CALL_TIMEOUT,
        )


def invoke_with_timeout(llm, messages, timeout: int = LLM_CALL_TIMEOUT):
    """Call LLM with a hard timeout. Raises TimeoutError if it takes too long."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.invoke, messages)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning(f"⏰ LLM call timed out after {timeout}s — skipping this chunk")
            raise TimeoutError(f"LLM call exceeded {timeout}s timeout")
