from __future__ import annotations

import json
import textwrap
from io import BytesIO
from typing import Iterable, List

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from .models import Criterion, Persona, Result, Task

pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))


def _write_block(c: canvas.Canvas, x: int, y: int, text: str, size: int = 11, leading: int = 14) -> int:
    lines = textwrap.wrap(text, width=72)
    c.setFont("HeiseiKakuGo-W5", size)
    cursor = y
    for line in lines:
        if cursor < 40:
            c.showPage()
            c.setFont("HeiseiKakuGo-W5", size)
            cursor = A4[1] - 40
        c.drawString(x, cursor, line)
        cursor -= leading
    return cursor


def _block_title(c: canvas.Canvas, x: int, y: int, title: str) -> int:
    c.setFont("HeiseiKakuGo-W5", 14)
    c.drawString(x, y, title)
    return y - 18


def build_task_report(
    task: Task,
    personas: Iterable[Persona],
    criteria: Iterable[Criterion],
    results: Iterable[Result],
) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40

    y = _block_title(c, 40, y, f"SSR Report: {task.title}")
    y = _write_block(
        c,
        40,
        y,
        f"Status: {task.status} / Session: {task.session_label or '-'} / Created: {task.created_at:%Y-%m-%d %H:%M UTC}",
    )
    if task.operation_context:
        ctx_text = " | ".join(f"{k}:{v}" for k, v in task.operation_context.items())
        y = _write_block(c, 40, y, f"Ops context: {ctx_text}")
    if task.guidance:
        y = _write_block(c, 40, y, f"Evaluation guidance: {task.guidance}")
    if task.stimulus_text:
        y = _block_title(c, 40, y, "Stimulus text")
        y = _write_block(c, 40, y, task.stimulus_text)

    criterion_map = {c.id: c for c in criteria if c.id is not None}
    persona_map = {p.id: p for p in personas if p.id is not None}

    y = _block_title(c, 40, y, "Results")
    for res in results:
        persona = persona_map.get(res.persona_id)
        criterion = criterion_map.get(res.criterion_id)
        persona_label = f"{persona.name}({persona.age}/{persona.gender})" if persona else str(res.persona_id)
        criterion_label = criterion.label if criterion else str(res.criterion_id)
        dist_text = " | ".join(f"{idx+1}:{v}" for idx, v in enumerate(res.distribution))
        y = _write_block(
            c,
            40,
            y,
            f"{persona_label} x {criterion_label} -> Mode:{res.rating} / Dist:{dist_text}",
        )
        y = _write_block(c, 40, y, res.summary, size=10, leading=13)

    y = _block_title(c, 40, y, "Summary")
    summary_lines: List[str] = []
    for criterion_id, criterion in criterion_map.items():
        scores = [r.rating for r in results if r.criterion_id == criterion_id]
        if scores:
            avg = round(sum(scores) / len(scores), 2)
            summary_lines.append(f"{criterion.label}: mean {avg} (n={len(scores)})")
    if not summary_lines:
        summary_lines.append("No results yet.")
    y = _write_block(c, 40, y, " / ".join(summary_lines))

    # Appendix: raw JSON
    y = _block_title(c, 40, y, "Appendix: task JSON")
    raw_json = {
        "task": task.dict(),
        "personas": [p.dict() for p in personas],
        "criteria": [c.dict() for c in criteria],
        "results": [r.dict() for r in results],
    }
    y = _write_block(c, 40, y, json.dumps(raw_json, ensure_ascii=False)[:1500], size=8, leading=10)

    c.showPage()
    c.save()
    return buffer.getvalue()
