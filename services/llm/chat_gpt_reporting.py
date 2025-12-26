# services/llm/chatgpt_reporting_service.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import OpenAI


def sha256_json(obj: Any) -> str:
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChatGPTConfig:
    api_key: str
    model: str = "gpt-5.2"
    temperature: float = 0.2
    timeout_s: Optional[float] = None


class ChatGPTMonthlyReportingService:
    """
    LLM narrative generator that references benchmark fields already computed
    in metrics_json. The agent must benchmark versus SPY by default.
    """

    DISCLOSURES = [
        "Proprietary, unaudited performance. Past performance is not indicative of future results.",
        "This material is for informational purposes only and does not constitute investment advice.",
        "All returns are shown net of estimated transaction costs unless otherwise stated.",
    ]

    RESPONSE_SCHEMA: Dict[str, Any] = {
        "name": "monthly_commentary",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "executive_bullets": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {"type": "string", "minLength": 5, "maxLength": 220},
                },
                "performance_commentary": {
                    "type": "string",
                    "minLength": 20,
                    "maxLength": 1200,
                },
                "risk_commentary": {
                    "type": "string",
                    "minLength": 20,
                    "maxLength": 1200,
                },
                "positioning_commentary": {
                    "type": "string",
                    "minLength": 20,
                    "maxLength": 1200,
                },
                "activity_commentary": {
                    "type": "string",
                    "minLength": 20,
                    "maxLength": 1200,
                },
                "model_notes": {"type": "string", "minLength": 10, "maxLength": 600},
                "disclosures": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 10,
                    "items": {"type": "string", "minLength": 5, "maxLength": 240},
                },
            },
            "required": [
                "executive_bullets",
                "performance_commentary",
                "risk_commentary",
                "positioning_commentary",
                "activity_commentary",
                "model_notes",
                "disclosures",
            ],
        },
        "strict": True,
    }

    BANNED_PHRASES = (
        "guarantee",
        "will outperform",
        "you should",
        "we expect",
        "prediction",
        "certainly",
        "risk-free",
        "low risk",
    )

    def __init__(self, cfg: ChatGPTConfig, benchmark_symbol: str = "SPY"):
        self.cfg = cfg
        self.benchmark_symbol = benchmark_symbol.upper().strip()
        self.client = OpenAI(api_key=cfg.api_key)

    def _build_instructions(self) -> str:
        return (
            "You are a performance reporting analyst for a rules-based ETF strategy.\n"
            "Rules:\n"
            "- Use ONLY the facts/numbers provided in METRICS_JSON.\n"
            "- Do NOT invent or infer missing values.\n"
            "- Do NOT provide recommendations, advice, or forward-looking statements.\n"
            "- Avoid promissory language (no predictions, no guarantees).\n"
            "- Return output strictly matching the provided JSON schema.\n"
            f"- Benchmark the strategy versus {self.benchmark_symbol} whenever benchmark fields are present.\n"
            f"- If benchmark fields for {self.benchmark_symbol} are missing, explicitly state that benchmark comparison is unavailable.\n"
        )

    def _require_benchmark_fields(self, metrics_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensures the prompt clearly requests SPY benchmarking. Does NOT compute it.
        """
        perf = (metrics_json or {}).get("performance") or {}
        # We do not error if missing; we instruct the agent to state unavailable.
        return {
            "benchmark_symbol": perf.get("benchmark_symbol") or self.benchmark_symbol,
            "has_benchmark_mtd": "benchmark_mtd_return" in perf
            and perf.get("benchmark_mtd_return") is not None,
            "has_benchmark_ytd": "benchmark_ytd_return" in perf
            and perf.get("benchmark_ytd_return") is not None,
            "has_benchmark_si": "benchmark_si_return" in perf
            and perf.get("benchmark_si_return") is not None,
        }

    def _build_user_input(self, metrics_json: Dict[str, Any]) -> str:
        b = self._require_benchmark_fields(metrics_json)

        return (
            "Generate a monthly performance commentary.\n\n"
            "Required content:\n"
            "- 3–5 executive bullets\n"
            "- Performance summary: MTD/YTD/SI returns.\n"
            f"- Benchmark comparison versus {self.benchmark_symbol}:\n"
            "  - If benchmark fields exist, compare strategy vs benchmark for MTD/YTD/SI as available.\n"
            "  - If benchmark fields are missing, explicitly state benchmark comparison is unavailable.\n"
            "- Risk summary: vol, max drawdown, and best/worst week if present.\n"
            "- Positioning: top holdings/weights.\n"
            "- Activity: rebalance count, trades, turnover if present.\n"
            "- Model notes: strategy_version + whether model_change occurred.\n\n"
            "Hard constraints:\n"
            "- Facts only from METRICS_JSON.\n"
            "- No predictions or advice.\n"
            "- Keep tone professional and concise.\n\n"
            f"Benchmark presence flags (for clarity): {json.dumps(b)}\n"
            f"Disclosures (must be included): {json.dumps(self.DISCLOSURES)}\n\n"
            f"METRICS_JSON:\n{json.dumps(metrics_json, indent=2, default=str)}\n"
        )

    def _validate_banned_language(self, obj: Dict[str, Any]) -> None:
        blob = json.dumps(obj, ensure_ascii=False).lower()
        for phrase in self.BANNED_PHRASES:
            if phrase in blob:
                raise ValueError(f"Banned phrase detected in LLM output: {phrase}")

    def generate_monthly_commentary(
        self, metrics_json: Dict[str, Any]
    ) -> Dict[str, Any]:
        instructions = self._build_instructions()
        user_input = self._build_user_input(metrics_json)

        prompt_hash = sha256_text(instructions + "\n\n" + user_input)
        inputs_hash = sha256_json(metrics_json)

        resp = self.client.responses.create(
            model=self.cfg.model,
            instructions=instructions,
            input=user_input,
            temperature=self.cfg.temperature,
            text={
                "format": {
                    "type": "json_schema",
                    "strict": True,
                    "schema": self.RESPONSE_SCHEMA["schema"],
                    "name": self.RESPONSE_SCHEMA["name"],
                }
            },
        )

        raw_text = resp.output_text
        data = json.loads(raw_text)

        # Force disclosures deterministic in calling task as well (defense in depth)
        self._validate_banned_language(data)

        return {
            "commentary": data,
            "llm_model": self.cfg.model,
            "prompt_hash": prompt_hash,
            "inputs_hash": inputs_hash,
        }
