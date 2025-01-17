"""Enumeration types used across the fraud detection system."""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    """Ordered fraud risk levels assigned by agents and the orchestrator."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    def __lt__(self, other: "RiskLevel") -> bool:
        order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        return order.index(self) < order.index(other)

    def __le__(self, other: "RiskLevel") -> bool:
        return self == other or self < other

    def __gt__(self, other: "RiskLevel") -> bool:
        return not self <= other

    def __ge__(self, other: "RiskLevel") -> bool:
        return self == other or self > other

    @classmethod
    def from_probability(
        cls,
        prob: float,
        low_max: float = 0.30,
        medium_max: float = 0.60,
        high_max: float = 0.85,
    ) -> "RiskLevel":
        """Map a fraud probability score to a risk level.

        Args:
            prob: Fraud probability in [0, 1].
            low_max: Upper bound (exclusive) for LOW risk.
            medium_max: Upper bound (exclusive) for MEDIUM risk.
            high_max: Upper bound (exclusive) for HIGH risk.

        Returns:
            Corresponding RiskLevel.
        """
        if prob < low_max:
            return cls.LOW
        if prob < medium_max:
            return cls.MEDIUM
        if prob < high_max:
            return cls.HIGH
        return cls.CRITICAL


class MerchantCategory(str, Enum):
    """Simplified merchant categories derived from ISO 18245 MCC groups."""

    GROCERIES = "groceries"
    GAS_STATION = "gas_station"
    RESTAURANT = "restaurant"
    FAST_FOOD = "fast_food"
    RETAIL = "retail"
    ONLINE_RETAIL = "online_retail"
    ELECTRONICS = "electronics"
    JEWELRY = "jewelry"
    TRAVEL = "travel"
    HOTEL = "hotel"
    ENTERTAINMENT = "entertainment"
    HEALTHCARE = "healthcare"
    PHARMACY = "pharmacy"
    UTILITY = "utility"
    EDUCATION = "education"
    GOVERNMENT = "government"
    FINANCIAL_SERVICES = "financial_services"
    MONEY_TRANSFER = "money_transfer"
    CRYPTOCURRENCY = "cryptocurrency"
    GAMBLING = "gambling"
    CASH_ADVANCE = "cash_advance"
    GIFT_CARD = "gift_card"
    OTHER = "other"

    @property
    def base_risk_score(self) -> float:
        """Intrinsic risk score for this merchant category (0–1).

        Higher scores indicate categories that are disproportionately
        associated with fraud losses per CPA 2023 data.
        """
        _scores: dict["MerchantCategory", float] = {
            MerchantCategory.GROCERIES: 0.05,
            MerchantCategory.GAS_STATION: 0.15,
            MerchantCategory.RESTAURANT: 0.05,
            MerchantCategory.FAST_FOOD: 0.05,
            MerchantCategory.RETAIL: 0.10,
            MerchantCategory.ONLINE_RETAIL: 0.25,
            MerchantCategory.ELECTRONICS: 0.45,
            MerchantCategory.JEWELRY: 0.55,
            MerchantCategory.TRAVEL: 0.20,
            MerchantCategory.HOTEL: 0.15,
            MerchantCategory.ENTERTAINMENT: 0.10,
            MerchantCategory.HEALTHCARE: 0.05,
            MerchantCategory.PHARMACY: 0.10,
            MerchantCategory.UTILITY: 0.05,
            MerchantCategory.EDUCATION: 0.05,
            MerchantCategory.GOVERNMENT: 0.02,
            MerchantCategory.FINANCIAL_SERVICES: 0.30,
            MerchantCategory.MONEY_TRANSFER: 0.70,
            MerchantCategory.CRYPTOCURRENCY: 0.75,
            MerchantCategory.GAMBLING: 0.65,
            MerchantCategory.CASH_ADVANCE: 0.60,
            MerchantCategory.GIFT_CARD: 0.55,
            MerchantCategory.OTHER: 0.20,
        }
        return _scores.get(self, 0.20)


class TransactionChannel(str, Enum):
    """Channel through which the transaction was initiated."""

    POS = "pos"               # Physical point-of-sale terminal
    ONLINE = "online"         # Card-not-present, web browser
    ATM = "atm"               # ATM cash withdrawal
    MOBILE = "mobile"         # Mobile banking app
    TELEPHONE = "telephone"   # Mail-order/telephone-order (MOTO)
    CONTACTLESS = "contactless"  # NFC/tap payment

    @property
    def card_present(self) -> bool:
        """Whether the physical card is expected to be present."""
        return self in {
            TransactionChannel.POS,
            TransactionChannel.ATM,
            TransactionChannel.CONTACTLESS,
        }


class TransactionType(str, Enum):
    """High-level transaction type classification."""

    PURCHASE = "purchase"
    CASH_WITHDRAWAL = "cash_withdrawal"
    REFUND = "refund"
    TRANSFER = "transfer"
    PRE_AUTHORIZATION = "pre_authorization"
    RECURRING = "recurring"
    REVERSAL = "reversal"


class SignalSeverity(str, Enum):
    """Severity of an individual risk signal."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendedAction(str, Enum):
    """Final recommended action from the orchestrator."""

    APPROVE = "approve"
    REVIEW = "review"
    BLOCK = "block"
    ESCALATE = "escalate"


class FraudTypology(str, Enum):
    """Known fraud typologies the system can classify."""

    CARD_NOT_PRESENT = "card_not_present"
    ACCOUNT_TAKEOVER = "account_takeover"
    SYNTHETIC_IDENTITY = "synthetic_identity"
    MERCHANT_COLLUSION = "merchant_collusion"
    GEO_VELOCITY_ANOMALY = "geo_velocity_anomaly"
    CARD_TESTING = "card_testing"
    MONEY_LAUNDERING = "money_laundering"
    FIRST_PARTY_FRAUD = "first_party_fraud"
    SOCIAL_ENGINEERING = "social_engineering"
    UNKNOWN = "unknown"
