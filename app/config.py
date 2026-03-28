import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "mistral")

    # OpenAI (also used for OpenAI-compatible servers like Groq, Together, llama.cpp)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")
    # "standard" for Groq/Together/OpenRouter, "llamacpp" for llama.cpp prompt-based API
    OPENAI_API_COMPAT: str = os.getenv("OPENAI_API_COMPAT", "standard")

    # App
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    SUPPORTED_EXTENSIONS: list[str] = os.getenv(
        "SUPPORTED_EXTENSIONS", ".py,.js,.ts,.java,.go,.rb"
    ).split(",")

    # Directories to skip
    SKIP_DIRS: set[str] = {
        "node_modules", "venv", ".venv", ".git", "__pycache__",
        "dist", "build", ".next", ".nuxt", "env", ".env",
        ".tox", ".mypy_cache", ".pytest_cache", "site-packages",
    }

    MAX_FILE_SIZE_BYTES: int = 100 * 1024  # 100KB


settings = Settings()
