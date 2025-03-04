"""Transaction Analysis Agent.

Performs feature-based anomaly scoring on a single transaction and
uses the LLM to produce a structured fraud risk assessment.

Features computed:
- Amount z-score vs customer 30-day baseline
- Time-of-day anomaly score
- Geo-velocity check against most recent transaction
- Merchant category risk score
- Card-present / channel consistency flag
"""

from __future__ import annotations

import time
from datetime import datetime

import structlog

from src.agents.base_agent import AgentError, BaseAgent, LLMCallError, LLMParseError
from src.data.feature_engineering import FeatureEngineer
from src.models.enums import FraudTypology, RiskLevel, SignalSeverity
from src.models.schemas import AgentReport, CustomerProfile, RiskSignal, Transaction

logger = structlog.get_logger(__name__)


class TransactionAgent(BaseAgent):
    """Analyses a single transaction against the customer's historical baseline.

    This agent is always the first node in the fraud detection graph.  It
    produces a preliminary risk assessment that the router uses to decide
    whether deeper behavioural or contextual analysis is needed.
    """

    def __init__(self) -> None:
        super().__init__()
        self._feature_eng = FeatureEngineer()

    @property
    def _config_key(self) -> str:
        return "transaction_agent"

    async def analyze(
        self,
        transaction: Transaction,
        customer_profile: CustomerProfile | None,
    ) -> AgentReport:
        """Run the transaction analysis pipeline.

        Args:
            transaction: The transaction to evaluate.
            customer_profile: Customer's historical profile for anomaly scoring.
                If ``None``, the agent uses conservative (high-uncertainty) defaults.

        Returns:
            An :class:`~src.models.schemas.AgentReport` with risk assessment.
        """
        t0 = time.monotonic()
        self._log.info(
            "transaction_agent.analyze.start",
            transaction_id=transaction.transaction_id,
        )

        # ── 1. Compute features ───────────────────────────────────────
        features = self._feature_eng.compute_transaction_features(
            transaction=transaction,
            profile=customer_profile,
        )

        # ── 2. Build preliminary rule-based signals ────────────────────
        rule_signals: list[RiskSignal] = []

        if features.get("amount_z_score", 0) > self._cfg.get("amount_z_score_threshold", 2.5):
            rule_signals.append(
                RiskSignal(
                    signal_type="amount_anomaly",
                    description=(
                        f"Transaction amount ${float(transaction.amount):.2f} is "
                        f"{features['amount_z_score']:.1f} standard deviations above "
                        "the customer's 30-day mean."
                    ),
                    severity=SignalSeverity.HIGH
                    if features["amount_z_score"] > 4.0
                    else SignalSeverity.MEDIUM,
                    score=min(features["amount_z_score"] / 6.0, 1.0),
                    source_agent="transaction_agent",
                )
            )

        if features.get("time_anomaly", False):
            rule_signals.append(
                RiskSignal(
                    signal_type="time_of_day_anomaly",
                    description=(
                        f"Transaction at {transaction.timestamp.strftime('%H:%M UTC')} "
                        "is outside this customer's typical activity hours."
                    ),
                    severity=SignalSeverity.LOW,
                    score=0.4,
                    source_agent="transaction_agent",
                )
            )

        geo_violation = features.get("geo_velocity_kmh", 0.0)
        if geo_violation > self._cfg.get("geo_velocity_max_kmh", 900):
            rule_signals.append(
                RiskSignal(
                    signal_type="geo_velocity_impossible_travel",
                    description=(
                        f"Implied travel speed of {geo_violation:.0f} km/h between "
                        "this and the previous transaction is physically impossible."
                    ),
                    severity=SignalSeverity.HIGH,
                    score=1.0,
                    source_agent="transaction_agent",
                )
            )

        mcc_risk = transaction.merchant_category.base_risk_score
        if mcc_risk >= 0.50:
            rule_signals.append(
                RiskSignal(
                    signal_type="high_risk_merchant_category",
                    description=(
                        f"Merchant category '{transaction.merchant_category.value}' "
                        f"has elevated baseline fraud risk ({mcc_risk:.0%})."
                    ),
                    severity=SignalSeverity.MEDIUM,
                    score=mcc_risk,
                    source_agent="transaction_agent",
                )
            )

        if not transaction.card_present and transaction.channel.card_present:
            rule_signals.append(
                RiskSignal(
                    signal_type="channel_card_mismatch",
                    description="Card-not-present flag set but channel implies card present.",
                    severity=SignalSeverity.MEDIUM,
                    score=0.5,
                    source_agent="transaction_agent",
                )
            )

        # ── 3. LLM assessment ─────────────────────────────────────────
        system_prompt = (
            "You are a financial transaction fraud analyst at a major Canadian bank. "
            "Always respond with valid JSON only — no prose outside the JSON object."
        )
        user_prompt = self._format_prompt(
            self._prompt_template,
            transaction_details=_format_transaction(transaction),
            profile_summary=_format_profile(customer_profile),
            feature_scores=_format_features(features),
        )

        raw_response = ""
        try:
            raw_response = await self._call_llm(system_prompt, user_prompt)
            parsed = self._parse_json_response(raw_response)
        except (LLMCallError, LLMParseError) as exc:
            self._log.warning(
                "transaction_agent.llm.fallback",
                error=str(exc),
                transaction_id=transaction.transaction_id,
            )
            parsed = _fallback_assessment(rule_signals)

        # ── 4. Build report ────────────────────────────────────────────
        llm_signals = [
            RiskSignal(
                signal_type=s.get("signal_type", "unknown"),
                description=s.get("description", ""),
                severity=SignalSeverity(s.get("severity", "MEDIUM")),
                score=float(s.get("score", 0.5)),
                source_agent="transaction_agent",
            )
            for s in parsed.get("risk_signals", [])
        ]

        all_signals = _deduplicate_signals(rule_signals + llm_signals)
        fraud_prob = float(parsed.get("fraud_probability", 0.3))
        risk_level = RiskLevel(parsed.get("risk_level", "MEDIUM"))

        elapsed = (time.monotonic() - t0) * 1000
        self._log.info(
            "transaction_agent.analyze.complete",
            transaction_id=transaction.transaction_id,
            risk_level=risk_level,
            fraud_prob=round(fraud_prob, 3),
            elapsed_ms=round(elapsed, 2),
        )

        return AgentReport(
            agent_name="transaction_agent",
            risk_level=risk_level,
            fraud_probability=fraud_prob,
            confidence=float(parsed.get("confidence", 0.75)),
            reasoning=parsed.get("reasoning", "No LLM reasoning available."),
            risk_signals=all_signals,
            fraud_type=None,
            processing_time_ms=elapsed,
            raw_llm_response=raw_response,
        )


