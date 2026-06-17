# Stack Overflow Developer Survey AI Tooling Mini Dataset

This bundled Praxis Core demo source is a small aggregate excerpt derived from the official Stack Overflow Developer Survey archives for 2024 and 2025.

It is designed for a first-run Praxis demo: no credentials, no large download, no respondent-level records. The raw survey files stay outside the repo; only aggregate counts, percentages, schema field notes, and source provenance are bundled.

## What Praxis Can Retrieve

- AI adoption by year from `AISelect`.
- Developer favorability toward AI tools from `AISent`.
- Trust in AI output accuracy from `AIAcc`.
- Perceived ability to handle complex tasks from `AIComplex`.
- Job-threat perception from `AIThreat`.
- Developer-segment rollups by `DevType`.
- Top shared tooling items from language, database, platform, and web framework columns.

## Example Aggregate Findings

- In the 2024 survey excerpt, 37,662 of 65,437 respondents answered that they used AI tools in their development process.
- In the 2025 survey excerpt, 26,469 of 49,191 respondents reported daily, weekly, monthly, or infrequent AI tool use.
- The segment file lets Praxis compare AI use, favorability, trust, complex-task handling, and job-threat perception across common developer types.
- The tooling file lets Praxis retrieve common language, database, platform, and web framework signals alongside AI attitudes.

## Files

- `ai_attitudes_by_year.csv`: response counts and percentages for shared AI attitude fields.
- `ai_developer_segments.csv`: aggregate AI metrics by developer segment.
- `developer_tooling_top_items.csv`: top tooling items from shared HaveWorkedWith columns.
- `shared_schema_fields.csv`: selected shared schema fields and result-column mappings.
- `source_manifest.json`: source URLs, access dates, licenses, and checksums.

## License And Attribution

This aggregate excerpt is derived from Stack Overflow Developer Survey data. The source survey database is distributed by Stack Overflow under ODbL 1.0, with database contents under DbCL 1.0. Preserve attribution and source-license terms if redistributing or modifying this derived dataset.
