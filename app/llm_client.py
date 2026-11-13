"""本地模型调用：只对接 Ollama，不引入任何云端依赖。"""

from __future__ import annotations

import re
from typing import Any

import httpx

# qwen3 系列默认开启 thinking，返回内容带成对的标记，这里整段剔除
THINK_PATTERN = re.compile(r"<\*{2}>.*?</\*{2}>|</\*{2}>|<\*{2}>", re.S)


class OllamaClient:
    def __init__(self, config: dict[str, Any]) -> None:
        llm = config["llm"]
        self.base_url: str = llm["base_url"].rstrip("/")
        self.chat_model: str = llm["chat_model"]
        self.timeout: float = float(llm.get("timeout_seconds", 60))

    async def generate(self, prompt: str, system: str = "") -> str:
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            return THINK_PATTERN.sub("", resp.json().get("response", "")).strip()

    async def is_alive(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
