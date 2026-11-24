#!/usr/bin/env bash
# Build the Claude Code plugin for the adirso/skills marketplace from this repository.
#   scripts/publish-skill.sh /path/to/skills-repo
# Writes plugins/wedding-album-curator/ (skill + bundled app = tracked files only).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
dest_repo="${1:?usage: publish-skill.sh /path/to/skills-repo}"
plugin="$dest_repo/plugins/wedding-album-curator"
skill="$plugin/skills/wedding-album-curator"
version="$(sed -n 's/^version = "\(.*\)"/\1/p' "$root/backend/pyproject.toml" | head -1)"
rm -rf "$skill"
mkdir -p "$skill/app" "$plugin/.claude-plugin"
# the skill itself
(cd "$root/skills/wedding-album-curator" && git ls-files -z | xargs -0 -I{} rsync -R "{}" "$skill/")
# the app: every tracked file except the skill folder
(cd "$root" && git ls-files -z -- . ':!skills/' | xargs -0 -I{} rsync -R "{}" "$skill/app/")
echo "$version" > "$skill/VERSION"
cat > "$plugin/.claude-plugin/plugin.json" <<JSON
{
  "name": "wedding-album-curator",
  "description": "Local-first app that helps couples pick ~500 album photos from thousands of wedding photos: face grouping, quality checks, similar shots, explainable album selection, export. Photos never leave the computer by default.",
  "version": "$version",
  "author": {
    "name": "Adir Solomon",
    "email": "goodadir@gmail.com"
  },
  "repository": "https://github.com/adirso/skills",
  "keywords": ["wedding", "photos", "album", "face-grouping", "local-ai", "hebrew", "rtl"]
}
JSON
echo "Plugin written to $plugin (version $version)"
