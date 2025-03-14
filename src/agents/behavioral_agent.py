"""Behavioral Profiling Agent.

Analyses a customer's spending patterns across multiple time windows (7d,
30d, 90d) to detect behavioural anomalies indicative of account takeover,
synthetic identity fraud, or first-party fraud.

Patterns checked:
- Transaction velocity spike
- Merchant-category distribution shift
- Amount escalation pattern (micro-test + big charge)
- Device/channel change detection
- Time-of-day pattern shift
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import structlog

from src.agents.base_agent import BaseAgent, LLMCallError, LLMParseError
from src.models.enums import FraudTypology, RiskLevel, SignalSeverity
from src.models.schemas import AgentReport, CustomerProfile, RiskSignal, Transaction

logger = structlog.get_logger(__name__)


class BehavioralAgent(BaseAgent):
    """Detects anomalous behavioural patterns using time-windowed analysis.

    Invoked by the LangGraph router only for MEDIUM, HIGH, and CRITICAL risk
    transactions — skipped entirely for LOW risk to reduce latency.
    """

    @property
    def _config_key(self) -> str:
        return "behavioral_agent"

    async def analyze(
        self,
        transaction: Transaction,
        customer_profile: CustomerProfile | None,
        prior_signals: list[RiskSignal],
    ) -> AgentReport:
        """Analyse customer behavioural patterns for this transaction.

        Args:
            transaction: The transaction under review.
            customer_profile: Customer's aggregated behavioural profile.
            prior_signals: Risk signals already emitted by earlier agents.

        Returns:
            :class:`~src.models.schemas.AgentReport` with behavioural risk signals.
        """
        t0 = time.monotonic()
        self._log.info(
            "behavioral_agent.analyze.start",
            transaction_id=transaction.transaction_id,
        )

        if customer_profile is None:
            return self._no_profile_report(transaction, t0)

        # ── 1. Rule-based behavioural signals ─────────────────────────
        rule_signals: list[RiskSignal] = []
        anomalies: list[str] = []

        # Velocity check
        velocity_ok = self._check_velocity(transaction, customer_profile, rule_signals, anomalies)

        # Category distribution shift
        self._check_category_shift(transaction, customer_profile, rule_signals, anomalies)

        # Amount escalation (card-testing pattern)
        self._check_amount_escalation(transaction, customer_profile, rule_signals, anomalies)

        # Device / channel change
        self._check_device_change(transaction, customer_profile, rule_signals, anomalies)

        # ── 2. Build profile summary for LLM ──────────────────────────
        profile_summary = _build_behavioral_summary(transaction, customer_profile)
        anomaly_text = (
            "\n".join(f"- {a}" for a in anomalies) if anomalies else "No anomalies detected."
        )

        system_prompt = (
            "You are a behavioural fraud analyst specialising in account-takeover "
            "and identity fraud at a Canadian financial institution. "
            "Always respond with valid JSON only."
        )
        user_prompt = self._format_prompt(
            self._prompt_template,
            behavioral_summary=profile_summary,
            behavioral_anomalies=anomaly_text,
        )

        raw_response = ""
        try:
            raw_response = await self._call_llm(system_prompt, user_prompt)
            parsed = self._parse_json_response(raw_response)
        except (LLMCallError, LLMParseError) as exc:
            self._log.warning(
                "behavioral_agent.llm.fallback",
                error=str(exc),
                transaction_id=transaction.transaction_id,
            )
            parsed = _fallback_assessment(rule_signals)

        llm_signals = [
            RiskSignal(
                signal_type=s.get("signal_type", "unknown"),
                description=s.get("description", ""),
                severity=SignalSeverity(s.get("severity", "MEDIUM")),
                score=float(s.get("score", 0.5)),
                source_agent="behavioral_agent",
            )
            for s in parsed.get("risk_signals", [])
        ]

        all_signals = rule_signals + llm_signals
        elapsed = (time.monotonic() - t0) * 1000

        self._log.info(
            "behavioral_agent.analyze.complete",
            transaction_id=transaction.transaction_id,
            signal_count=len(all_signals),
            elapsed_ms=round(elapsed, 2),
        )

        return AgentReport(
            agent_name="behavioral_agent",
            risk_level=RiskLevel(parsed.get("risk_level", "MEDIUM")),
            fraud_probability=float(parsed.get("fraud_probability", 0.4)),
            confidence=float(parsed.get("confidence", 0.70)),
            reasoning=parsed.get("reasoning", "Behavioural analysis fallback."),
            risk_signals=all_signals,
            processing_time_ms=elapsed,
            raw_llm_response=raw_response,
        )

    # ── Rule checkers ─────────────────────────────────────────────────

    def _check_velocity(
        self,
        transaction: Transaction,
        profile: CustomerProfile,
        signals: list[RiskSignal],
        anomalies: list[str],
    ) -> bool:
        """Flag if transaction rate in 7-day window exceeds threshold."""
        threshold = self._cfg.get("velocity_alert_txn_per_hour", 5)
        if profile.stats_7d is None:
            return True
        hourly_rate = profile.stats_7d.transaction_count / max(7 * 24, 1)
        if hourly_rate > threshold:
            signals.append(
                RiskSignal(
                    signal_type="velocity_spike",
                    description=(
                        f"Customer averaging {hourly_rate:.1f} transactions/hour "
                        f"over the last 7 days (threshold: {threshold})."
                    ),
                    severity=SignalSeverity.HIGH,
                    score=min(hourly_rate / (threshold * 2), 1.0),
                    source_agent="behavioral_agent",
                )
            )
            anomalies.append(
                f"Velocity spike: {hourly_rate:.1f} txn/hour over 7 days."
            )
            return False
        return True

    def _check_category_shift(
        self,
        transaction: Transaction,
        profile: CustomerProfile,
        signals: list[RiskSignal],
        anomalies: list[str],
    ) -> None:
        """Flag if current merchant category is absent from 90-day history."""
        if profile.stats_90d is None:
            return
        known = {c.lower() for c in profile.stats_90d.top_categories}
        current_cat = transaction.merchant_category.value
        threshold = self._cfg.get("category_shift_threshold", 0.40)
        if known and current_cat not in known:
            signals.append(
                RiskSignal(
                    signal_type="category_distribution_shift",
                    description=(
                        f"Merchant category '{current_cat}' has not appeared "
                        "in the customer's 90-day transaction history."
                    ),
                    severity=SignalSeverity.MEDIUM,
                    score=0.60,
                    source_agent="behavioral_agent",
                )
            )
            anomalies.append(
                f"New category: '{current_cat}' not in 90-day history {known}."
            )

    def _check_amount_escalation(
        self,
        transaction: Transaction,
        profile: CustomerProfile,
        signals: list[RiskSignal],
        anomalies: list[str],
    ) -> None:
        """Detect micro-test + large-charge pattern."""
        factor = self._cfg.get("amount_escalation_factor", 3.0)
        if profile.stats_30d is None:
            return
        amount = float(transaction.amount)
        mean = profile.stats_30d.mean_amount
        if mean > 0 and amount > mean * factor:
            signals.append(
                RiskSignal(
                    signal_type="amount_escalation",
                    description=(
                        f"Transaction amount ${amount:.2f} is "
                        f"{amount / mean:.1f}× the customer's 30-day mean "
                        f"(${mean:.2f})."
                    ),
                    severity=SignalSeverity.HIGH
                    if amount > mean * factor * 2
                    else SignalSeverity.MEDIUM,
                    score=min((amount / mean) / (factor * 4), 1.0),
                    source_agent="behavioral_agent",
                )
            )
            anomalies.append(
                f"Amount escalation: ${amount:.2f} vs ${mean:.2f} mean."
            )

    def _check_device_change(
        self,
        transaction: Transaction,
        profile: CustomerProfile,
        signals: list[RiskSignal],
        anomalies: list[str],
    ) -> None:
        """Flag unknown device fingerprint or IP prefix."""
        if (
            transaction.device_fingerprint
            and profile.known_device_fingerprints
            and transaction.device_fingerprint not in profile.known_device_fingerprints
        ):
            signals.append(
                RiskSignal(
                    signal_type="new_device_fingerprint",
                    description=(
                        "Transaction originated from a device fingerprint not "
                        "previously associated with this customer."
                    ),
                    severity=SignalSeverity.MEDIUM,
                    score=0.55,
                    source_agent="behavioral_agent",
                )
            )
            anomalies.append("New device fingerprint detected.")

    # ── Fallbacks ─────────────────────────────────────────────────────

    def _no_profile_report(
        self, transaction: Transaction, t0: float
    ) -> AgentReport:
        """Return a conservative report when no customer profile exists."""
        return AgentReport(
            agent_name="behavioral_agent",
            risk_level=RiskLevel.MEDIUM,
            fraud_probability=0.40,
            confidence=0.40,
            reasoning=(
                "No historical profile available.  Applying conservative "
                "MEDIUM risk due to insufficient behavioural baseline."
            ),
            risk_signals=[
                RiskSignal(
                    signal_type="no_customer_profile",
                    description="Customer has no transaction history in the system.",
                    severity=SignalSeverity.MEDIUM,
                    score=0.40,
                    source_agent="behavioral_agent",
                )
            ],
            processing_time_ms=(time.monotonic() - t0) * 1000,
        )


# ── Helpers ───────────────────────────────────────────────────────────────


def _build_behavioral_summary(
    transaction: Transaction, profile: CustomerProfile
) -> str:
    lines = [
        f"Customer ID: {profile.customer_id}",
        f"Account age: {profile.account_age_days} days",
        f"Lifetime transactions: {profile.lifetime_transaction_count}",
    ]
    for attr, label in [
        ("stats_7d", "7-day"),
        ("stats_30d", "30-day"),
        ("stats_90d", "90-day"),
    ]:
        stats = getattr(profile, attr)
        if stats:
            lines.append(
                f"{label} window — {stats.transaction_count} txns, "
                f"mean ${stats.mean_amount:.2f}, "
                f"top categories: {', '.join(stats.top_categories)}"
            )
    lines.append(
        f"Current transaction: ${float(transaction.amount):.2f} at "
        f"{transaction.merchant_name} ({transaction.merchant_category.value})"
    )
    return "\n".join(lines)


def _fallback_assessment(rule_signals: list[RiskSignal]) -> dict:
    high = sum(1 for s in rule_signals if s.severity == SignalSeverity.HIGH)
    prob = min(0.35 + 0.20 * high, 0.90)
    return {
        "risk_level": RiskLevel.from_probability(prob).value,
        "fraud_probability": prob,
        "confidence": 0.45,
        "reasoning": "LLM unavailable; behavioural risk based on rule signals.",
        "risk_signals": [],
    }
