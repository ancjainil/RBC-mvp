"""Orchestrator Agent.

Synthesises the reports from all specialised agents into a single,
compliance-ready fraud determination.  This is the final node in every
execution path of the LangGraph workflow.

The orchestrator:
1. Computes a weighted-average fraud probability across available reports
2. Calls the LLM for a coherent natural-language explanation
3. Assigns the recommended action (approve / review / block / escalate)
4. Stamps the full audit trail onto the final assessment
"""

from __future__ import annotations

import time
from datetime import datetime

import structlog

from src.agents.base_agent import BaseAgent, LLMCallError, LLMParseError
from src.models.enums import FraudTypology, RecommendedAction, RiskLevel
from src.models.schemas import (
    AgentReport,
    AuditRecord,
    FraudAssessment,
    RiskSignal,
    Transaction,
)

logger = structlog.get_logger(__name__)


class OrchestratorAgent(BaseAgent):
    """Final decision agent that synthesises all prior agent outputs.

    Weights (from ``agent_config.yaml``):
    - transaction_agent: 35 %
    - behavioral_agent:  30 %
    - context_agent:     35 %

    If an agent was not invoked (LOW risk fast-path), its weight is
    redistributed proportionally among the agents that were invoked.
    """

    @property
    def _config_key(self) -> str:
        return "orchestrator_agent"

    async def decide(
        self,
        transaction: Transaction,
        transaction_report: AgentReport | None,
        behavioral_report: AgentReport | None,
        context_report: AgentReport | None,
        risk_signals: list[RiskSignal],
        audit_trail: list[AuditRecord],
    ) -> FraudAssessment:
        """Produce the final fraud assessment.

        Args:
            transaction: The transaction under review.
            transaction_report: Report from the Transaction Analysis Agent.
            behavioral_report: Report from the Behavioral Profiling Agent.
            context_report: Report from the Context Enrichment Agent.
            risk_signals: All accumulated risk signals.
            audit_trail: All audit records emitted so far.

        Returns:
            A complete :class:`~src.models.schemas.FraudAssessment`.
        """
        t0 = time.monotonic()
        self._log.info(
            "orchestrator.decide.start",
            transaction_id=transaction.transaction_id,
        )

        # ── 1. Weighted probability aggregation ────────────────────────
        weights = {
            "transaction": self._cfg.get("signal_weight_transaction", 0.35),
            "behavioral": self._cfg.get("signal_weight_behavioral", 0.30),
            "context": self._cfg.get("signal_weight_context", 0.35),
        }

        reports_map = {
            "transaction": transaction_report,
            "behavioral": behavioral_report,
            "context": context_report,
        }

        available = {k: v for k, v in reports_map.items() if v is not None}
        if not available:
            # Degenerate case: all agents failed
            fraud_prob = 0.5
        else:
            total_weight = sum(weights[k] for k in available)
            fraud_prob = sum(
                weights[k] * r.fraud_probability
                for k, r in available.items()
            ) / total_weight

        risk_level = RiskLevel.from_probability(fraud_prob)

        # ── 2. Collect regulatory flags and fraud type ─────────────────
        all_reports = [r for r in reports_map.values() if r is not None]
        regulatory_flags = list(
            {flag for r in all_reports for flag in r.regulatory_flags}
        )

        # Prefer context agent's typology; fall back to transaction agent's
        fraud_type: FraudTypology | None = None
        for r in [context_report, transaction_report, behavioral_report]:
            if r and r.fraud_type:
                fraud_type = r.fraud_type
                break

        # ── 3. LLM synthesis ──────────────────────────────────────────
        system_prompt = (
            "You are the chief fraud decisioning officer at a major Canadian bank. "
            "Synthesise the provided agent assessments into a single final determination. "
            "Always respond with valid JSON only."
        )
        user_prompt = self._format_prompt(
            self._prompt_template,
            transaction_assessment=_format_report(transaction_report, "Transaction Analysis"),
            behavioral_assessment=_format_report(behavioral_report, "Behavioral Profiling"),
            context_assessment=_format_report(context_report, "Context Enrichment"),
        )

        raw_response = ""
        try:
            raw_response = await self._call_llm(system_prompt, user_prompt)
            parsed = self._parse_json_response(raw_response)
        except (LLMCallError, LLMParseError) as exc:
            self._log.warning(
                "orchestrator.llm.fallback",
                error=str(exc),
                transaction_id=transaction.transaction_id,
            )
            parsed = _fallback_decision(fraud_prob, risk_level, fraud_type)

        # ── 4. Reconcile LLM output with weighted aggregation ──────────
        # Trust the weighted probability over LLM self-reported probability
        # but respect the LLM's qualitative flags and explanation.
        final_risk = RiskLevel(parsed.get("risk_level", risk_level.value))
        final_prob = float(parsed.get("fraud_probability", fraud_prob))
        final_prob = (final_prob + fraud_prob) / 2  # blend for stability

        is_fraudulent = final_prob >= 0.50 or final_risk in {
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        }

        action_raw = parsed.get("recommended_action", _default_action(final_prob))
        try:
            action = RecommendedAction(action_raw)
        except ValueError:
            action = _default_action_enum(final_prob)

        elapsed = (time.monotonic() - t0) * 1000

        self._log.info(
            "orchestrator.decide.complete",
            transaction_id=transaction.transaction_id,
            risk_level=final_risk,
            fraud_prob=round(final_prob, 3),
            is_fraudulent=is_fraudulent,
            action=action,
            elapsed_ms=round(elapsed, 2),
        )

        return FraudAssessment(
            transaction_id=transaction.transaction_id,
            risk_level=final_risk,
            fraud_probability=round(final_prob, 4),
            is_fraudulent=is_fraudulent,
            fraud_type=fraud_type,
            explanation=parsed.get("explanation", "Automated fraud assessment."),
            risk_signals=risk_signals,
            agent_reports=all_reports,
            recommended_action=action,
            regulatory_flags=regulatory_flags + parsed.get("regulatory_flags", []),
            processing_time_ms=elapsed,
            model_version="1.0.0",
            audit_trail=audit_trail,
            assessed_at=datetime.utcnow(),
        )


