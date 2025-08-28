from typing import Protocol

class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...

class EchoProvider:
    def complete(self, prompt: str) -> str:
        return f"[echo] {prompt}"
