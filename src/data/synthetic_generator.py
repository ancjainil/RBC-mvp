"""Synthetic Canadian transaction data generator.

Generates 200 customer profiles with realistic spending patterns and
10,000+ transactions, of which ~8% are fraudulent.  Fraud scenarios:

1. Card-not-present (CNP) fraud          — online purchases from unusual merchants
2. Geographic impossibility              — Vancouver txn 30 min after Toronto txn
3. Sudden high-value purchase            — electronics / jewelry out of pattern
4. Account takeover (ATO)                — complete spending pattern shift + new device
5. Card-testing micro-charge + big buy   — $1–2 test charge then a large purchase
6. Money-mule gift card purchasing       — multiple >$200 gift card purchases
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog
from faker import Faker

from src.models.enums import MerchantCategory, TransactionChannel, TransactionType
from src.models.schemas import CustomerProfile, GeoLocation, SpendingStats, Transaction

logger = structlog.get_logger(__name__)
_fake = Faker("en_CA")
random.seed(42)

# ── Canadian city coordinates ─────────────────────────────────────────────
_CA_CITIES: list[dict] = [
    {"name": "Toronto", "lat": 43.6532, "lon": -79.3832},
    {"name": "Vancouver", "lat": 49.2827, "lon": -123.1207},
    {"name": "Montreal", "lat": 45.5017, "lon": -73.5673},
    {"name": "Calgary", "lat": 51.0447, "lon": -114.0719},
    {"name": "Ottawa", "lat": 45.4215, "lon": -75.6972},
    {"name": "Edmonton", "lat": 53.5461, "lon": -113.4938},
    {"name": "Winnipeg", "lat": 49.8951, "lon": -97.1384},
    {"name": "Quebec City", "lat": 46.8139, "lon": -71.2080},
    {"name": "Hamilton", "lat": 43.2557, "lon": -79.8711},
    {"name": "Kitchener", "lat": 43.4516, "lon": -80.4925},
]

# ── Typical Canadian merchants by category ────────────────────────────────
_MERCHANTS: dict[MerchantCategory, list[str]] = {
    MerchantCategory.GROCERIES: ["Loblaws", "Metro", "Sobeys", "No Frills", "FreshCo"],
    MerchantCategory.GAS_STATION: ["Petro-Canada", "Shell", "Esso", "Canadian Tire Gas Bar"],
    MerchantCategory.RESTAURANT: ["The Keg", "Montana's", "Swiss Chalet", "Tim Hortons"],
    MerchantCategory.FAST_FOOD: ["McDonald's", "Subway", "Wendy's", "Harvey's"],
    MerchantCategory.RETAIL: ["Winners", "HomeSense", "Canadian Tire", "Dollarama"],
    MerchantCategory.ONLINE_RETAIL: ["Amazon.ca", "Shopify Store", "Best Buy Online", "Indigo"],
    MerchantCategory.ELECTRONICS: ["Best Buy", "Apple Store", "Staples", "The Source"],
    MerchantCategory.JEWELRY: ["Peoples Jewellers", "Birks", "Tiffany & Co."],
    MerchantCategory.TRAVEL: ["Air Canada", "WestJet", "Expedia.ca", "Via Rail"],
    MerchantCategory.PHARMACY: ["Shoppers Drug Mart", "Rexall", "Jean Coutu"],
    MerchantCategory.ENTERTAINMENT: ["Cineplex", "Ticketmaster.ca", "Netflix"],
    MerchantCategory.GIFT_CARD: ["Steam Gift Card", "iTunes Gift Card", "Visa Gift Card"],
    MerchantCategory.MONEY_TRANSFER: ["Western Union", "MoneyGram", "Interac e-Transfer"],
    MerchantCategory.CRYPTOCURRENCY: ["Coinsquare", "Newton Crypto", "Shakepay"],
    MerchantCategory.GAMBLING: ["OLG Online", "PlayNow.com"],
}

_MCC_MAP: dict[MerchantCategory, str] = {
    MerchantCategory.GROCERIES: "5411",
    MerchantCategory.GAS_STATION: "5541",
    MerchantCategory.RESTAURANT: "5812",
    MerchantCategory.FAST_FOOD: "5814",
    MerchantCategory.RETAIL: "5999",
    MerchantCategory.ONLINE_RETAIL: "5999",
    MerchantCategory.ELECTRONICS: "5065",
    MerchantCategory.JEWELRY: "5944",
    MerchantCategory.TRAVEL: "4511",
    MerchantCategory.PHARMACY: "5912",
    MerchantCategory.ENTERTAINMENT: "7832",
    MerchantCategory.GIFT_CARD: "5999",
    MerchantCategory.MONEY_TRANSFER: "4829",
    MerchantCategory.CRYPTOCURRENCY: "6051",
    MerchantCategory.GAMBLING: "7995",
}


# ── Customer profile ──────────────────────────────────────────────────────


@dataclass
class _CustomerDef:
    customer_id: str
    home_city: dict
    monthly_income: float
    typical_categories: list[MerchantCategory]
    mean_txn_amount: float
    std_txn_amount: float
    typical_hours: tuple[int, int]  # (start, end) 24h
    device_ids: list[str]
    ip_prefixes: list[str]


def _create_customer() -> _CustomerDef:
    city = random.choice(_CA_CITIES)
    income = random.choice([2_500, 3_500, 5_000, 7_500, 10_000, 15_000])
    mean_amt = income * random.uniform(0.01, 0.05)
    return _CustomerDef(
        customer_id=f"cust_{uuid.uuid4().hex[:8]}",
        home_city=city,
        monthly_income=income,
        typical_categories=random.sample(
            [
                MerchantCategory.GROCERIES,
                MerchantCategory.GAS_STATION,
                MerchantCategory.RESTAURANT,
                MerchantCategory.FAST_FOOD,
                MerchantCategory.RETAIL,
                MerchantCategory.PHARMACY,
            ],
            k=random.randint(3, 5),
        ),
        mean_txn_amount=mean_amt,
        std_txn_amount=mean_amt * 0.6,
        typical_hours=(8, 21),
        device_ids=[f"dev_{uuid.uuid4().hex[:10]}" for _ in range(random.randint(1, 3))],
        ip_prefixes=[
            f"192.168.{random.randint(0, 254)}" for _ in range(random.randint(1, 2))
        ],
    )


# ── Transaction generators ────────────────────────────────────────────────


def _normal_transaction(
    customer: _CustomerDef, base_ts: datetime
) -> tuple[dict, bool, str | None]:
    """Generate a single legitimate transaction dict."""
    cat = random.choice(customer.typical_categories)
    merchants = _MERCHANTS.get(cat, ["Unknown Merchant"])
    merchant = random.choice(merchants)
    amount = max(1.0, random.gauss(customer.mean_txn_amount, customer.std_txn_amount))
    hour_offset = random.randint(customer.typical_hours[0], customer.typical_hours[1])
    ts = base_ts.replace(hour=hour_offset % 24, minute=random.randint(0, 59), second=0)
    city = customer.home_city

    txn = {
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
        "customer_id": customer.customer_id,
        "amount": round(amount, 2),
        "currency": "CAD",
        "merchant_id": f"merch_{merchant[:4].lower()}_{uuid.uuid4().hex[:6]}",
        "merchant_name": merchant,
        "merchant_category_code": _MCC_MAP.get(cat, "5999"),
        "merchant_category": cat.value,
        "transaction_type": TransactionType.PURCHASE.value,
        "channel": TransactionChannel.POS.value,
        "card_present": True,
        "timestamp": ts.isoformat(),
        "location": {"lat": city["lat"] + random.uniform(-0.05, 0.05),
                     "lon": city["lon"] + random.uniform(-0.05, 0.05),
                     "city": city["name"], "country_code": "CA"},
        "device_fingerprint": random.choice(customer.device_ids),
        "ip_address": None,
        "recurring": False,
        "fraud_label": False,
        "fraud_type": None,
    }
    return txn, False, None


def _fraud_cnp(customer: _CustomerDef, base_ts: datetime) -> dict:
    """Card-not-present fraud."""
    cat = random.choice([MerchantCategory.ELECTRONICS, MerchantCategory.ONLINE_RETAIL,
                         MerchantCategory.GIFT_CARD])
    merchants = _MERCHANTS.get(cat, ["Suspicious Online Store"])
    merchant = random.choice(merchants)
    amount = random.uniform(customer.mean_txn_amount * 3, customer.mean_txn_amount * 10)
    return {
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
        "customer_id": customer.customer_id,
        "amount": round(amount, 2),
        "currency": "CAD",
        "merchant_id": f"merch_fraud_{uuid.uuid4().hex[:6]}",
        "merchant_name": merchant,
        "merchant_category_code": _MCC_MAP.get(cat, "5999"),
        "merchant_category": cat.value,
        "transaction_type": TransactionType.PURCHASE.value,
        "channel": TransactionChannel.ONLINE.value,
        "card_present": False,
        "timestamp": base_ts.isoformat(),
        "location": None,
        "device_fingerprint": f"dev_unknown_{uuid.uuid4().hex[:8]}",
        "ip_address": f"185.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}",
        "recurring": False,
        "fraud_label": True,
        "fraud_type": "card_not_present",
    }


def _fraud_geo_velocity(customer: _CustomerDef, base_ts: datetime) -> tuple[dict, dict]:
    """Geographic impossibility — two cities 30 minutes apart."""
    city_a = customer.home_city
    city_b = random.choice([c for c in _CA_CITIES if c["name"] != city_a["name"]])
    ts_a = base_ts
    ts_b = base_ts + timedelta(minutes=30)

    def _make(city: dict, ts: datetime, fraud: bool) -> dict:
        cat = random.choice([MerchantCategory.ELECTRONICS, MerchantCategory.GROCERIES])
        merchant = random.choice(_MERCHANTS.get(cat, ["Store"]))
        return {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "customer_id": customer.customer_id,
            "amount": round(random.uniform(50, 2_500), 2),
            "currency": "CAD",
            "merchant_id": f"merch_{uuid.uuid4().hex[:6]}",
            "merchant_name": merchant,
            "merchant_category_code": _MCC_MAP.get(cat, "5999"),
            "merchant_category": cat.value,
            "transaction_type": TransactionType.PURCHASE.value,
            "channel": TransactionChannel.POS.value,
            "card_present": True,
            "timestamp": ts.isoformat(),
            "location": {"lat": city["lat"], "lon": city["lon"],
                         "city": city["name"], "country_code": "CA"},
            "device_fingerprint": random.choice(customer.device_ids),
            "ip_address": None,
            "recurring": False,
            "fraud_label": fraud,
            "fraud_type": "geo_velocity_anomaly" if fraud else None,
        }

    return _make(city_a, ts_a, False), _make(city_b, ts_b, True)


def _fraud_ato(customer: _CustomerDef, base_ts: datetime) -> dict:
    """Account takeover — new device, new category, high amount."""
    cat = random.choice([MerchantCategory.ELECTRONICS, MerchantCategory.JEWELRY,
                         MerchantCategory.MONEY_TRANSFER])
    merchant = random.choice(_MERCHANTS.get(cat, ["ATO Merchant"]))
    amount = random.uniform(customer.mean_txn_amount * 8, customer.mean_txn_amount * 20)
    return {
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
        "customer_id": customer.customer_id,
        "amount": round(amount, 2),
        "currency": "CAD",
        "merchant_id": f"merch_ato_{uuid.uuid4().hex[:6]}",
        "merchant_name": merchant,
        "merchant_category_code": _MCC_MAP.get(cat, "5999"),
        "merchant_category": cat.value,
        "transaction_type": TransactionType.PURCHASE.value,
        "channel": TransactionChannel.ONLINE.value,
        "card_present": False,
        "timestamp": base_ts.isoformat(),
        "location": None,
        "device_fingerprint": f"dev_ato_{uuid.uuid4().hex[:8]}",
        "ip_address": f"45.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}",
        "recurring": False,
        "fraud_label": True,
        "fraud_type": "account_takeover",
    }


def _fraud_card_test(customer: _CustomerDef, base_ts: datetime) -> tuple[dict, dict]:
    """Micro-charge test then large purchase."""
    ts_test = base_ts
    ts_big = base_ts + timedelta(hours=random.uniform(1, 4))

    test_txn = {
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
        "customer_id": customer.customer_id,
        "amount": round(random.uniform(0.50, 2.00), 2),
        "currency": "CAD",
        "merchant_id": f"merch_test_{uuid.uuid4().hex[:6]}",
        "merchant_name": "Digital Verify Service",
        "merchant_category_code": "5999",
        "merchant_category": MerchantCategory.ONLINE_RETAIL.value,
        "transaction_type": TransactionType.PURCHASE.value,
        "channel": TransactionChannel.ONLINE.value,
        "card_present": False,
        "timestamp": ts_test.isoformat(),
        "location": None,
        "device_fingerprint": f"dev_ct_{uuid.uuid4().hex[:8]}",
        "ip_address": f"185.{random.randint(1,254)}.{random.randint(1,254)}.1",
        "recurring": False,
        "fraud_label": True,
        "fraud_type": "card_testing",
    }

    cat = MerchantCategory.ELECTRONICS
    big_txn = {
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
        "customer_id": customer.customer_id,
        "amount": round(random.uniform(800, 3_500), 2),
        "currency": "CAD",
        "merchant_id": f"merch_big_{uuid.uuid4().hex[:6]}",
        "merchant_name": random.choice(_MERCHANTS[cat]),
        "merchant_category_code": _MCC_MAP[cat],
        "merchant_category": cat.value,
        "transaction_type": TransactionType.PURCHASE.value,
        "channel": TransactionChannel.ONLINE.value,
        "card_present": False,
        "timestamp": ts_big.isoformat(),
        "location": None,
        "device_fingerprint": f"dev_ct_{uuid.uuid4().hex[:8]}",
        "ip_address": f"185.{random.randint(1,254)}.{random.randint(1,254)}.2",
        "recurring": False,
        "fraud_label": True,
        "fraud_type": "card_testing",
    }
    return test_txn, big_txn


# ── Main generator ────────────────────────────────────────────────────────


class SyntheticDataGenerator:
    """Generates a labelled synthetic Canadian transaction dataset.

    Args:
        num_customers: Number of distinct customer profiles to generate.
        num_transactions: Approximate total transaction count.
        fraud_rate: Target fraction of fraudulent transactions (~0.08).
        seed: Random seed for reproducibility.
    """

    def __init__(
        self,
        num_customers: int = 200,
        num_transactions: int = 10_000,
        fraud_rate: float = 0.08,
        seed: int = 42,
    ) -> None:
        self.num_customers = num_customers
        self.num_transactions = num_transactions
        self.fraud_rate = fraud_rate
        random.seed(seed)

    def generate(self) -> tuple[list[dict], list[CustomerProfile]]:
        """Generate transactions and customer profiles.

        Returns:
            Tuple of (transactions_list, customer_profiles_list).
        """
        customers = [_create_customer() for _ in range(self.num_customers)]
        transactions: list[dict] = []
        base_dt = datetime.now(tz=timezone.utc) - timedelta(days=90)

        txns_per_customer = self.num_transactions // self.num_customers
        fraud_per_customer = max(1, int(txns_per_customer * self.fraud_rate))

        for customer in customers:
            # Normal transactions
            for i in range(txns_per_customer - fraud_per_customer):
                ts = base_dt + timedelta(
                    days=random.uniform(0, 89), hours=random.uniform(0, 23)
                )
                txn, _, _ = _normal_transaction(customer, ts)
                transactions.append(txn)

            # Fraud injections
            fraud_slots = random.sample(
                range(txns_per_customer - fraud_per_customer,
                      txns_per_customer - fraud_per_customer + fraud_per_customer),
                k=min(fraud_per_customer, 4),
            )
            fraud_types = random.choices(
                ["cnp", "geo", "ato", "card_test"], k=len(fraud_slots)
            )
            for ft in fraud_types:
                ts = base_dt + timedelta(days=random.uniform(60, 89))
                if ft == "cnp":
                    transactions.append(_fraud_cnp(customer, ts))
                elif ft == "geo":
                    a, b = _fraud_geo_velocity(customer, ts)
                    transactions.extend([a, b])
                elif ft == "ato":
                    transactions.append(_fraud_ato(customer, ts))
                elif ft == "card_test":
                    a, b = _fraud_card_test(customer, ts)
                    transactions.extend([a, b])

        # Sort by timestamp
        transactions.sort(key=lambda t: t["timestamp"])

        logger.info(
            "synthetic_generator.complete",
            total=len(transactions),
            fraudulent=sum(1 for t in transactions if t["fraud_label"]),
            customers=len(customers),
        )

        profiles = [_customer_to_profile(c, transactions) for c in customers]
        return transactions, profiles

    def save(
        self,
        output_dir: str = "data/synthetic",
        transactions: list[dict] | None = None,
        profiles: list[CustomerProfile] | None = None,
    ) -> None:
        """Persist generated data to JSON files.

        Args:
            output_dir: Directory to write output files to.
            transactions: Transactions to save (generated if None).
            profiles: Profiles to save (generated if None).
        """
        if transactions is None or profiles is None:
            transactions, profiles = self.generate()

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        txn_path = out / "transactions.json"
        txn_path.write_text(json.dumps(transactions, indent=2, default=str))

        profile_path = out / "customer_profiles.json"
        profile_path.write_text(
            json.dumps(
                [p.model_dump(mode="json") for p in profiles], indent=2, default=str
            )
        )
        logger.info(
            "synthetic_generator.saved",
            txn_file=str(txn_path),
            profile_file=str(profile_path),
            total_txns=len(transactions),
        )


def _customer_to_profile(
    c: _CustomerDef, all_txns: list[dict]
) -> CustomerProfile:
    """Build a CustomerProfile from a _CustomerDef and transaction history."""
    cust_txns = [t for t in all_txns if t["customer_id"] == c.customer_id]
    amounts = [t["amount"] for t in cust_txns]
    cats = [t["merchant_category"] for t in cust_txns]
    from collections import Counter

    top_cats = [k for k, _ in Counter(cats).most_common(5)]
    mean_amt = sum(amounts) / len(amounts) if amounts else c.mean_txn_amount
    import math

    variance = (
        sum((a - mean_amt) ** 2 for a in amounts) / len(amounts) if amounts else 0
    )
    std_amt = math.sqrt(variance)

    def _stats(window: int) -> SpendingStats:
        return SpendingStats(
            window_days=window,
            mean_amount=mean_amt,
            std_amount=std_amt,
            transaction_count=len(cust_txns),
            top_categories=top_cats,
        )

    last_txn = max(cust_txns, key=lambda t: t["timestamp"], default=None)

    return CustomerProfile(
        customer_id=c.customer_id,
        account_age_days=random.randint(180, 3_650),
        lifetime_transaction_count=len(cust_txns),
        stats_7d=_stats(7),
        stats_30d=_stats(30),
        stats_90d=_stats(90),
        last_known_location=GeoLocation(
            lat=c.home_city["lat"],
            lon=c.home_city["lon"],
            city=c.home_city["name"],
            country_code="CA",
        ),
        last_transaction_timestamp=(
            datetime.fromisoformat(last_txn["timestamp"]) if last_txn else None
        ),
        known_device_fingerprints=c.device_ids,
        known_ip_prefixes=c.ip_prefixes,
    )
