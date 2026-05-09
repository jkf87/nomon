"""
Gnomon evaluation report — per-agent scores, ranking, markdown/JSON export.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openclaw_gnomon.gates.base import GateResult


@dataclass
class AgentEvaluation:
    agent_name: str
    gate_results: List[GateResult] = field(default_factory=list)
    total_score: float = 0.0
    rank: int = 0
    duration_seconds: float = 0.0
    notes: List[str] = field(default_factory=list)
    skipped: bool = False


@dataclass
class EvaluationReport:
    task_name: str
    task_type: str
    timestamp: str
    agents: List[AgentEvaluation] = field(default_factory=list)
    winner: Optional[str] = None
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_name": self.task_name,
            "task_type": self.task_type,
            "timestamp": self.timestamp,
            "winner": self.winner,
            "summary": self.summary,
            "agents": [
                {
                    "agent_name": a.agent_name,
                    "total_score": a.total_score,
                    "rank": a.rank,
                    "duration_seconds": a.duration_seconds,
                    "skipped": a.skipped,
                    "notes": a.notes,
                    "gate_results": [asdict(g) for g in a.gate_results],
                }
                for a in self.agents
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append(f"# Gnomon Evaluation Report — {self.task_name}")
        lines.append("")
        lines.append(f"- **Task type:** `{self.task_type}`")
        lines.append(f"- **Timestamp:** {self.timestamp}")
        lines.append(f"- **Winner:** {self.winner or '—'}")
        lines.append("")
        if self.summary:
            lines.append("## Summary")
            lines.append(self.summary)
            lines.append("")

        lines.append("## Ranking")
        lines.append("")
        lines.append("| Rank | Agent | Score | Duration | Status |")
        lines.append("|---:|:--|---:|---:|:--|")
        for a in sorted(self.agents, key=lambda x: x.rank):
            status = "skipped" if a.skipped else "ran"
            lines.append(
                f"| {a.rank} | {a.agent_name} | {a.total_score:.1f} |"
                f" {a.duration_seconds:.1f}s | {status} |"
            )

        for a in self.agents:
            lines.append("")
            lines.append(f"### {a.agent_name}")
            if a.notes:
                for n in a.notes:
                    lines.append(f"- {n}")
            for g in a.gate_results:
                lines.append("")
                lines.append(f"**Gate: `{g.name}`** — score {g.score:.1f} | passed={g.passed}")
                if g.details:
                    lines.append("")
                    lines.append("```json")
                    lines.append(json.dumps(g.details, indent=2, ensure_ascii=False))
                    lines.append("```")
        return "\n".join(lines)


def build_report(
    task_name: str,
    task_type: str,
    agent_evals: List[AgentEvaluation],
    summary: str = "",
) -> EvaluationReport:
    """Rank agents by total_score (desc) and decide a winner."""
    sorted_agents = sorted(agent_evals, key=lambda a: a.total_score, reverse=True)
    for idx, agent in enumerate(sorted_agents, start=1):
        agent.rank = idx
    winner = None
    for agent in sorted_agents:
        if not agent.skipped and agent.gate_results:
            winner = agent.agent_name
            break

    return EvaluationReport(
        task_name=task_name,
        task_type=task_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        agents=sorted_agents,
        winner=winner,
        summary=summary or _default_summary(sorted_agents),
    )


def _default_summary(agents: List[AgentEvaluation]) -> str:
    if not agents:
        return "No agents produced results."
    best = agents[0]
    if best.skipped:
        return "All agents were skipped."
    parts = [f"{a.agent_name}: {a.total_score:.1f}" for a in agents]
    return f"Top: {best.agent_name} ({best.total_score:.1f}). Scores: {', '.join(parts)}"
