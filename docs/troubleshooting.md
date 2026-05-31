# Troubleshooting

This page covers the most common first-run issues.

## `praxis` Is Not Recognized

This usually means Python installed the command into a Scripts/bin directory that is not on your PATH.

Use the module form:

```bash
python3 -m praxis --help
python3 -m praxis setup
```

Windows PowerShell:

```powershell
py -m praxis --help
py -m praxis setup
```

Important: Praxis commands are subcommands. Use:

```powershell
py -m praxis ingest "https://example.com/source"
```

Do not run `ingest` by itself.

## `No module named praxis`

Install Praxis from the checkout:

```bash
python3 -m pip install -e .
```

Windows PowerShell:

```powershell
py -m pip install -e .
```

If you do not want to install, run from the checkout with `PYTHONPATH`:

```bash
PYTHONPATH=src python3 -m praxis --help
```

PowerShell:

```powershell
$env:PYTHONPATH = "src"
py -m praxis --help
```

## `no such table: source_registry`

The local SQLite databases have not been initialized yet.

Run:

```bash
praxis bootstrap
praxis doctor --require-index
```

If you only need Reach/Agency fixture demos, run:

```bash
praxis reach init
```

## The Setup Wizard Fails Halfway Through

Re-run the same setup path. Fixture setup uses `--overwrite` for demo clients, so it is safe to repeat:

```bash
praxis setup --non-interactive --path reach-demo
```

If a generated artifact looks stale, inspect it before deleting anything:

```bash
praxis reach evidence list --client demo
praxis agency client show demo
praxis reach stale list --client demo --all
```

## Live Connector Credentials Are Missing

Reach fixture demos do not need credentials. Live connectors do.

HubSpot:

```bash
praxis reach connectors test hubspot --client acme
```

Google Ads:

```bash
praxis reach connectors test google_ads --client acme
```

Google Analytics:

```bash
praxis reach connectors test google_analytics --client acme
```

The connector test output tells you which environment variable is missing.

## Search Returns Nothing

Check that sources were chunked and embedded:

```bash
praxis doctor --require-index
praxis chunk --changed-only
praxis embed --provider local-hash
praxis search "your query" --explain
```

`local-hash` embeddings are offline and credential-free. They are good for setup and demos. For production-quality semantic ranking, configure a real embedding provider later.

## Windows Path And Quoting Tips

Use quotes around URLs:

```powershell
py -m praxis ingest "https://example.com/source"
```

Run commands from the Praxis checkout unless you pass `--root`:

```powershell
py -m praxis --root "C:\Users\you\praxis" doctor --require-index
```

If PowerShell wraps long URLs across lines, keep the URL in one quoted string.
