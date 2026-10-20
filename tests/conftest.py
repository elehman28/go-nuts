"""Shared test setup: a fake model so tests are free, offline and repeatable."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gonuts.agents import build_team  # noqa: E402
from gonuts.db import DB  # noqa: E402
from gonuts.llm import UsageTracker  # noqa: E402

PROFILE = {"allergens": ["Peanuts", "All tree nuts"], "severity": "Severe"}


class FakeLLM:
    """Stands in for gpt-6-luna. `answers[agent]` is a dict, or a function(system, user) -> dict.
    `tool_calls[agent]` is a list of (name, args) the fake model 'calls' before answering."""

    def __init__(self, answers=None, tool_calls=None, tokens_per_call=(1000, 200, 300)):
        self.tracker = UsageTracker()
        self.answers = answers or {}
        self.tool_calls = tool_calls or {}
        self.tokens = tokens_per_call
        self.prompts = []  # (agent, user message) for every call
        self.tool_results = []

    def new_run(self):
        return "test"

    def run(self, agent, system, user, tools=None, on_tool=None, max_rounds=3):
        self.prompts.append((agent, user))
        inp, cached, out = self.tokens
        self.tracker.calls.append({"agent": agent, "input_tokens": inp, "cached_input_tokens": cached,
                                   "output_tokens": out})
        for name, args in self.tool_calls.get(agent, []):
            try:
                self.tool_results.append(on_tool(name, args))
            except Exception as e:
                self.tool_results.append({"error": str(e)})
        answer = self.answers.get(agent, {})
        return answer(system, user) if callable(answer) else answer


@pytest.fixture
def make_team(tmp_path):
    def _make(**fake_kwargs):
        fake = FakeLLM(**fake_kwargs)
        team = build_team(db=DB(tmp_path / "test.db"), llm=fake)
        return team, fake
    return _make
