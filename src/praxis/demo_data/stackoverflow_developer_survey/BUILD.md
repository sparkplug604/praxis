# Build Notes

This demo dataset is an aggregate-only excerpt derived from the official Stack Overflow Developer Survey archives.

## Source Inputs

- 2024 schema: `https://media.githubusercontent.com/media/StackExchange/Survey/main/packages/archive/2024/schema.csv`
- 2024 results: `https://media.githubusercontent.com/media/StackExchange/Survey/main/packages/archive/2024/results.csv`
- 2025 schema: `https://media.githubusercontent.com/media/StackExchange/Survey/main/packages/archive/2025/schema.csv`
- 2025 results: `https://media.githubusercontent.com/media/StackExchange/Survey/main/packages/archive/2025/results.csv`

The raw source files are not committed to this repository. Their downloaded byte counts and SHA-256 checksums are recorded in `source_manifest.json`.

## Aggregation

The bundled CSVs are generated from shared 2024/2025 AI and tooling fields:

- `AISelect`
- `AISent`
- `AIAcc`
- `AIComplex`
- `AIThreat`
- `DevType`
- `LanguageHaveWorkedWith`
- `DatabaseHaveWorkedWith`
- `PlatformHaveWorkedWith`
- `WebframeHaveWorkedWith`

Generated files include:

- `ai_attitudes_by_year.csv`: response counts and percentages for shared AI attitude fields.
- `ai_developer_segments.csv`: developer-segment rollups for adoption, favorability, trust, complex-task handling, and job-threat perception.
- `developer_tooling_top_items.csv`: top shared tooling items by year.
- `shared_schema_fields.csv`: selected schema fields and 2024/2025 result-column mappings.

## Privacy Boundary

Only aggregate rows are bundled. Raw respondent-level rows, free-text answers, and survey PDFs are excluded from the repository.

## License

The source survey database is distributed by Stack Overflow under ODbL 1.0, with database contents under DbCL 1.0. Preserve attribution and license terms if redistributing or modifying this derived dataset.
