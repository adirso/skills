# adirso-skills

A [Claude Code](https://code.claude.com) plugin marketplace for the skills I publish.

## Install

```bash
claude plugin marketplace add adirso/skills
claude plugin install <plugin-name>@adirso-skills
```

Or inside a Claude Code session:

```
/plugin marketplace add adirso/skills
/plugin install <plugin-name>@adirso-skills
```

## Plugins

| Plugin | Description |
|---|---|
| `taskforge` | Work with Task-Forge tasks, projects, phases, and sprints via its REST API |
| `motion-creator` | Studio-grade motion graphics in code with Hebrew RTL text, exported to MP4/GIF |

## Adding a skill

1. Create `plugins/<name>/.claude-plugin/plugin.json` with `{"name": "<name>", "description": "...", "version": "0.1.0"}`.
2. Put the skill at `plugins/<name>/skills/<skill-name>/SKILL.md`.
3. Add an entry to `.claude-plugin/marketplace.json`:
   `{"name": "<name>", "source": "./plugins/<name>", "description": "..."}`
   (the entry `name` must match the `name` in `plugin.json`).
4. Run `claude plugin validate .` before pushing.