# ── Formatting helpers ────────────────────────────────────────────────────


def _format_transaction(t: Transaction) -> str:
    return (
        f"ID: {t.transaction_id}\n"
        f"Amount: {t.currency} {float(t.amount):.2f}\n"
        f"Merchant: {t.merchant_name} (MCC {t.merchant_category_code})\n"
        f"Category: {t.merchant_category.value}\n"
        f"Channel: {t.channel.value} (card present: {t.card_present})\n"
        f"Timestamp: {t.timestamp.isoformat()}\n"
        f"Location: {t.location}\n"
        f"Device fingerprint: {t.device_fingerprint or 'N/A'}\n"
        f"IP address: {t.ip_address or 'N/A'}\n"
        f"Recurring: {t.recurring}"
    )


def _format_profile(p: CustomerProfile | None) -> str:
    if p is None:
        return "No historical profile available (new customer or lookup failed)."
    lines = [
        f"Customer ID: {p.customer_id}",
        f"Account age: {p.account_age_days} days",
        f"Lifetime transactions: {p.lifetime_transaction_count}",
    ]
    if p.stats_30d:
        lines += [
            f"30-day mean amount: ${p.stats_30d.mean_amount:.2f} "
            f"(±${p.stats_30d.std_amount:.2f})",
            f"30-day transaction count: {p.stats_30d.transaction_count}",
            f"Top categories: {', '.join(p.stats_30d.top_categories)}",
        ]
    if p.last_transaction_timestamp:
        lines.append(f"Last transaction: {p.last_transaction_timestamp.isoformat()}")
    if p.last_known_location:
        lines.append(
            f"Last known location: {p.last_known_location.city or 'unknown'} "
            f"({p.last_known_location.lat:.4f}, {p.last_known_location.lon:.4f})"
        )
    return "\n".join(lines)


def _format_features(features: dict) -> str:
    return "\n".join(f"  {k}: {v}" for k, v in features.items())


def _fallback_assessment(rule_signals: list[RiskSignal]) -> dict:
    """Conservative fallback when the LLM call fails."""
    high_signals = [s for s in rule_signals if s.severity == SignalSeverity.HIGH]
    prob = min(0.3 + 0.2 * len(high_signals), 0.9)
    level = RiskLevel.from_probability(prob)
    return {
        "risk_level": level.value,
        "fraud_probability": prob,
        "confidence": 0.50,
        "reasoning": "LLM unavailable; assessment based on rule-based signals only.",
        "risk_signals": [],
    }


def _deduplicate_signals(signals: list[RiskSignal]) -> list[RiskSignal]:
    """Remove duplicate signal types, keeping the highest-severity instance."""
    seen: dict[str, RiskSignal] = {}
    order = {SignalSeverity.LOW: 0, SignalSeverity.MEDIUM: 1, SignalSeverity.HIGH: 2}
    for sig in signals:
        existing = seen.get(sig.signal_type)
        if existing is None or order[sig.severity] > order[existing.severity]:
            seen[sig.signal_type] = sig
    return list(seen.values())
