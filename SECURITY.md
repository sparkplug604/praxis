# Security Policy

Praxis handles source captures, summaries, graph memory, retrieval indexes, and generated skill references. Treat those artifacts as part of your local knowledge layer.

## Supported Versions

Praxis is pre-1.0. Security fixes target the current `main` branch until formal version support is introduced.

## Reporting A Vulnerability

Please do not post exploitable details publicly.

If GitHub private vulnerability reporting is enabled for this repository, use it. Otherwise, open a GitHub issue with a minimal description and request a private follow-up before sharing sensitive details.

## Sensitive Data Guidance

Do not commit:

- API keys or credentials;
- private customer data;
- raw sensitive transcripts;
- proprietary corpora that should not be public;
- personal connector exports;
- local machine paths that reveal private workspace structure.

Praxis is designed to preserve provenance and audit trails, but provenance is not a substitute for data classification. Review what you capture before sharing a repository or generated artifact publicly.
