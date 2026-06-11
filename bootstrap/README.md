# Bootstrap Assets

`bootstrap/` contains starter files that are safe to commit.

These files seed a fresh Praxis checkout:

- `db/schema.sql`: relational Praxis library schema.
- `kg/schema.sql`: SkillGraph schema.
- `kg/seed_graph.json`: starter SkillGraph nodes and edges.
- `sources/seed_sources.json`: starter source records.

Generated databases and runtime captures do not belong here. They live under
`workspace/`.
