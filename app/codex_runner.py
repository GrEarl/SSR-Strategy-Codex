from __future__ import annotations

import base64
import json
import os
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
    persona_line = f"{persona.get('name', 'Persona')} ({persona.get('age', '?')}/{persona.get('gender', '?')})"
    persona_note = persona.get("notes") or "（詳細記載なし）"
    ctx_lines = []
    for key in ["game_title", "genre", "target_metric", "liveops_cadence", "monetization", "seasonality", "notes"]:
        val = (operation_context or {}).get(key)
        if val:
            ctx_lines.append(str(val))
    ctx_text = " | ".join(ctx_lines)
    guide_text = guidance or ""
    return textwrap.dedent(
        f"""
        あなたは以下のペルソナになりきり、「このゲームが今まさに次の運営施策を実施している状態」でプレイしている自分を想像してください。その状況下でのプレイ感情・行動意図を日本語で1〜2文（一行）だけ述べてください。数値・評価・箇条書き・マークダウンは禁止です。
        ペルソナ: {persona_line}
        ペルソナ詳細: {persona_note}
        運営施策の内容: {stimulus}
        補足ガイダンス: {guide_text}
        運営コンテキスト: {ctx_text}
        継続したい／課金したい／離脱したい等の動機や不安があれば具体的に触れてください。
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
    prompt = _build_exec_prompt(
        persona, criterion_label, criterion_question, anchors, stimulus, guidance, operation_context, template_text
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cmd = [
            "codex",
            "exec",
            "--model",
            "gpt-5.1",
            "--sandbox",
            os.getenv("CODEX_SANDBOX", "danger-full-access"),
            "--color",
            "never",
            "--skip-git-repo-check",
            "--json",
        ]
        if image_b64:
            img_path = _decode_image(image_b64, image_name, tmp_path)
            cmd.extend(["--image", str(img_path)])
        # 明示的にオプション終端を入れてプロンプトを確実に渡す
        cmd.append("--")
        cmd.append(prompt or "(no prompt)")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log_path = Path(os.getenv("CODEX_EXEC_LOG", "/tmp/codex-exec.log"))
        log_path.write_text(
            f"cmd={' '.join(cmd)}\nreturncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}\n",
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise CodexExecError((result.stderr or result.stdout).strip() or "codex exec failed")
        summary = ""
        for ln in result.stdout.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "item.completed":
                item = obj.get("item", {})
                if item.get("type") == "agent_message":
                    summary = item.get("text", "")
        if not summary:
            raise CodexExecError("codex exec returned no agent_message")
    summary = normalize_text(summary)
    return CodexSSRResult(summary=summary, raw_output=result.stdout.strip())