# ── Helpers ───────────────────────────────────────────────────────────────


def _format_report(report: AgentReport | None, label: str) -> str:
    if report is None:
        return f"{label}: Not invoked (fast-path routing)."
    return (
        f"{label}:\n"
        f"  Risk Level: {report.risk_level.value}\n"
        f"  Fraud Probability: {report.fraud_probability:.3f}\n"
        f"  Confidence: {report.confidence:.2f}\n"
        f"  Fraud Type: {report.fraud_type or 'N/A'}\n"
        f"  Regulatory Flags: {report.regulatory_flags or 'None'}\n"
        f"  Key Signals: {[s.signal_type for s in report.risk_signals[:3]]}\n"
        f"  Reasoning: {report.reasoning[:300]}"
    )


def _fallback_decision(
    fraud_prob: float,
    risk_level: RiskLevel,
    fraud_type: FraudTypology | None,
) -> dict:
    action = _default_action(fraud_prob)
    return {
        "risk_level": risk_level.value,
        "fraud_probability": fraud_prob,
        "is_fraudulent": fraud_prob >= 0.50,
        "fraud_type": fraud_type.value if fraud_type else None,
        "recommended_action": action,
        "explanation": (
            "Automated fraud assessment based on rule-based and ML signals. "
            "LLM synthesis was unavailable; weighted aggregation applied."
        ),
        "regulatory_flags": [],
    }


def _default_action(prob: float) -> str:
    if prob < 0.20:
        return RecommendedAction.APPROVE.value
    if prob < 0.60:
        return RecommendedAction.REVIEW.value
    if prob < 0.85:
        return RecommendedAction.BLOCK.value
    return RecommendedAction.ESCALATE.value


def _default_action_enum(prob: float) -> RecommendedAction:
    return RecommendedAction(_default_action(prob))
