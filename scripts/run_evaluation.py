"""CLI: Run benchmark evaluation and write a JSON report.

Usage:
    python scripts/run_evaluation.py [--output PATH] [--samples N]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))


@click.command()
@click.option("--test-file", default="data/synthetic/transactions.json",
              show_default=True, help="Labelled transactions JSON file")
@click.option("--profile-file", default="data/synthetic/customer_profiles.json",
              show_default=True, help="Customer profiles JSON file")
@click.option("--output", default="reports/evaluation.json",
              show_default=True, help="Output path for evaluation report")
@click.option("--samples", default=None, type=int,
              help="Limit to N samples for a quick run")
@click.option("--concurrency", default=5, show_default=True,
              help="Concurrent graph invocations")
def main(
    test_file: str,
    profile_file: str,
    output: str,
    samples: int | None,
    concurrency: int,
) -> None:
    """Run the fraud detection benchmark and write a JSON report."""
    from src.api.dependencies import get_compiled_graph
    from src.evaluation.benchmark import BenchmarkRunner

    click.echo("Initialising graph …")
    graph = get_compiled_graph()

    runner = BenchmarkRunner(
        graph=graph,
        max_samples=samples,
        concurrency=concurrency,
    )

    click.echo(f"Running evaluation on {test_file} …")
    report = asyncio.run(
        runner.run(test_file=test_file, profile_file=profile_file)
    )

    report_dict = report.to_dict()

    # Print summary
    s = report_dict["summary"]
    click.echo(
        f"\n{'─'*50}\n"
        f"  Precision:  {s['precision']:.4f}\n"
        f"  Recall:     {s['recall']:.4f}\n"
        f"  F1 Score:   {s['f1']:.4f}\n"
        f"  AUC-ROC:    {s['auc_roc']:.4f}\n"
        f"  FP Rate:    {s['false_positive_rate']:.4f}\n"
        f"  Accuracy:   {s['accuracy']:.4f}\n"
        f"{'─'*50}\n"
        f"  Latency P50: {report_dict['latency_ms']['median']:.0f} ms\n"
        f"  Latency P95: {report_dict['latency_ms']['p95']:.0f} ms\n"
        f"  Latency P99: {report_dict['latency_ms']['p99']:.0f} ms\n"
        f"{'─'*50}"
    )

    # Write report
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_dict, indent=2))
    click.echo(f"\n✓ Report written to {output}")


if __name__ == "__main__":
    main()
