from __future__ import annotations

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from sqlmodel import select

from .models import (
    Criterion,
    Persona,
    PromptTemplate,
    Result,
    Task,
    get_criteria_map,
    get_persona_map,
    get_prompt_template,
    get_session,
)
from .ssr import DEFAULT_ANCHORS, compute_distribution, distribution_to_rating, synthesize_response


SESSION_ROOT = Path.home() / ".codex" / "session"
SESSION_ROOT.mkdir(parents=True, exist_ok=True)


@dataclass
class QueueItem:
    task_id: int


class JobManager:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self.worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self.worker_task is None:
            self.worker_task = asyncio.create_task(self._worker())

    async def enqueue(self, task_id: int) -> None:
        await self.queue.put(QueueItem(task_id=task_id))

    async def _worker(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                await self._process_task(item.task_id)
            except Exception as exc:  # noqa: BLE001
                session = get_session()
                task = session.get(Task, item.task_id)
                if task:
                    task.status = "failed"
                    task.error = str(exc)
                    task.updated_at = datetime.utcnow()
                    session.add(task)
                    session.commit()
                session.close()
            finally:
                self.queue.task_done()

    async def _process_task(self, task_id: int) -> None:
        session = get_session()
        task = session.get(Task, task_id)
        if not task:
            session.close()
            return
        task.status = "processing"
        task.updated_at = datetime.utcnow()
        session.add(task)
        session.commit()

        personas = get_persona_map(session, task.persona_ids)
        criteria = get_criteria_map(session, task.criterion_ids)
        template: PromptTemplate | None = get_prompt_template(session, task.prompt_template_id)
        results: List[Result] = []
        combined_prompt = self._build_prompt(task, template)
        try:
            for persona in personas:
                persona_payload = {
                    "id": persona.id,
                    "name": persona.name,
                    "age": persona.age,
                    "gender": persona.gender,
                    "notes": persona.notes,
                }
                for criterion in criteria:
                    anchors = criterion.anchors or DEFAULT_ANCHORS
                    response_text = synthesize_response(
                        persona_payload,
                        criterion.label,
                        task.guidance,
                        combined_prompt,
                        task.operation_context,
                        template.content if template else None,
                        task.run_seed,
                    )
                    distribution = compute_distribution(
                        response_text,
                        anchors,
                        method=task.similarity_method or "tfidf",
                    )
                    rating = distribution_to_rating(distribution)
                    summary = (
                        f"{persona.name} ({persona.age}/{persona.gender}) evaluated {criterion.label}."
                        f" {response_text}"
                    )
                    result = Result(
                        task_id=task.id,
                        persona_id=persona.id,
                        criterion_id=criterion.id,
                        summary=summary,
                        distribution=distribution,
                        rating=rating,
                    )
                    session.add(result)
                    results.append(result)
            session.commit()
            task.status = "completed"
            task.updated_at = datetime.utcnow()
            session.add(task)
            session.commit()
            self._write_session_file(task, personas, criteria, template, results)
        except Exception as exc:  # noqa: BLE001
            task.status = "failed"
            task.error = str(exc)
            task.updated_at = datetime.utcnow()
            session.add(task)
            session.commit()
        finally:
            session.close()

    def _build_prompt(self, task: Task, template: PromptTemplate | None) -> str:
        base = task.stimulus_text or ""
        if not base and task.image_name:
            base = f"Proposal based on image '{task.image_name}'"
        if task.image_name:
            base += f" (image input: {task.image_name})"
        if task.guidance:
            base += f"\nEvaluation guidance: {task.guidance}"
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
            value = task.operation_context.get(key)
            if value:
                context_lines.append(f"{label}:{value}")
        if context_lines:
            base += "\nOps context: " + " | ".join(context_lines)
        if template:
            base += f"\nTemplate: {template.name}"
        return base.strip() or "(no description)"

    def _write_session_file(
        self,
        task: Task,
        personas: List[Persona],
        criteria: List[Criterion],
        template: PromptTemplate | None,
        results: List[Result],
    ) -> Path:
        now = datetime.utcnow()
        session_dir = SESSION_ROOT / f"{now.year}" / f"{now.month:02d}" / f"{now.day:02d}"
        session_dir.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, object] = {
            "task": {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "stimulus_text": task.stimulus_text,
                "image_name": task.image_name,
                "persona_ids": task.persona_ids,
                "criterion_ids": task.criterion_ids,
                "guidance": task.guidance,
                "session_label": task.session_label,
                "operation_context": task.operation_context,
                "prompt_template_id": task.prompt_template_id,
                "similarity_method": task.similarity_method,
                "run_seed": task.run_seed,
                "created_at": task.created_at.isoformat(),
            },
            "personas": [
                {
                    "id": p.id,
                    "name": p.name,
                    "age": p.age,
                    "gender": p.gender,
                    "notes": p.notes,
                }
                for p in personas
            ],
            "criteria": [
                {
                    "id": c.id,
                    "label": c.label,
                    "question": c.question,
                    "anchors": c.anchors,
                }
                for c in criteria
            ],
            "prompt_template": {
                "id": template.id if template else None,
                "name": template.name if template else None,
                "content": template.content if template else None,
            },
            "results": [
                {
                    "persona_id": r.persona_id,
                    "criterion_id": r.criterion_id,
                    "distribution": r.distribution,
                    "rating": r.rating,
                    "summary": r.summary,
                }
                for r in results
            ],
        }
        path = session_dir / f"task-{task.id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def list_session_files() -> List[Dict[str, str]]:
    files: List[Dict[str, str]] = []
    for path in sorted(SESSION_ROOT.glob("**/task-*.json")):
        rel = path.relative_to(SESSION_ROOT)
        files.append({"path": str(rel), "updated": datetime.utcfromtimestamp(path.stat().st_mtime).isoformat()})
    return files


def load_session_file(rel_path: str) -> Path:
    resolved = (SESSION_ROOT / rel_path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(rel_path)
    return resolved


def aggregate_scores() -> List[Dict[str, object]]:
    session = get_session()
    statement = select(Result, Persona, Criterion).join(Persona, Result.persona_id == Persona.id).join(
        Criterion, Result.criterion_id == Criterion.id
    )
    aggregates: Dict[str, Dict[str, object]] = {}
    for result, persona, criterion in session.exec(statement):
        key = f"{persona.gender}-{persona.age}-{criterion.label}"
        bucket = aggregates.setdefault(
            key,
            {
                "gender": persona.gender,
                "age": persona.age,
                "criterion": criterion.label,
                "scores": [],
                "counts": [],
            },
        )
        bucket["scores"].append(result.rating)
        bucket["counts"].append(sum(result.distribution))
    session.close()

    summary: List[Dict[str, object]] = []
    for bucket in aggregates.values():
        scores: List[float] = bucket["scores"]
        avg = sum(scores) / len(scores) if scores else 0.0
        summary.append(
            {
                "gender": bucket["gender"],
                "age": bucket["age"],
                "criterion": bucket["criterion"],
                "average": round(avg, 3),
                "samples": len(scores),
            }
        )
    return summary
