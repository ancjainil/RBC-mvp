"""Unit tests for BehavioralAgent."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.behavioral_agent import BehavioralAgent
from src.models.enums import RiskLevel, SignalSeverity
from src.models.schemas import AgentReport, RiskSignal


@pytest.fixture
def agent() -> BehavioralAgent:
    with patch("src.agents.base_agent._build_llm"), \
         patch("src.agents.base_agent._load_agent_config", return_value={
             "behavioral_agent": {
                 "model_temperature": 0.0,
                 "max_tokens": 1024,
                 "time_windows_days": [7, 30, 90],
                 "velocity_alert_txn_per_hour": 5,
                 "category_shift_threshold": 0.40,
                 "amount_escalation_factor": 3.0,
                 "prompt": "{behavioral_summary} {behavioral_anomalies}",
             }
         }):
        a = BehavioralAgent()
        a._llm = AsyncMock()
    return a


class TestBehavioralAgent:
    @pytest.mark.asyncio
    async def test_no_profile_returns_medium_risk(
        self, agent: BehavioralAgent, sample_transaction
    ) -> None:
        report = await agent.analyze(sample_transaction, customer_profile=None, prior_signals=[])
        assert isinstance(report, AgentReport)
        assert report.risk_level == RiskLevel.MEDIUM
        assert any(
            s.signal_type == "no_customer_profile" for s in report.risk_signals
        )

    @pytest.mark.asyncio
    async def test_normal_transaction_low_risk(
        self, agent: BehavioralAgent, sample_transaction, customer_profile
    ) -> None:
        llm_resp = '{"risk_level":"LOW","fraud_probability":0.05,"confidence":0.9,"reasoning":"Normal spending","risk_signals":[]}'
        agent._llm.ainvoke = AsyncMock(return_value=MagicMock(content=llm_resp))
        report = await agent.analyze(sample_transaction, customer_profile, prior_signals=[])
        assert report.risk_level == RiskLevel.LOW

    @pytest.mark.asyncio
    async def test_new_device_triggers_signal(
        self, agent: BehavioralAgent, sample_transaction, customer_profile
    ) -> None:
        llm_resp = '{"risk_level":"MEDIUM","fraud_probability":0.45,"confidence":0.7,"reasoning":"New device","risk_signals":[]}'
        agent._llm.ainvoke = AsyncMock(return_value=MagicMock(content=llm_resp))

        # Override device to an unknown one
        sample_transaction.device_fingerprint = "dev_completely_unknown_xyz"
        report = await agent.analyze(sample_transaction, customer_profile, prior_signals=[])
        signal_types = [s.signal_type for s in report.risk_signals]
        assert "new_device_fingerprint" in signal_types

    @pytest.mark.asyncio
    async def test_amount_escalation_detected(
        self, agent: BehavioralAgent, customer_profile
    ) -> None:
        from decimal import Decimal
        from datetime import datetime, timezone
        from src.models.enums import MerchantCategory, TransactionChannel, TransactionType
        from src.models.schemas import Transaction

        # Customer mean ~65 CAD; 3× threshold = 195; use 1000 to trigger
        large_txn = Transaction(
            transaction_id="txn_large",
            customer_id="cust_abc123",
            amount=Decimal("1000.00"),
            merchant_id="m1",
            merchant_name="Big Store",
            merchant_category_code="5065",
            merchant_category=MerchantCategory.ELECTRONICS,
            transaction_type=TransactionType.PURCHASE,
            channel=TransactionChannel.ONLINE,
            card_present=False,
            timestamp=datetime(2024, 11, 15, 14, 0, tzinfo=timezone.utc),
        )

        llm_resp = '{"risk_level":"HIGH","fraud_probability":0.75,"confidence":0.8,"reasoning":"Escalation","risk_signals":[]}'
        agent._llm.ainvoke = AsyncMock(return_value=MagicMock(content=llm_resp))
        report = await agent.analyze(large_txn, customer_profile, prior_signals=[])
        signal_types = [s.signal_type for s in report.risk_signals]
        assert "amount_escalation" in signal_types
