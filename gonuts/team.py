"""The team: a message bus where ANY agent can delegate a task to ANY other agent.

Agents never call each other directly. They call `team.send(sender, recipient, task, payload)`.
The bus:
  - delivers the task to the recipient and returns its answer
  - records every hand-off in a trace (shown in the app's "Agent trace" tab)
  - stops runaway delegation: a hop limit, a depth limit, and loop detection
    (an agent may not be handed a task identical to one it is already working on)
"""
import hashlib
import json
import time

from . import config


class DelegationError(Exception):
    pass


class Agent:
    name = "agent"
    title = "Agent"
    description = ""
    uses_model = False
    # task name -> short description. Other agents (and the AI agents' delegate tool) read these.
    skills: dict[str, str] = {}

    def __init__(self, team: "Team"):
        self.team = team

    @property
    def db(self):
        return self.team.db

    @property
    def llm(self):
        return self.team.llm

    def delegate(self, recipient: str, task: str, **payload):
        return self.team.send(self.name, recipient, task, payload)

    def handle(self, task: str, payload: dict):
        method = getattr(self, task, None)
        if task not in self.skills or method is None:
            raise DelegationError(f"{self.title} can't do '{task}'. It can do: {', '.join(self.skills)}")
        return method(**payload)

    # ---- for AI agents: a tool that lets the model delegate to any teammate
    def delegate_tool(self) -> dict:
        others = [a for a in self.team.agents.values() if a.name != self.name]
        menu = "\n".join(f"- {a.name}.{task}: {desc}" for a in others for task, desc in a.skills.items())
        return {
            "type": "function",
            "function": {
                "name": "delegate",
                "description": "Hand a task to a teammate and get their answer. Teammates and tasks:\n" + menu,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "enum": [a.name for a in others]},
                        "task": {"type": "string"},
                        "payload": {"type": "object", "description": "Arguments for the task"},
                    },
                    "required": ["agent", "task", "payload"],
                },
            },
        }

    def on_tool(self, name: str, args: dict):
        if name != "delegate":
            return {"error": f"unknown tool {name}"}
        return self.delegate(args.get("agent", ""), args.get("task", ""), **(args.get("payload") or {}))


class Team:
    def __init__(self, llm, db):
        self.llm = llm
        self.db = db
        self.agents: dict[str, Agent] = {}
        self.trace: list[dict] = []
        self._stack: list[tuple[str, str]] = []
        self._hops = 0
        self.on_step = None  # optional callback(step) so the app can show live progress

    def add(self, agent_cls) -> Agent:
        agent = agent_cls(self)
        self.agents[agent.name] = agent
        return agent

    def start_run(self) -> str:
        self.trace = []
        self._hops = 0
        self._stack = []
        return self.llm.new_run()

    def send(self, sender: str, recipient: str, task: str, payload: dict | None = None):
        payload = payload or {}
        if recipient not in self.agents:
            raise DelegationError(f"No agent named '{recipient}'. Agents: {', '.join(self.agents)}")
        self._hops += 1
        if self._hops > config.MAX_HOPS_PER_RUN:
            raise DelegationError(f"Stopped: more than {config.MAX_HOPS_PER_RUN} hand-offs in one request.")
        if len(self._stack) >= config.MAX_DELEGATION_DEPTH:
            raise DelegationError(f"Stopped: delegation chain deeper than {config.MAX_DELEGATION_DEPTH}.")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
        signature = (recipient, task + ":" + fingerprint)
        if signature in self._stack:
            raise DelegationError(f"Stopped a loop: {recipient} is already working on this exact '{task}' task.")

        step = {"step": len(self.trace) + 1, "depth": len(self._stack), "from": sender, "to": recipient,
                "task": task, "input": _preview(payload), "status": "running", "output": "",
                "tokens": 0, "seconds": 0.0}
        self.trace.append(step)
        if self.on_step:
            try:
                self.on_step(step)
            except Exception:  # a display problem must never break the team's work
                pass
        tokens_before = self.llm.tracker.total_tokens
        start = time.time()
        self._stack.append(signature)
        try:
            result = self.agents[recipient].handle(task, payload)
            step["status"] = "done"
            step["output"] = _preview(result)
            return result
        except Exception as e:
            step["status"] = "error"
            step["output"] = str(e)[:300]
            raise
        finally:
            self._stack.pop()
            step["seconds"] = round(time.time() - start, 2)
            step["tokens"] = self.llm.tracker.total_tokens - tokens_before

    def edges(self) -> list[tuple[str, str, str]]:
        return [(s["from"], s["to"], s["task"]) for s in self.trace]


def _preview(obj, limit: int = 160) -> str:
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            if isinstance(v, str):
                v = v if len(v) < 40 else f"<{len(v):,} chars>"
            elif isinstance(v, (list, dict)):
                v = f"<{len(v)} items>"
            parts.append(f"{k}={v}")
        text = ", ".join(parts)
    elif isinstance(obj, list):
        text = f"{len(obj)} items"
    else:
        text = str(obj)
    return text[:limit]
