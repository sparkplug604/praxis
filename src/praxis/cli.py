"""Command line interface for Praxis."""

from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

from . import __version__
from .paths import commands_dir, default_root


COMMANDS = {
    "bootstrap": ("__bootstrap__", "Initialize DBs, graph, chunks, and local embeddings for a fresh checkout."),
    "doctor": ("skill_doctor.py", "Healthcheck a Praxis checkout."),
    "init-db": ("init_agentic_db.py", "Initialize the relational Praxis database."),
    "init-graph": ("init_skill_graph.py", "Initialize the Praxis SkillGraph database."),
    "capture": ("research_source.py", "Capture a URL, file, or directory."),
    "propose": ("propose_graph_update.py", "Create a reviewed-before-apply graph proposal."),
    "apply": ("apply_graph_update.py", "Apply a reviewed graph proposal."),
    "scan": ("scan_watchlist.py", "Scan a configured research watchlist."),
    "capture-hit": ("capture_research_hit.py", "Promote a watchlist hit into a source capture."),
    "chunk": ("chunk_sources.py", "Chunk local Praxis sources into the semantic index."),
    "embed": ("index_vectors.py", "Embed pending semantic chunks."),
    "search": ("hybrid_search.py", "Run hybrid semantic/keyword/graph search."),
    "semantic-search": ("semantic_search.py", "Run semantic search only."),
    "graph": ("search_skill_graph.py", "Search or traverse the SkillGraph."),
    "library": ("search_praxis_library.py", "Search the relational Praxis library."),
    "eval": ("eval_retrieval.py", "Run lightweight retrieval checks."),
    "check-embeddings": ("check_embedding_setup.py", "Check embedding provider setup."),
    "export-graph": ("export_skill_graph.py", "Export SkillGraph slices."),
    "export-skill-refs": ("export_skill_refs.py", "Export database records to skill references."),
    "add-note": ("add_memory_note.py", "Add a durable non-secret local note."),
    "add-source-stub": ("add_source_stub.py", "Create a source analysis Markdown stub."),
    "refresh": ("refresh_stale_sources.py", "List sources due for refresh."),
}


def run_script(script_name: str, args: list[str], root: Path) -> int:
    script = commands_dir() / script_name
    if not script.exists():
        raise SystemExit(
            "\n".join(
                [
                    f"Praxis script not found: {script}",
                    "The installed Praxis package is missing its command implementations.",
                    "Try reinstalling Praxis, or run from a complete checkout with PYTHONPATH=src.",
                ]
            )
        )
    old_argv = sys.argv[:]
    old_path = sys.path[:]
    old_root = os.environ.get("PRAXIS_ROOT")
    try:
        os.environ["PRAXIS_ROOT"] = str(root)
        sys.path.insert(0, str(script.parent))
        sys.argv = [str(script), *args]
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    finally:
        sys.argv = old_argv
        sys.path = old_path
        if old_root is None:
            os.environ.pop("PRAXIS_ROOT", None)
        else:
            os.environ["PRAXIS_ROOT"] = old_root
    return 0


def bootstrap(root: Path) -> int:
    steps = [
        ("init-db", ["init_agentic_db.py", []]),
        ("init-graph", ["init_skill_graph.py", []]),
        ("chunk", ["chunk_sources.py", ["--reset", "--no-runtimes"]]),
        ("embed", ["index_vectors.py", ["--provider", "local-hash", "--force"]]),
        ("doctor", ["skill_doctor.py", ["--require-index"]]),
    ]
    for label, (script_name, args) in steps:
        print(f"== praxis {label} ==")
        code = run_script(script_name, args, root)
        if code:
            return code
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="praxis",
        description="Praxis knowledge-to-skill CLI.",
        epilog="Use `praxis <command> --help` for command-specific options.",
    )
    parser.add_argument("--root", default=str(default_root()), help="Praxis checkout/workspace root.")
    parser.add_argument("--version", action="store_true", help="Print Praxis version and exit.")
    parser.add_argument("command", nargs="?", choices=sorted(COMMANDS), help="Command to run.")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the command.")
    parsed = parser.parse_args(argv)

    if parsed.version:
        print(__version__)
        return 0
    if not parsed.command:
        parser.print_help()
        return 0

    if parsed.command == "bootstrap":
        return bootstrap(Path(parsed.root).expanduser().resolve())

    script_name, _ = COMMANDS[parsed.command]
    return run_script(script_name, parsed.args, Path(parsed.root).expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
