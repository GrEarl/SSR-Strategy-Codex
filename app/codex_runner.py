from __future__ import annotations

import base64
import json
import re
import subprocess
import textwrap
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

from .ssr import normalize_text


@dataclass
class CodexSSRResult:
    summary: str
    raw_output: str


class CodexExecError(Exception):
    """Raised when codex exec fails or returns unusable output."""


def _build_exec_prompt(
    persona: Dict[str, str],
    criterion_label: str,
    criterion_question: str,
    anchors: Sequence[str],
    stimulus: str,
    guidance: str | None,
    operation_context: Dict[str, str] | None,
    template_text: str | None,
) -> str:
    anchor_lines = "\n".join(f"{idx+1}. {normalize_text(a)}" for idx, a in enumerate(anchors))
    context_lines = []
    for key, label in [
        ("game_title", "Game"),
        ("genre", "Genre"),
        ("target_metric", "Target KPI"),
        ("liveops_cadence", "Cadence"),
        ("monetization", "Monetization"),
        ("seasonality", "Seasonality"),
        ("notes", "Notes"),
    ]:
        value = (operation_context or {}).get(key)
        if value:
            context_lines.append(f"{label}:{value}")
    ctx_text = " | ".join(context_lines) or "-"
    guide_text = guidance or "-"
    template_clause = normalize_text(template_text or "-")
    persona_line = f"{persona.get('name', 'Persona')} ({persona.get('age', '?')}/{persona.get('gender', '?')})"

    return textwrap.dedent(
        f"""
        You act as a semantic similarity rater for consumer research.
        Respond AS JSON ONLY with keys: "summary" (one paragraph), "distribution" (5 floats summing to 1.0 in Likert order 1-5), "rating" (integer 1-5 equal to the argmax of distribution).
        Persona: {persona_line}
        Criterion: {criterion_label}
        Question: {criterion_question}
        Anchors (1=lowest,5=highest):
        {anchor_lines}
        Stimulus: {stimulus}
        Guidance: {guide_text}
        Ops context: {ctx_text}
        Prompt template: {template_clause}
        Produce human-like qualitative reasoning that aligns with the persona and anchors, then map it to the Likert distribution.
        JSON only, no markdown fences.
        """
    ).strip()


def _decode_image(image_b64: str, image_name: str | None, workdir: Path) -> Path:
    suffix = Path(image_name or "image.png").suffix or ".png"
    img_path = workdir / f"input{suffix}"
    img_path.write_bytes(base64.b64decode(image_b64))
    return img_path


def _extract_json(text: str) -> Dict[str, object]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise CodexExecError("codex exec returned no JSON payload")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise CodexExecError(f"invalid JSON from codex exec: {exc}") from exc


def run_codex_ssr(
    persona: Dict[str, str],
    criterion_label: str,
    criterion_question: str,
    anchors: Sequence[str],
    stimulus: str,
    guidance: str | None,
    operation_context: Dict[str, str] | None,
    template_text: str | None,
    image_b64: str | None,
    image_name: str | None,
    timeout: int = 120,
) -> CodexSSRResult:
    prompt = _build_exec_prompt(persona, criterion_label, criterion_question, anchors, stimulus, guidance, operation_context, template_text)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        last_path = tmp_path / "last.txt"
        cmd = [
            "codex",
            "exec",
            "--model",
            "gpt-5.1",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--skip-git-repo-check",
            "--output-last-message",
            str(last_path),
        ]
        if image_b64:
            img_path = _decode_image(image_b64, image_name, tmp_path)
            cmd.extend(["--image", str(img_path)])
        cmd.append(prompt)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise CodexExecError(result.stderr.strip() or "codex exec failed")
        if not last_path.exists():
            raise CodexExecError("codex exec produced no last message")
        raw = last_path.read_text(encoding="utf-8").strip()
    payload = _extract_json(raw)
    summary = normalize_text(str(payload.get("summary", "")))
    return CodexSSRResult(summary=summary, raw_output=raw)
