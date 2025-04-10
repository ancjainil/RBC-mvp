"""CLI: Ingest the knowledge base into the vector store.

Usage:
    python scripts/ingest_knowledge_base.py [--reset] [--kb-dir PATH]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

# Ensure the project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))


@click.command()
@click.option("--kb-dir", default="knowledge_base", show_default=True, help="Knowledge base directory")
@click.option("--reset", is_flag=True, default=False, help="Drop and recreate the collection before ingesting")
@click.option("--persist-dir", default=None, help="Override ChromaDB persist directory")
def main(kb_dir: str, reset: bool, persist_dir: str | None) -> None:
    """Ingest all documents in KB_DIR into the vector store."""
    import structlog

    from src.rag.ingestion import KnowledgeBaseIngestionPipeline
    from src.rag.vector_store import FraudVectorStore

    log = structlog.get_logger("ingest_kb")

    store_kwargs = {}
    if persist_dir:
        store_kwargs["persist_dir"] = persist_dir

    store = FraudVectorStore(**store_kwargs)
    pipeline = KnowledgeBaseIngestionPipeline(
        vector_store=store, knowledge_base_dir=kb_dir
    )

    log.info("ingestion.starting", kb_dir=kb_dir, reset=reset)
    summary = pipeline.ingest_all(reset=reset)

    click.echo(json.dumps(summary, indent=2))

    if summary["errors"]:
        click.echo(f"\n[WARNING] {len(summary['errors'])} file(s) failed to ingest.", err=True)
        sys.exit(1)

    click.echo(
        f"\n✓ Ingested {summary['files_processed']} files → "
        f"{summary['chunks_added']} chunks into '{store._collection_name}'"
    )


if __name__ == "__main__":
    main()
