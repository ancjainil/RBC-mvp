"""Unit tests for TransactionAgent.

LLM calls are mocked — these tests verify the agent's signal logic and
report construction, not the LLM provider.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.transaction_agent import TransactionAgent, _deduplicate_signals
from src.models.enums import RiskLevel, SignalSeverity
from src.models.schemas import AgentReport, RiskSignal


@pytest.fixture
def agent() -> TransactionAgent:
    with patch("src.agents.base_agent._build_llm"), \
         patch("src.agents.base_agent._load_agent_config", return_value={
             "transaction_agent": {
                 "model_temperature": 0.0,
                 "max_tokens": 1024,
                 "amount_z_score_threshold": 2.5,
                 "time_anomaly_hour_start": 1,
                 "time_anomaly_hour_end": 5,
                 "geo_velocity_max_kmh": 900,
                 "high_risk_mcc_codes": ["5944", "5065"],
                 "prompt": "Analyze: {transaction_details} {profile_summary} {feature_scores}",
             }
         }):
        agent = TransactionAgent()
        agent._llm = AsyncMock()
    return agent


class TestTransactionAgent:
    @pytest.mark.asyncio
    async def test_analyze_returns_agent_report(
        self,
        agent: TransactionAgent,
        sample_transaction,
        customer_profile,
        mock_llm_response_low_risk: str,
    ) -> None:
        agent._llm.ainvoke = AsyncMock(
            return_value=MagicMock(content=mock_llm_response_low_risk)
        )
        report = await agent.analyze(sample_transaction, customer_profile)
        assert isinstance(report, AgentReport)
        assert report.agent_name == "transaction_agent"
        assert report.risk_level == RiskLevel.LOW
        assert 0 <= report.fraud_probability <= 1

    @pytest.mark.asyncio
    async def test_analyze_high_risk_transaction(
        self,
        agent: TransactionAgent,
        high_risk_transaction,
        customer_profile,
        mock_llm_response_high_risk: str,
    ) -> None:
        agent._llm.ainvoke = AsyncMock(
            return_value=MagicMock(content=mock_llm_response_high_risk)
        )
        report = await agent.analyze(high_risk_transaction, customer_profile)
        assert report.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        assert report.fraud_probability >= 0.5

    @pytest.mark.asyncio
    async def test_analyze_no_profile_fallback(
        self,
        agent: TransactionAgent,
        sample_transaction,
        mock_llm_response_low_risk: str,
    ) -> None:
        agent._llm.ainvoke = AsyncMock(
            return_value=MagicMock(content=mock_llm_response_low_risk)
        )
        report = await agent.analyze(sample_transaction, customer_profile=None)
        assert isinstance(report, AgentReport)

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_rules(
        self,
        agent: TransactionAgent,
        sample_transaction,
        customer_profile,
    ) -> None:
        from src.agents.base_agent import LLMCallError

        agent._llm.ainvoke = AsyncMock(side_effect=LLMCallError("API error"))
        agent._call_llm = AsyncMock(side_effect=LLMCallError("API error"))

        # Should not raise; should fall back to rule-based assessment
        report = await agent.analyze(sample_transaction, customer_profile)
        assert isinstance(report, AgentReport)
        assert report.fraud_probability >= 0


class TestDeduplicateSignals:
    def test_deduplication_keeps_highest_severity(self) -> None:
        signals = [
            RiskSignal(
                signal_type="amount_anomaly",
                description="low",
                severity=SignalSeverity.LOW,
                score=0.2,
                source_agent="txn",
            ),
            RiskSignal(
                signal_type="amount_anomaly",
                description="high",
                severity=SignalSeverity.HIGH,
                score=0.9,
                source_agent="txn",
            ),
        ]
        result = _deduplicate_signals(signals)
        assert len(result) == 1
        assert result[0].severity == SignalSeverity.HIGH

    def test_different_types_kept(self) -> None:
        signals = [
            RiskSignal(signal_type="a", description="a", score=0.5, source_agent="txn"),
            RiskSignal(signal_type="b", description="b", score=0.5, source_agent="txn"),
        ]
        result = _deduplicate_signals(signals)
        assert len(result) == 2
