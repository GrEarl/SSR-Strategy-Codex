from __future__ import annotations

import asyncio
import base64
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List

from sqlmodel import select

from .jobs import JobManager
from .models import Criterion, Persona, PromptTemplate, Result, Task, get_session, init_db
from .reports import build_summary_report, build_task_report
from .ssr import GAME_OPS_ANCHORS, SPEND_ANCHORS


ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "samples"
REPORTS_DIR = ROOT / "reports"


def parse_personas(md_path: Path) -> List[Persona]:
    text = md_path.read_text(encoding="utf-8")
    personas: List[Persona] = []
    used_names: dict[str, int] = {}

    def _clean_notes(raw: str) -> str:
        # マークダウン装飾を軽く除去し、空行をつぶす
        raw = raw.replace("**", "")
        lines = [ln.strip() for ln in raw.splitlines()]
        lines = [ln for ln in lines if ln]
        return " / ".join(lines)

    groups = re.split(r"(?=#\s*\d+代)", text)
    for group in groups:
        header = re.match(r"#\s*([0-9]+代)", group.strip())
        segment_label = header.group(1) if header else "不明"
        blocks = re.split(r"(?=ペルソナ\s*\d+)", group)
        for block in blocks:
            name_match = re.search(r"ペルソナ\s*(\d+)", block)
            if not name_match:
                continue
            age_match = re.search(r"年齢\*\*\s*[：:]?\s*([0-9]+)", block)
            if age_match:
                age_val = int(age_match.group(1))
            else:
                # 年齢が明記されていない場合は年代の中央値を使う
                decade = int(segment_label.replace("代", "")) if segment_label.endswith("代") else 0
                age_val = decade + 5 if decade else 30
            base_name = f"{segment_label}-ペルソナ{name_match.group(1)}"
            dup_count = used_names.get(base_name, 0)
            name = f"{base_name}-v{dup_count+1}" if dup_count else base_name
            used_names[base_name] = dup_count + 1
            # ペルソナ説明全文を notes に格納
            note_body = re.sub(r"^ペルソナ\s*\d+\s*", "", block.strip(), flags=re.MULTILINE)
            note_body = re.sub(r"#\s*[0-9]+代", "", note_body)
            notes = _clean_notes(note_body)
            personas.append(Persona(name=name, age=age_val, gender="Unknown", notes=notes))
    return personas


def ensure_personas(session) -> List[int]:
    existing = {p.name: p for p in session.exec(select(Persona)).all()}
    seen = set(existing.keys())
    added: List[Persona] = []
    for persona in parse_personas(SAMPLES_DIR / "ペルソナ.md"):
        if persona.name in seen:
            # 既存レコードに notes 等がなければ補完
            cur = existing[persona.name]
            updated = False
            if not cur.notes and persona.notes:
                cur.notes = persona.notes
                updated = True
            if persona.age and cur.age != persona.age:
                cur.age = persona.age
                updated = True
            if updated:
                session.add(cur)
            continue
        session.add(persona)
        added.append(persona)
        seen.add(persona.name)
    session.commit()
    for p in added:
        session.refresh(p)
        existing[p.name] = p
    ids = [p.id for p in existing.values() if p.id is not None]
    # ペルソナ数を間引く: 環境変数で上限または比率を指定
    limit_env = os.getenv("SSR_PERSONA_LIMIT")
    frac_env = os.getenv("SSR_PERSONA_FRACTION")
    if limit_env:
        try:
            limit = max(1, int(limit_env))
            ids = ids[:limit]
        except ValueError:
            pass
    elif frac_env:
        try:
            import math

            frac = float(frac_env)
            k = max(1, math.ceil(len(ids) * frac))
            ids = ids[:k]
        except ValueError:
            pass
    return ids


def ensure_criteria(session) -> List[int]:
    labels = {c.label: c for c in session.exec(select(Criterion)).all()}
    created: List[Criterion] = []
    if "継続意向" not in labels:
        created.append(
            Criterion(
                label="継続意向",
                question="この運営施策後もどの程度プレイを続けるか？",
                anchors=GAME_OPS_ANCHORS,
            )
        )
    if "課金意欲" not in labels:
        created.append(
            Criterion(
                label="課金意欲",
                question="この施策でどの程度課金したくなるか？",
                anchors=SPEND_ANCHORS,
            )
        )
    for c in created:
        session.add(c)
    session.commit()
    for c in created:
        session.refresh(c)
        labels[c.label] = c
    return [c.id for c in labels.values() if c.id is not None]


def ensure_template(session) -> int | None:
    tpl = session.exec(select(PromptTemplate).where(PromptTemplate.name == "ソシャゲ運営評価" )).first()
    if tpl:
        return tpl.id
    tpl = PromptTemplate(
        name="ソシャゲ運営評価",
        description="ソーシャルゲーム運営施策のプレイ継続・課金影響を評価するプロンプト",
        content="プレイヤーとして施策を見たときの継続意向と課金意欲を率直に述べてください。",
    )
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return tpl.id


