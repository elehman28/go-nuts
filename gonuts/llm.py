"""The single place the app talks to the model.

Every call goes through `LLM.run`, which:
  - always uses config.MODEL (gpt-6-luna via Portkey)
  - refuses to run once the session or daily token budget is spent
  - records input / cached input / output tokens for the Tokenomics tab
  - lets an agent call tools (used for delegating to other agents), up to MAX_TOOL_ROUNDS
"""
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config


class BudgetExceeded(Exception):
    pass


class MissingKey(Exception):
    pass


class ModelError(Exception):
    """The model was unreachable or its answer was unusable. Messages are safe to show users."""


class OutputCutOff(ModelError):
    """The answer hit MAX_OUTPUT_TOKENS and was cut off mid-JSON."""


@dataclass
class UsageTracker:
    """Token usage for one browser session."""
    budget: int = config.SESSION_TOKEN_BUDGET
    calls: list = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(c["input_tokens"] + c["output_tokens"] for c in self.calls)

    def totals(self, run_id: str | None = None) -> dict:
        calls = [c for c in self.calls if run_id is None or c.get("run_id") == run_id]
        return {
            "calls": len(calls),
            "input_tokens": sum(c["input_tokens"] for c in calls),
            "cached_input_tokens": sum(c["cached_input_tokens"] for c in calls),
            "output_tokens": sum(c["output_tokens"] for c in calls),
        }


def _usage_numbers(usage) -> tuple[int, int, int]:
    if usage is None:
        return 0, 0, 0
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) if details else 0
    return usage.prompt_tokens or 0, cached or 0, usage.completion_tokens or 0


def parse_json(text: str) -> dict:
    text = (text or "{}").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        try:
            if start != -1 and end > start:
                return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
        raise ModelError("The AI's answer came back garbled. Please try again.")


class LLM:
    def __init__(self, tracker: UsageTracker, db=None):
        self.tracker = tracker
        self.db = db
        self.run_id: str = uuid.uuid4().hex[:8]
        self._client = None

    def new_run(self) -> str:
        self.run_id = uuid.uuid4().hex[:8]
        return self.run_id

    def client(self):
        if self._client is None:
            from portkey_ai import Portkey
            key = config.get_portkey_key()
            if not key:
                raise MissingKey("PORTKEY_API_KEY not found. Put it in a .env file in this folder or the folder above it.")
            self._client = Portkey(api_key=key)
        return self._client

    def check_budget(self):
        if self.tracker.total_tokens >= self.tracker.budget:
            raise BudgetExceeded(f"This session used its {self.tracker.budget:,}-token budget. "
                                 "Refresh the page to start a new session.")
        if self.db is not None and self.db.tokens_today() >= config.DAILY_TOKEN_BUDGET:
            raise BudgetExceeded("Go Nuts has reached its daily AI budget. Cached restaurants still work; "
                                 "new menus can be checked tomorrow.")

    def _create(self, agent: str, messages: list, tools: list | None):
        self.check_budget()
        start = time.time()
        kwargs = dict(model=config.MODEL, messages=messages, max_completion_tokens=config.MAX_OUTPUT_TOKENS,
                      timeout=config.MODEL_TIMEOUT_SECONDS,
                      response_format={"type": "json_object"})
        if tools:
            kwargs["tools"] = tools
            # gpt-6-luna on /chat/completions only accepts function tools with reasoning turned off.
            kwargs["reasoning_effort"] = "none"
        elif agent in config.REASONING_EFFORT:
            kwargs["reasoning_effort"] = config.REASONING_EFFORT[agent]
        try:
            resp = self.client().chat.completions.create(**kwargs)
        except Exception as e:
            kind = type(e).__name__
            if "Timeout" in kind:
                raise ModelError(f"The AI model didn't answer within {config.MODEL_TIMEOUT_SECONDS} seconds. "
                                 "Please try again.") from e
            if "RateLimit" in kind:
                raise ModelError("The AI model is busy right now. Please try again in a minute.") from e
            if "Connection" in kind:
                raise ModelError("Could not reach the AI model. Check your internet connection.") from e
            raise ModelError(f"The AI model returned an error ({kind}).") from e
        inp, cached, out = _usage_numbers(resp.usage)
        rec = {"time": datetime.now(timezone.utc).isoformat(), "run_id": self.run_id, "agent": agent,
               "model": config.MODEL, "input_tokens": inp, "cached_input_tokens": cached,
               "output_tokens": out, "seconds": round(time.time() - start, 2)}
        self.tracker.calls.append(rec)
        if self.db is not None:
            self.db.log_usage(rec)
        config.LOG_DIR.mkdir(exist_ok=True)
        with open(config.LOG_DIR / "usage.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        if resp.choices[0].finish_reason == "length":
            raise OutputCutOff(f"The AI's answer was longer than {config.MAX_OUTPUT_TOKENS:,} tokens and was cut off.")
        return resp.choices[0].message

    def run(self, agent: str, system: str, user, tools: list | None = None, on_tool=None,
            max_rounds: int = config.MAX_TOOL_ROUNDS) -> dict:
        """Run one agent task and return its final JSON answer.

        `user` is a string, or a list of content parts (for images).
        If the model calls a tool, `on_tool(name, args)` runs it and the answer is sent back.
        """
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for round_no in range(max_rounds + 1):
            allow_tools = tools if round_no < max_rounds else None
            msg = self._create(agent, messages, allow_tools)
            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                return parse_json(msg.content)
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.function.name,
                                                          "arguments": tc.function.arguments}}
                                            for tc in tool_calls]})
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = on_tool(tc.function.name, args) if on_tool else {"error": "no tools available"}
                except Exception as e:  # tell the model what went wrong instead of crashing
                    result = {"error": str(e)}
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result, default=str)[:12_000]})
        return {}
