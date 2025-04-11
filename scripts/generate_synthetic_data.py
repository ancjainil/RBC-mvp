"""CLI: Generate synthetic labelled transaction dataset.

Usage:
    python scripts/generate_synthetic_data.py [OPTIONS]
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))


@click.command()
@click.option("--customers", default=200, show_default=True, help="Number of customer profiles")
@click.option("--transactions", default=10_000, show_default=True, help="Approximate total transactions")
@click.option("--fraud-rate", default=0.08, show_default=True, help="Target fraud rate (0–1)")
@click.option("--output-dir", default="data/synthetic", show_default=True, help="Output directory")
@click.option("--seed", default=42, show_default=True, help="Random seed for reproducibility")
def main(
    customers: int,
    transactions: int,
    fraud_rate: float,
    output_dir: str,
    seed: int,
) -> None:
    """Generate a synthetic Canadian transaction dataset with fraud labels."""
    from src.data.synthetic_generator import SyntheticDataGenerator

    click.echo(
        f"Generating {transactions:,} transactions across {customers:,} customers "
        f"(fraud rate: {fraud_rate:.1%}) …"
    )

    gen = SyntheticDataGenerator(
        num_customers=customers,
        num_transactions=transactions,
        fraud_rate=fraud_rate,
        seed=seed,
    )
    txns, profiles = gen.generate()
    gen.save(output_dir=output_dir, transactions=txns, profiles=profiles)

    fraud_count = sum(1 for t in txns if t.get("fraud_label"))
    click.echo(
        f"\n✓ Generated {len(txns):,} transactions "
        f"({fraud_count:,} fraudulent, {len(txns) - fraud_count:,} legitimate)\n"
        f"  Saved to {output_dir}/"
    )


if __name__ == "__main__":
    main()
