from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Iterable, List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from .models import Criterion, Persona, Result, Task


# 共通設定
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
PAGE_MARGIN = 44
LINE_WIDTH = 64


def _age_band(age: int | None) -> str:
    if age is None:
        return "unknown"
    decade = (age // 10) * 10
    return f"{decade}s"


# ---------------- ReportLab fallback ----------------

def _write_block(c: canvas.Canvas, x: int, y: int, text: str, size: int = 11, leading: int = 14, width: int = LINE_WIDTH) -> int:
    import textwrap

    lines = textwrap.wrap(text, width=width)
    c.setFont("HeiseiKakuGo-W5", size)
    cursor = y
    for line in lines:
        if cursor < 40:
            c.showPage()
            c.setFont("HeiseiKakuGo-W5", size)
            cursor = A4[1] - PAGE_MARGIN
        c.drawString(x, cursor, line)
        cursor -= leading
    return cursor


def _block_title(c: canvas.Canvas, x: int, y: int, title: str) -> int:
    c.setFillColor(colors.black)
    c.setFont("HeiseiKakuGo-W5", 14)
    c.drawString(x, y, title)
    return y - 18


def _draw_distribution_bar(c: canvas.Canvas, x: int, y: int, values: Iterable[float], width: int = 380) -> int:
    bar_h = 12
    palette = [colors.HexColor("#2563eb"), colors.HexColor("#7c3aed"), colors.HexColor("#0ea5e9"), colors.HexColor("#16a34a"), colors.HexColor("#f97316")]
    cursor = x
    for idx, val in enumerate(values):
        fill = palette[idx % len(palette)]
        w = width * float(val)
        c.setFillColor(fill)
        c.rect(cursor, y - bar_h, w, bar_h, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("HeiseiKakuGo-W5", 8)
        c.drawString(cursor + 2, y - 3, f"{idx+1}:{val:.2f}")
        cursor += w
    return y - bar_h - 8


def _draw_mean_bar(c: canvas.Canvas, x: int, y: int, label: str, value: float, max_val: float = 5.0, width: int = 200) -> int:
    bar_h = 10
    pct = min(max(value / max_val, 0.0), 1.0)
    c.setFillColor(colors.HexColor("#2563eb"))
    c.rect(x, y - bar_h, width * pct, bar_h, stroke=0, fill=1)
    c.setStrokeColor(colors.black)
    c.rect(x, y - bar_h, width, bar_h, stroke=1, fill=0)
    c.setFillColor(colors.black)
    c.setFont("HeiseiKakuGo-W5", 9)
    c.drawString(x + width + 6, y - bar_h + 1, f"{value:.2f}")
    c.drawString(x, y + 2, label)
    return y - bar_h - 12


def _reportlab_task(task: Task, personas: Iterable[Persona], criteria: Iterable[Criterion], results: Iterable[Result]) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - PAGE_MARGIN

    y = _block_title(c, PAGE_MARGIN, y, f"SSR Report: {task.title}")
    meta_lines = [
        f"Status: {task.status} / Session: {task.session_label or '-'} / Created: {task.created_at:%Y-%m-%d %H:%M UTC}",
        f"Similarity: {task.similarity_method} | Seed: {task.run_seed or '-'}",
    ]
    if task.operation_context:
        ctx_text = " | ".join(f"{k}:{v}" for k, v in task.operation_context.items())
        meta_lines.append(f"Ops: {ctx_text}")
    if task.guidance:
        meta_lines.append(f"Guidance: {task.guidance}")
    if task.stimulus_text:
        meta_lines.append(f"Stimulus: {task.stimulus_text}")
    y = _write_block(c, PAGE_MARGIN, y, "\n".join(meta_lines), size=11, leading=14, width=LINE_WIDTH)

    criterion_map = {c.id: c for c in criteria if c.id is not None}
    persona_map = {p.id: p for p in personas if p.id is not None}
    seen_anchors = set()
    age_gender: dict[str, List[int]] = {}

    y = _block_title(c, PAGE_MARGIN, y, "Results (text → TF-IDF → anchors)")
    for res in results:
        persona = persona_map.get(res.persona_id)
        criterion = criterion_map.get(res.criterion_id)
        persona_label = f"{persona.name}({persona.age}/{persona.gender})" if persona else str(res.persona_id)
        criterion_label = criterion.label if criterion else str(res.criterion_id)
        dist_text = " | ".join(f"{idx+1}:{v}" for idx, v in enumerate(res.distribution))
        if criterion and criterion_label not in seen_anchors:
            anchor_text = " / ".join(criterion.anchors)
            y = _write_block(c, PAGE_MARGIN, y, f"Anchors[{criterion_label}]: {anchor_text}", size=10, width=LINE_WIDTH)
            seen_anchors.add(criterion_label)

        box_top = y
        y = _write_block(c, PAGE_MARGIN, y, f"{persona_label} × {criterion_label} → Mode:{res.rating} / Dist:{dist_text}", size=11, width=LINE_WIDTH)
        y = _draw_distribution_bar(c, PAGE_MARGIN, y, res.distribution)
        y = _write_block(c, PAGE_MARGIN, y, res.summary, size=10, leading=13, width=LINE_WIDTH)
        box_height = box_top - y
        c.setFillColor(colors.HexColor("#f5f5f5"))
        c.rect(PAGE_MARGIN - 6, y, width - PAGE_MARGIN * 2 + 12, box_height + 12, stroke=0, fill=1)
        c.setFillColor(colors.black)
        y -= 8
        if persona:
            key = f"{persona.gender}/{persona.age}"
            age_gender.setdefault(key, []).append(res.rating)

    y = _block_title(c, PAGE_MARGIN, y, "Summary")
    summary_lines: List[str] = []
    mean_pairs: List[Tuple[str, float, int]] = []
    for criterion_id, criterion in criterion_map.items():
        scores = [r.rating for r in results if r.criterion_id == criterion_id]
        if scores:
            avg = round(sum(scores) / len(scores), 2)
            summary_lines.append(f"{criterion.label}: mean {avg} (n={len(scores)})")
            mean_pairs.append((criterion.label, avg, len(scores)))
    if not summary_lines:
        summary_lines.append("No results yet.")
    y = _write_block(c, PAGE_MARGIN, y, " / ".join(summary_lines))

    if mean_pairs:
        y = _block_title(c, PAGE_MARGIN, y, "Mean ratings (1-5)")
        for label, avg, _n in mean_pairs:
            y = _draw_mean_bar(c, PAGE_MARGIN, y, label, avg, max_val=5.0, width=220)

    if age_gender:
        y = _block_title(c, PAGE_MARGIN, y, "Age/Gender aggregates")
        agg_lines = []
        for key, vals in age_gender.items():
            mean_val = sum(vals) / len(vals)
            agg_lines.append(f"{key}: mean {mean_val:.2f} (n={len(vals)})")
        y = _write_block(c, PAGE_MARGIN, y, " | ".join(agg_lines), width=LINE_WIDTH)
        band_means = sorted(((k, sum(v) / len(v), len(v)) for k, v in age_gender.items()), key=lambda x: -x[1])
        y = _block_title(c, PAGE_MARGIN, y, "Top bands")
        for k, m, n in band_means[:8]:
            y = _draw_mean_bar(c, PAGE_MARGIN, y, f"{k} (n={n})", m, max_val=5.0, width=220)

    c.showPage()
    c.save()
    return buffer.getvalue()


def _reportlab_summary(tasks: Iterable[Task], personas: Iterable[Persona], criteria: Iterable[Criterion], results: Iterable[Result]) -> bytes:
    results_list = list(results)
    task_map = {t.id: t for t in tasks if t.id is not None}
    persona_map = {p.id: p for p in personas if p.id is not None}
    criterion_map = {c.id: c for c in criteria if c.id is not None}

    buckets: dict[str, dict[str, dict[str, dict[str, List[int]]]]] = {}
    for res in results_list:
        task = task_map.get(res.task_id)
        persona = persona_map.get(res.persona_id)
        crit = criterion_map.get(res.criterion_id)
        if not task or not crit:
            continue
        gender = (persona.gender if persona else "Unknown") or "Unknown"
        band = _age_band(persona.age if persona else None)
        strategy = task.title
        strat_bucket = buckets.setdefault(strategy, {})
        crit_bucket = strat_bucket.setdefault(crit.label, {})
        gender_bucket = crit_bucket.setdefault(gender, {})
        gender_bucket.setdefault(band, []).append(res.rating)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - PAGE_MARGIN

    y = _block_title(c, PAGE_MARGIN, y, "Summary: Age/Gender means by strategy")
    y = _write_block(c, PAGE_MARGIN, y, f"Strategies: {len(buckets)} / Personas: {len(persona_map)} / Results: {len(results_list)}")

    for strategy, crit_bucket in buckets.items():
        y = _block_title(c, PAGE_MARGIN, y, f"Strategy: {strategy}")
        for crit_label, gender_bucket in crit_bucket.items():
            box_top = y
            y = _write_block(c, PAGE_MARGIN, y, f"Criterion: {crit_label}", size=12)
            lines: List[str] = []
            flat_ratings: List[int] = []
            for gender, band_bucket in gender_bucket.items():
                for band, ratings in band_bucket.items():
                    if not ratings:
                        continue
                    mean_val = sum(ratings) / len(ratings)
                    lines.append(f"{gender}/{band}: mean {mean_val:.2f} (n={len(ratings)})")
                    flat_ratings.extend(ratings)
            if lines:
                y = _write_block(c, PAGE_MARGIN, y, " | ".join(lines), width=LINE_WIDTH)
            else:
                y = _write_block(c, PAGE_MARGIN, y, "No samples", width=LINE_WIDTH)
            if flat_ratings:
                overall_mean = sum(flat_ratings) / len(flat_ratings)
                y = _draw_mean_bar(c, PAGE_MARGIN, y, "Overall mean", overall_mean, max_val=5.0, width=220)
            c.setFillColor(colors.HexColor("#eef2ff"))
            box_h = box_top - y + 10
            c.rect(PAGE_MARGIN - 6, y, width - PAGE_MARGIN * 2 + 12, box_h, stroke=0, fill=1)
            c.setFillColor(colors.black)
            y -= 6
            if y < 120:
                c.showPage()
                y = height - PAGE_MARGIN

    c.showPage()
    c.save()
    return buffer.getvalue()


# ---------------- LaTeX helpers ----------------

def _slugify(title: str) -> str:
    import re

    slug = title.strip().lower()
    slug = re.sub(r"[^\w一-龠ぁ-ゔァ-ヴーａ-ｚＡ-Ｚ０-９\-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        slug = f"report-{abs(hash(title))}"
    return slug[:80]


LATEX_TEMPLATE_HEADER = r"""
\documentclass[11pt,a4paper]{article}
\usepackage{fontspec}
\usepackage{xeCJK}
\setmainfont{Hiragino Sans}\setsansfont{Hiragino Sans}
\setCJKmainfont{Hiragino Sans}
\XeTeXlinebreaklocale "ja"
\XeTeXlinebreakskip=0pt plus 1pt
\usepackage[margin=18mm]{geometry}
\usepackage{longtable}
\usepackage{ltablex}
\keepXColumns
\usepackage{tabularx}
\usepackage{booktabs}
\usepackage[table]{xcolor}
\definecolor{lightgray}{RGB}{245,245,245}
\definecolor{barblue}{RGB}{37,99,235}
\definecolor{bargray}{RGB}{230,230,230}
\setlength{\parskip}{4pt}
\setlength{\parindent}{0pt}
\setlength{\tabcolsep}{3pt}
\renewcommand{\arraystretch}{1.15}
\newcolumntype{Y}{>{\raggedright\arraybackslash}X}
\newcommand{\ratingbar}[1]{%
  \begingroup
  \color{barblue}\rule{#1mm}{3pt}%
  \color{bargray}\rule{\dimexpr50mm-#1mm\relax}{3pt}%
  \endgroup}
"""


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def _latex_bar(value: float, max_val: float = 5.0) -> str:
    width = max(0.0, min(value / max_val, 1.0)) * 50  # mm
    return f"\\ratingbar{{{width:.1f}}}\\, {value:.2f}"


def _compile_latex(tex: str, *, slug: str) -> bytes:
    debug_dir = Path("/tmp/codex-latex-debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"{slug}.tex").write_text(tex, encoding="utf-8")
    # 生成物をリポジトリ側にも保存しておくと再コンパイルしやすい
    tex_out_dir = Path(os.getenv("SSR_TEX_OUT_DIR", "reports/tex"))
    try:
        tex_out_dir.mkdir(parents=True, exist_ok=True)
        (tex_out_dir / f"{slug}.tex").write_text(tex, encoding="utf-8")
    except Exception:
        # 保存失敗は致命的でないので握りつぶす
        pass

    skip_flag = os.getenv("SSR_SKIP_LATEX", "").lower()
    if skip_flag in ("1", "true", "yes", "on"):
        return b""

    engine = shutil.which("xelatex") or shutil.which("pdflatex")
    if not engine:
        raise RuntimeError("xelatex/pdflatex が見つかりません。TeX環境をインストールしてください。")
    with tempfile.TemporaryDirectory() as tmp:
        tex_path = Path(tmp) / f"{slug}.tex"
        tex_path.write_text(tex, encoding="utf-8")
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", tex_path.name]
        result = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
        (debug_dir / "stdout.log").write_text(result.stdout or "", encoding="utf-8")
        (debug_dir / "stderr.log").write_text(result.stderr or "", encoding="utf-8")
        pdf_path = Path(tmp) / f"{slug}.pdf"
        if pdf_path.exists():
            return pdf_path.read_bytes()
        raise RuntimeError(f"pdflatex 失敗: {result.stderr[:4000]}")


def _table_row(items: List[str], end: str = "\\\\") -> str:
    return " & ".join(items) + f" {end}\n"


def _build_task_report_latex(task: Task, personas: Iterable[Persona], criteria: Iterable[Criterion], results: Iterable[Result]) -> bytes:
    persona_map = {p.id: p for p in personas if p.id is not None}
    criterion_map = {c.id: c for c in criteria if c.id is not None}

    mean_pairs: List[Tuple[str, float, int]] = []
    age_gender: dict[str, List[int]] = {}
    for cid, criterion in criterion_map.items():
        scores = [r.rating for r in results if r.criterion_id == cid]
        if scores:
            mean_pairs.append((criterion.label, sum(scores) / len(scores), len(scores)))
    for res in results:
        persona = persona_map.get(res.persona_id)
        if persona:
            key = f"{persona.gender}/{persona.age}"
            age_gender.setdefault(key, []).append(res.rating)

    # personaごとに同一生成文を1行でまとめる
    grouped_rows: List[Tuple[str, str, str]] = []  # persona, crit block, summary
    persona_bucket: dict[int, dict[str, object]] = {}
    for res in results:
        persona = persona_map.get(res.persona_id)
        if not persona:
            continue
        bucket = persona_bucket.setdefault(
            res.persona_id,
            {"label": persona.name, "summary": None, "criteria": []},
        )
        criterion = criterion_map.get(res.criterion_id)
        c_label = criterion.label if criterion else str(res.criterion_id)
        dist = " / ".join(f"{idx+1}:{v:.2f}" for idx, v in enumerate(res.distribution))
        bucket["criteria"].append(f"{_latex_escape(c_label)}→{res.rating} [{_latex_escape(dist)}]")
        if bucket["summary"] is None:
            summary_raw = res.summary.replace("\\", " ").replace("\n", " ")
            bucket["summary"] = _latex_escape(summary_raw[:220])
    for pid, bucket in persona_bucket.items():
        crit_text = " \\quad ".join(bucket["criteria"])
        grouped_rows.append((bucket["label"], crit_text, bucket.get("summary") or ""))

    anchors_block = []
    for c in criterion_map.values():
        anchors_block.append(f"\\textbf{{{_latex_escape(c.label)}}}: " + " / ".join(_latex_escape(a) for a in c.anchors))

    meta_lines = [
        f"Status: {task.status}\\ ",
        f"Session: {task.session_label or '-'}\\ ",
        f"Created: {task.created_at:%Y-%m-%d %H:%M UTC}\\ ",
        f"Similarity: {task.similarity_method} | Seed: {task.run_seed or '-'}\\ ",
    ]
    if task.operation_context:
        meta_lines.append("Ops: " + _latex_escape(" | ".join(f"{k}:{v}" for k, v in task.operation_context.items())) + "\\ ")
    if task.guidance:
        meta_lines.append("Guidance: " + _latex_escape(task.guidance) + "\\ ")
    if task.stimulus_text:
        meta_lines.append("Stimulus: " + _latex_escape(task.stimulus_text) + "\\ ")

    tex: List[str] = [LATEX_TEMPLATE_HEADER, "\\begin{document}"]
    tex.append(f"\\section*{{SSR Report: {_latex_escape(task.title)}}}")
    tex.append("{\\footnotesize " + " ".join(meta_lines) + "}")
    if anchors_block:
        tex.append("{\\small\\textbf{Anchors}: " + " \\quad ".join(anchors_block) + "}")

    tex.append("\\subsection*{Results (persona consolidated)}")
    tex.append("{\\small%")
    tex.append("\\begin{tabularx}{\\textwidth}{p{32mm}p{60mm}X}\\toprule")
    tex.append(_table_row(["Persona", "Criteria (R / Dist)", "Summary"], end="\\\\ \\midrule"))
    for p_label, crit_block, summary_txt in grouped_rows:
        tex.append(_table_row([_latex_escape(p_label), crit_block, summary_txt]))
    tex.append("\\bottomrule\\end{tabularx}")
    tex.append("}")  # end small

    if mean_pairs:
        tex.append("\\subsection*{Mean ratings}")
        tex.append("\\begin{tabular}{@{}p{50mm}p{60mm}@{}}\\toprule")
        tex.append(_table_row(["Criterion", "Mean (bar)"], end="\\\\ \\\\midrule"))
        for label, mean_val, n in mean_pairs:
            tex.append(_table_row([f"{_latex_escape(label)} (n={n})", _latex_bar(mean_val)], end="\\\\"))
        tex.append("\\bottomrule\\end{tabular}")

    if age_gender:
        tex.append("\\subsection*{Age/Gender aggregates}")
        tex.append("\\begin{tabular}{@{}p{40mm}p{70mm}@{}}\\toprule")
        tex.append(_table_row(["Band", "Mean (bar)"], end="\\\\ \\\\midrule"))
        band_means = sorted(((k, sum(v) / len(v), len(v)) for k, v in age_gender.items()), key=lambda x: -x[1])
        for k, m, n in band_means[:12]:
            tex.append(_table_row([f"{_latex_escape(k)} (n={n})", _latex_bar(m)], end="\\\\"))
        tex.append("\\bottomrule\\end{tabular}")

    tex.append("\\end{document}")
    return _compile_latex("\n".join(tex), slug=_slugify(task.title))


def _build_summary_report_latex(tasks: Iterable[Task], personas: Iterable[Persona], criteria: Iterable[Criterion], results: Iterable[Result]) -> bytes:
    task_map = {t.id: t for t in tasks if t.id is not None}
    criterion_map = {c.id: c for c in criteria if c.id is not None}
    results_list = list(results)

    buckets: dict[str, List[int]] = {}
    for res in results_list:
        task = task_map.get(res.task_id)
        crit = criterion_map.get(res.criterion_id)
        if not task or not crit:
            continue
        key = f"{task.title} | {crit.label}"
        buckets.setdefault(key, []).append(res.rating)

    tex: List[str] = [LATEX_TEMPLATE_HEADER, "\\begin{document}"]
    tex.append("\\section*{Summary: strategy x criterion means}")
    tex.append(f"Tasks: {len(task_map)}\\ Results: {len(results_list)}\\")
    tex.append("\\begin{tabular}{p{90mm}p{40mm}}\\toprule")
    tex.append(_table_row(["Strategy / Criterion", "Mean"], end="\\\\ \\\\midrule"))
    for key, vals in sorted(buckets.items()):
        mean_val = sum(vals) / len(vals)
        tex.append(_table_row([_latex_escape(key) + f" (n={len(vals)})", f"{mean_val:.2f}"], end="\\\\"))
    tex.append("\\bottomrule\\end{tabular}")
    tex.append("\\end{document}")
    return _compile_latex("\n".join(tex), slug="summary")


# ---------------- Public API ----------------


def build_task_report(task: Task, personas: Iterable[Persona], criteria: Iterable[Criterion], results: Iterable[Result]) -> bytes:
    if os.getenv("SSR_REPORT_ENGINE", "latex") == "latex":
        return _build_task_report_latex(task, personas, criteria, results)
    return _reportlab_task(task, personas, criteria, results)


def build_summary_report(tasks: Iterable[Task], personas: Iterable[Persona], criteria: Iterable[Criterion], results: Iterable[Result]) -> bytes:
    if os.getenv("SSR_REPORT_ENGINE", "latex") == "latex":
        return _build_summary_report_latex(tasks, personas, criteria, results)
    return _reportlab_summary(tasks, personas, criteria, results)