def load_image_b64(path: Path) -> tuple[str, str]:
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return path.name, data


def ensure_tasks(session, persona_ids: List[int], criterion_ids: List[int], template_id: int | None, similarity_method: str) -> List[Task]:
    tasks: List[Task] = []
    for img_path in sorted(SAMPLES_DIR.glob("*.png")):
        title = f"戦略:{img_path.stem}"
        existing = session.exec(select(Task).where(Task.title == title)).first()
        if existing:
            existing.similarity_method = similarity_method
            existing.status = "pending"
            existing.error = None
            existing.updated_at = datetime.utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            tasks.append(existing)
            continue
        image_name, image_data = load_image_b64(img_path)
        task = Task(
            title=title,
            stimulus_text=f"ソーシャルゲーム運営戦略 {img_path.stem} の評価",
            image_name=image_name,
            image_data=image_data,
            persona_ids=persona_ids,
            criterion_ids=criterion_ids,
            guidance="宣伝素材としてだけでなく、ゲーム体験とライブオペレーションの持続性を評価する",
            session_label=f"samples-{datetime.utcnow():%Y%m%d}",
            operation_context={
                "game_title": "Sample LiveOps",
                "genre": "RPG",
                "target_metric": "Retention & ARPPU",
                "liveops_cadence": "Weekly",
                "monetization": "Gacha + BP",
            },
            prompt_template_id=template_id,
            similarity_method=similarity_method,
            run_seed=42,
            status="pending",
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        tasks.append(task)
    return tasks


def process_tasks(task_ids: List[int], *, total_units: int) -> None:

    def progress_logger(payload: dict[str, object]) -> None:
        kind = payload.get("kind")
        if kind == "persona_done":
            done = int(payload.get("global_done", 0))
            total = int(payload.get("global_total", max(1, total_units)))
            pct = (done / total) * 100 if total else 0.0
            task_title = str(payload.get("task_title", ""))
            persona = str(payload.get("persona_name", ""))
            idx = payload.get("persona_index")
            ptotal = payload.get("persona_total")
            pos = f"{idx}/{ptotal}" if idx and ptotal else ""
            qsize = payload.get("queue_size", 0)
            print(f"[{done}/{total} {pct:5.1f}%] {task_title} {pos} persona:{persona} queue:{qsize}", flush=True)
        elif kind == "task_done":
            task_title = str(payload.get("task_title", ""))
            status = str(payload.get("status", ""))
            print(f"[task] {task_title} -> {status}", flush=True)

    async def run_all():
        mgr = JobManager(total_units=total_units, progress_callback=progress_logger)
        await mgr.start()
        for tid in task_ids:
            await mgr.enqueue(tid)
        await mgr.queue.join()
        await mgr.stop()

    asyncio.run(run_all())


def export_reports(tasks: List[Task]) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    session = get_session()
    personas = session.exec(select(Persona)).all()
    criteria = session.exec(select(Criterion)).all()
    all_results = session.exec(select(Result)).all()
    for task in tasks:
        task_personas = [p for p in personas if p.id in task.persona_ids]
        task_criteria = [c for c in criteria if c.id in task.criterion_ids]
        task_results = [r for r in all_results if r.task_id == task.id]
        pdf_bytes = build_task_report(task, task_personas, task_criteria, task_results)
        out_path = REPORTS_DIR / f"{task.title.replace(' ', '_')}.pdf"
        out_path.write_bytes(pdf_bytes)
    summary_pdf = build_summary_report(tasks, personas, criteria, all_results)
    (REPORTS_DIR / "summary.pdf").write_bytes(summary_pdf)
    session.close()


def main() -> None:
    init_db()
    session = get_session()
    persona_ids = ensure_personas(session)
    criterion_ids = ensure_criteria(session)
    template_id = ensure_template(session)
    similarity_method = os.getenv("SSR_METHOD", "tfidf")
    tasks = ensure_tasks(session, persona_ids, criterion_ids, template_id, similarity_method)
    persona_counts = {t.id: len(t.persona_ids or []) for t in tasks if t.id is not None}
    session.close()
    task_ids = [tid for tid in persona_counts.keys()]
    process_tasks(task_ids, total_units=sum(persona_counts.values()))
    # 再取得して最新状態をレポートに反映
    session = get_session()
    refreshed_tasks = session.exec(select(Task)).all()
    session.close()
    export_reports(refreshed_tasks)
    print(f"Processed {len(tasks)} tasks with method={similarity_method}. Reports -> {REPORTS_DIR}")


if __name__ == "__main__":
    main()
