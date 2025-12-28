from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


@dataclass
class LLMResult:
    text: str


class OpenAITextService:
    """
    Minimal wrapper for generating narrative commentary.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def generate_commentary(
        self, *, system: str, user: str, model: str = os.getenv("OPENAI_MODEL")
    ) -> LLMResult:
        # Responses API is recommended for new projects.
        # Keep it simple: request text output.
        resp = self.client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        # SDK returns a structured response; easiest is to use output_text helper.
        text = getattr(resp, "output_text", None) or ""
        return LLMResult(text=text.strip())
