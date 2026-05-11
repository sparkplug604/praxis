# Claude Code Adapter

The Claude Code adapter should export Praxis skills using the common Agent Skills `SKILL.md` structure.

## Target Shape

- Export runtime-neutral Praxis skills into Claude-compatible skill folders.
- Preserve progressive disclosure: small metadata first, detailed references/scripts on demand.
- Use Praxis evidence paths and source IDs in the skill body.
- Keep installation reversible.

## Notes

Claude Skills, Codex Skills, Cursor skills, and OpenCode skills are converging around the same basic directory pattern. Praxis should generate a canonical skill package first, then apply small runtime-specific changes.

