"""Requirement understanding stage.

This is a deterministic, rule-based analyzer. It intentionally does not call a
hosted LLM so the orchestrator is fully testable and runnable without
credentials. A real provider could be swapped in later via the same
`analyze(text) -> NormalizedRequirement` contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_BROWNFIELD_HINTS = ("existing", "without breaking", "legacy", "current system", "already", "add to")
_VAGUE_QUALITY_TERMS = {
    "safer": "what does 'safer' mean — rate limiting, destination allow-listing, link scanning, or something else?",
    "safe": "what safety property is required (scheme restriction, malware scanning, expiry, abuse limits)?",
    "secure": "what security property is required, and what threat is being mitigated?",
    "better": "what measurable outcome defines 'better' for this change?",
    "improve": "what metric should improve, and by how much?",
    "track usage": "what usage data is required (counts only, timestamps, referrers, user agents) and how long may it be retained?",
    "fast": "what latency or throughput target defines 'fast'?",
}
_GREENFIELD_HINTS = ("create", "build", "new", "greenfield", "from scratch")


@dataclass
class NormalizedRequirement:
    original_text: str
    mode: str  # "greenfield" | "brownfield" | "ambiguous"
    summary: str
    acceptance_criteria: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    risk_level: str = "low"  # "low" | "medium" | "high"
    requires_clarification: bool = False

    def to_dict(self) -> dict:
        return {
            "original_text": self.original_text,
            "mode": self.mode,
            "summary": self.summary,
            "acceptance_criteria": self.acceptance_criteria,
            "assumptions": self.assumptions,
            "ambiguities": self.ambiguities,
            "risk_level": self.risk_level,
            "requires_clarification": self.requires_clarification,
        }


class RequirementAnalyzer:
    """Rule-based stand-in for an LLM-backed requirement analyzer."""

    def analyze(self, text: str) -> NormalizedRequirement:
        lowered = text.lower()

        ambiguities = [
            question for term, question in _VAGUE_QUALITY_TERMS.items() if term in lowered
        ]

        is_brownfield = any(hint in lowered for hint in _BROWNFIELD_HINTS)
        is_greenfield = any(hint in lowered for hint in _GREENFIELD_HINTS)

        if ambiguities:
            mode = "ambiguous"
        elif is_brownfield:
            mode = "brownfield"
        elif is_greenfield:
            mode = "greenfield"
        else:
            mode = "greenfield"

        acceptance_criteria = [
            "Reject malformed or disallowed-scheme destination URLs.",
            "Generate unique short codes and handle collisions safely.",
            "Return a clear not-found response for unknown codes.",
            "Redirect only to the URL stored for the requested code.",
        ]
        assumptions = [
            "Only http and https destination schemes are permitted unless stated otherwise.",
            "SQLite persistence is acceptable for this prototype.",
        ]
        risk_level = "low"

        if "analytics" in lowered or "track usage" in lowered or "usage" in lowered:
            acceptance_criteria.append(
                "Record a click event without letting analytics failures break redirection."
            )

        if is_brownfield:
            acceptance_criteria.append("Preserve existing redirect behavior (no regressions).")
            assumptions.append("An existing, working short-link redirect path must not change its contract.")
            risk_level = "medium"

        if ambiguities:
            risk_level = "high"
            assumptions.append(
                "Until clarified, only low-risk, reversible safety defaults are applied "
                "(scheme allow-listing, minimal retained analytics fields)."
            )

        summary = (
            f"{mode.capitalize()} request: {text.strip()} "
            f"(derived {len(acceptance_criteria)} acceptance criteria, "
            f"{len(ambiguities)} open ambiguities)."
        )

        return NormalizedRequirement(
            original_text=text,
            mode=mode,
            summary=summary,
            acceptance_criteria=acceptance_criteria,
            assumptions=assumptions,
            ambiguities=ambiguities,
            risk_level=risk_level,
            requires_clarification=bool(ambiguities),
        )
