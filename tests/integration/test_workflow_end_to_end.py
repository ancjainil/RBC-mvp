"""Integration tests for the full LangGraph workflow.

These tests compile the real graph with mocked LLM clients so that
the full routing logic is exercised without real API calls.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.graph.state import initial_state
from src.models.enums import MerchantCategory, RiskLevel, TransactionChannel, TransactionType
from src.models.schemas import Transaction


def _low_risk_llm():
    return AsyncMock(
        return_value=MagicMock(
            content='{"risk_level":"LOW","fraud_probability":0.05,"confidence":0.9,"reasoning":"Normal","risk_signals":[]}'
        )
    )


def _high_risk_llm():
    return AsyncMock(
        return_value=MagicMock(
            content='{"risk_level":"HIGH","fraud_probability":0.82,"confidence":0.8,"reasoning":"Suspicious","risk_signals":[{"signal_type":"amount_anomaly","description":"High amount","severity":"HIGH","score":0.9}]}'
        )
    )


def _orchestrator_llm(action: str = "approve"):
    return AsyncMock(
        return_value=MagicMock(
            content=f'{{"risk_level":"LOW","fraud_probability":0.05,"is_fraudulent":false,"fraud_type":null,"recommended_action":"{action}","explanation":"System approved the transaction.","regulatory_flags":[]}}'
        )
    )


@pytest.fixture
def mock_retriever():
    r = MagicMock()
    r.aretrieve = AsyncMock(return_value=[])
    return r


@pytest.mark.asyncio
async def test_low_risk_fast_path(sample_transaction, customer_profile, mock_retriever) -> None:
    """LOW risk transactions should skip behavioral and context agents."""
    from src.agents.behavioral_agent import BehavioralAgent
    from src.agents.context_agent import ContextAgent
    from src.agents.orchestrator import OrchestratorAgent
    from src.agents.transaction_agent import TransactionAgent
    from src.graph.workflow import compile_graph

    with patch("src.agents.base_agent._build_llm"), \
         patch("src.agents.base_agent._load_agent_config", return_value={
             "transaction_agent": {"model_temperature": 0, "max_tokens": 512, "amount_z_score_threshold": 2.5, "time_anomaly_hour_start": 1, "time_anomaly_hour_end": 5, "geo_velocity_max_kmh": 900, "high_risk_mcc_codes": [], "prompt": "{transaction_details} {profile_summary} {feature_scores}"},
             "behavioral_agent": {"model_temperature": 0, "max_tokens": 512, "velocity_alert_txn_per_hour": 5, "category_shift_threshold": 0.4, "amount_escalation_factor": 3.0, "prompt": "{behavioral_summary} {behavioral_anomalies}"},
             "context_agent": {"model_temperature": 0, "max_tokens": 512, "retrieval_top_k": 5, "retrieval_similarity_threshold": 0.75, "rerank_top_k": 3, "prompt": "{risk_signals_summary} {retrieved_context}"},
             "orchestrator_agent": {"model_temperature": 0, "max_tokens": 512, "signal_weight_transaction": 0.35, "signal_weight_behavioral": 0.30, "signal_weight_context": 0.35, "prompt": "{transaction_assessment} {behavioral_assessment} {context_assessment}"},
         }):
        ta = TransactionAgent()
        ta._llm = _low_risk_llm()
        ba = BehavioralAgent()
        ba._llm = _low_risk_llm()
        ca = ContextAgent(retriever=mock_retriever)
        ca._llm = _low_risk_llm()
        oa = OrchestratorAgent()
        oa._llm = _orchestrator_llm("approve")

        graph = compile_graph(ta, ba, ca, oa)
        state = initial_state(transaction=sample_transaction, customer_profile=customer_profile)
        result = await graph.ainvoke(state)

    assert result["final_assessment"] is not None
    assert result["final_assessment"].risk_level == RiskLevel.LOW
    # Behavioral and context agents should not have been called (fast path)
    assert result.get("behavioral_analysis") is None
    assert result.get("context_enrichment") is None


@pytest.mark.asyncio
async def test_high_risk_full_path(high_risk_transaction, customer_profile, mock_retriever) -> None:
    """HIGH risk transactions should invoke all three agents."""
    from src.agents.behavioral_agent import BehavioralAgent
    from src.agents.context_agent import ContextAgent
    from src.agents.orchestrator import OrchestratorAgent
    from src.agents.transaction_agent import TransactionAgent
    from src.graph.workflow import compile_graph

    high_risk_orch_resp = '{"risk_level":"HIGH","fraud_probability":0.82,"is_fraudulent":true,"fraud_type":"card_not_present","recommended_action":"block","explanation":"High-risk CNP transaction.","regulatory_flags":[]}'

    with patch("src.agents.base_agent._build_llm"), \
         patch("src.agents.base_agent._load_agent_config", return_value={
             "transaction_agent": {"model_temperature": 0, "max_tokens": 512, "amount_z_score_threshold": 2.5, "time_anomaly_hour_start": 1, "time_anomaly_hour_end": 5, "geo_velocity_max_kmh": 900, "high_risk_mcc_codes": ["5065"], "prompt": "{transaction_details} {profile_summary} {feature_scores}"},
             "behavioral_agent": {"model_temperature": 0, "max_tokens": 512, "velocity_alert_txn_per_hour": 5, "category_shift_threshold": 0.4, "amount_escalation_factor": 3.0, "prompt": "{behavioral_summary} {behavioral_anomalies}"},
             "context_agent": {"model_temperature": 0, "max_tokens": 512, "retrieval_top_k": 5, "retrieval_similarity_threshold": 0.75, "rerank_top_k": 3, "prompt": "{risk_signals_summary} {retrieved_context}"},
             "orchestrator_agent": {"model_temperature": 0, "max_tokens": 512, "signal_weight_transaction": 0.35, "signal_weight_behavioral": 0.30, "signal_weight_context": 0.35, "prompt": "{transaction_assessment} {behavioral_assessment} {context_assessment}"},
         }):
        ta = TransactionAgent()
        ta._llm = _high_risk_llm()
        ba = BehavioralAgent()
        ba._llm = _high_risk_llm()
        ca = ContextAgent(retriever=mock_retriever)
        ca._llm = AsyncMock(return_value=MagicMock(content='{"risk_level":"HIGH","fraud_probability":0.88,"confidence":0.85,"fraud_type":"card_not_present","regulatory_flags":[],"reasoning":"Matches CNP pattern","risk_signals":[]}'))
        oa = OrchestratorAgent()
        oa._llm = AsyncMock(return_value=MagicMock(content=high_risk_orch_resp))

        graph = compile_graph(ta, ba, ca, oa)
        state = initial_state(transaction=high_risk_transaction, customer_profile=customer_profile)
        result = await graph.ainvoke(state)

    assert result["final_assessment"] is not None
    assert result["final_assessment"].is_fraudulent is True
    # All three agents should have been invoked
    assert result.get("transaction_analysis") is not None
    assert result.get("behavioral_analysis") is not None
    assert result.get("context_enrichment") is not None
