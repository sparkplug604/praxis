# Contributing to Praxis

Praxis is an early-stage, local-first framework for turning source material into searchable agent knowledge and reusable agent skills.

Contributions are welcome, especially when they make Praxis easier to run, inspect, test, extend, or explain.

## Good First Contributions

Useful first issues usually fit one of these shapes:

- improve CLI help text or error messages;
- add tests around an existing command;
- improve docs for a common workflow;
- add a small retrieval eval fixture;
- add adapter notes for an agent runtime or framework;
- harden source capture, graph changes, rollback, or export behavior.

## Local Setup

Install Praxis in editable mode:

```bash
python3 -m pip install -e .
```

Run the health checks and tests:

```bash
praxis bootstrap
praxis doctor --require-index
praxis eval
python3 -m unittest discover -s tests
```

If you do not want to install the package, run commands from the checkout:

```bash
PYTHONPATH=src python3 -m praxis --help
```

## Pull Request Guidelines

- Keep changes focused and easy to review.
- Add or update tests when changing behavior.
- Prefer small, inspectable scripts and CLI commands over hidden automation.
- Preserve source traceability, audit logs, and rollback behavior.
- Avoid committing private corpora, credentials, local absolute paths, API keys, generated secrets, or personal connector data.
- Update docs when a user-facing command or workflow changes.

## Design Priorities

Praxis should stay:

- local-first;
- source-traceable;
- reversible;
- agent-runtime agnostic;
- useful without hosted infrastructure;
- easy to inspect from plain files and SQLite databases.

When in doubt, optimize for boring, explicit, testable mechanisms over clever hidden behavior.
