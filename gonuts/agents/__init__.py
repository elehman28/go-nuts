"""The six Go Nuts agents. Any agent can delegate a task to any other through the Team bus."""
from ..db import DB
from ..llm import LLM, UsageTracker
from ..team import Team
from .analyst import MenuAnalyst
from .cost_control import CostControl
from .fetcher import MenuFetcher
from .finder import Finder
from .summarizer import Summarizer
from .verifier import Verifier

AGENT_CLASSES = [Finder, MenuFetcher, MenuAnalyst, Verifier, Summarizer, CostControl]


def build_team(tracker: UsageTracker | None = None, db: DB | None = None, llm=None) -> Team:
    db = db or DB()
    llm = llm or LLM(tracker or UsageTracker(), db)
    team = Team(llm, db)
    for cls in AGENT_CLASSES:
        team.add(cls)
    return team
