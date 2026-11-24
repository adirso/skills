"""Claude through the user's own Claude Code installation (headless `claude -p`).

Supported mechanism: Claude Code's documented non-interactive ("print") mode. Each photo
is passed as a base64 image in a stream-json user message; all tools are disabled, MCP
servers are not loaded, the session is not persisted, and the answer is constrained by a
JSON schema. We never read or reuse Claude Code's stored credentials: the `claude`
binary authenticates itself exactly as when the user runs it.

Limitations (stated in the UI as well):
- Usage counts against the user's Claude Code plan limits or their configured API
  billing. This app cannot see remaining allowance, and any cost figure reported by the
  CLI is informational for subscription plans.
- One CLI process per photo is slow (several seconds of start-up each) and is intended
  for small sets, e.g. re-checking the shortlisted album photos.
- This mode depends on CLI flags that may change between Claude Code versions; use
  "Test connection" after updates.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from .base import (ANALYSIS_SCHEMA, PROMPT, ImageAnalysis, ImageInput, ProviderCapabilities, ProviderError,
                   VisionProvider, normalize)

CLI = os.environ.get("WAC_CLAUDE_CLI", "claude")
TIMEOUT_S = 180


def cli_path() -> Optional[str]:
    return shutil.which(CLI)


def cli_version() -> Optional[str]:
    p = cli_path()
    if not p:
        return None
    try:
        out = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build_command(model: Optional[str], max_budget_usd: Optional[float]) -> list[str]:
    cmd = [
        cli_path() or CLI, "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--tools", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--json-schema", json.dumps(ANALYSIS_SCHEMA),
    ]
    if model:
        cmd += ["--model", model]
    if max_budget_usd:
        cmd += ["--max-budget-usd", f"{max_budget_usd:.4f}"]
    return cmd


def parse_stream(stdout: str) -> dict:
    result = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            result = ev
    if result is None:
        raise ProviderError("Claude Code returned no result.")
    if result.get("is_error") or result.get("subtype") not in (None, "success"):
        raise ProviderError(f"Claude Code reported an error: {str(result.get('result') or result.get('subtype'))[:200]}")
    return result


class ClaudeCodeProvider(VisionProvider):
    id = "claude_code"
    is_cloud = True

    def capabilities(self) -> ProviderCapabilities:
        path = cli_path()
        version = cli_version() if path else None
        return ProviderCapabilities(
            id=self.id, name="Claude via Claude Code (experimental)", is_cloud=True, requires_consent=True,
            available=bool(path), status=f"Found Claude Code {version}" if path else "Claude Code CLI not found on PATH.",
            models=[{"id": "", "label": "Claude Code default model"}],
            cost_note="Counts against your Claude Code plan limits or configured billing. This app cannot see your remaining allowance.",
            max_concurrency=1,
        )

    def analyze_image(self, inp: ImageInput) -> ImageAnalysis:
        if not cli_path():
            raise ProviderError("Claude Code CLI not found.")
        msg = {
            "type": "user",
            "message": {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                              "data": base64.standard_b64encode(inp.jpeg_bytes).decode()}},
                {"type": "text", "text": PROMPT},
            ]},
        }
        cmd = build_command(self.model or None, self.options.get("max_budget_usd_per_photo"))
        with tempfile.TemporaryDirectory(prefix="wac-claude-") as cwd:  # empty working directory
            try:
                proc = subprocess.run(cmd, input=json.dumps(msg) + "\n", capture_output=True, text=True,
                                      timeout=TIMEOUT_S, cwd=cwd)
            except subprocess.TimeoutExpired as e:
                raise ProviderError("Claude Code timed out.") from e
        if proc.returncode != 0 and '"type":"result"' not in proc.stdout.replace(" ", ""):
            raise ProviderError(f"Claude Code exited with code {proc.returncode}: {proc.stderr.strip()[:300]}")
        result = parse_stream(proc.stdout)
        raw = result.get("structured_output")
        if raw is None:
            try:
                raw = json.loads(result.get("result") or "")
            except json.JSONDecodeError as e:
                raise ProviderError("Claude Code returned an unparseable answer.") from e
        usage = result.get("usage") or {}
        return ImageAnalysis(
            **normalize(raw),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cost_usd=result.get("total_cost_usd"),
            cost_basis="cli_reported",
            model=self.model or "claude-code-default",
        )
