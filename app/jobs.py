from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
from typing import Callable, Dict, List, Optional

from sqlmodel import select

from .codex_runner import CodexExecError, CodexSSRResult, run_codex_ssr
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


# Codex CLI writes session JSONL under ~/.codex/sessions/<year>/<month>/<day>/
# (plural “sessions”). We also check singular for compatibility.
SESSION_ROOTS = [Path.home() / ".codex" / "sessions", Path.home() / ".codex" / "session", Path.cwd() / ".codex-local" / ".codex" / "sessions"]


@dataclass
class QueueItem:
    task_id: int


class JobManager:
    def __init__(self, *, total_units: int = 0, progress_callback: Optional[Callable[[Dict[str, object]], None]] = None) -> None:
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self.workers: List[asyncio.Task] = []
        self.max_concurrency = max(1, int(os.getenv("SSR_MAX_CONCURRENCY", "4")))
        # ペルソナ単位の同時実行数。明示指定がなければ全体のmaxと同一にする
        self.persona_concurrency = max(1, int(os.getenv("SSR_PERSONA_CONCURRENCY", str(self.max_concurrency))))
        self.total_units = max(0, total_units)
        self.completed_units = 0
        self.progress_cb = progress_callback

    async def start(self) -> None:
        if self.workers:
            return
        for _ in range(self.max_concurrency):
            self.workers.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        if not self.workers:
            return
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()

    async def enqueue(self, task_id: int) -> None:
        await self.queue.put(QueueItem(task_id=task_id))

    def _report_progress(
        self,
        *,
        kind: str,
        task: Task,
        persona_name: str | None = None,
        persona_index: int | None = None,
        persona_total: int | None = None,
        status: str | None = None,
    ) -> None:
        if kind == "persona_done":
            self.completed_units += 1
        if not self.progress_cb:
            return
        payload: Dict[str, object] = {
            "kind": kind,
            "task_id": task.id,
            "task_title": task.title,
            "global_done": self.completed_units,
            "global_total": self.total_units or 1,
            "queue_size": self.queue.qsize(),
        }
        if persona_name:
            payload["persona_name"] = persona_name
        if persona_index is not None:
            payload["persona_index"] = persona_index
        if persona_total is not None:
            payload["persona_total"] = persona_total
        if status:
            payload["status"] = status
        self.progress_cb(payload)

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
        combined_prompt = self._build_prompt(task, template)
        method = task.similarity_method or "codex"
        fallback_on_error = os.getenv("CODEX_FALLBACK_ON_ERROR", "1") != "0"
        persona_total = len(personas) or 1
        persona_done = 0
        persona_texts: List[tuple[Persona, str]] = []
        persona_errors: List[str] = []

        sem = asyncio.Semaphore(self.persona_concurrency)

        async def generate_for_persona(persona: Persona) -> None:
            nonlocal persona_done
            persona_payload = {
                "id": persona.id,
                "name": persona.name,
                "age": persona.age,
                "gender": persona.gender,
                "notes": persona.notes,
            }
            response_text = ""
            try:
                if method == "codex":
                    codex_res: CodexSSRResult = await asyncio.to_thread(
                        run_codex_ssr,
                        persona_payload,
                        "combined",
                        "",
                        [],
                        combined_prompt,
                        task.guidance,
                        task.operation_context,
                        template.content if template else None,
                        task.image_data,
                        task.image_name,
                    )
                    response_text = codex_res.summary
                else:
                    response_text = synthesize_response(
                        persona_payload,
                        "combined",
                        task.guidance,
                        combined_prompt,
                        task.operation_context,
                        template.content if template else None,
                        task.run_seed,
                    )
            except Exception as exc:  # noqa: BLE001
                if not fallback_on_error:
                    raise
                response_text = synthesize_response(
                    persona_payload,
                    "combined",
                    task.guidance,
                    combined_prompt,
                    task.operation_context,
                    template.content if template else None,
                    task.run_seed,
                )
                persona_errors.append(f"codex exec failed for {persona.name}: {exc}")
            finally:
                persona_done += 1
                self._report_progress(
                    kind="persona_done",
                    task=task,
                    persona_name=persona.name,
                    persona_index=persona_done,
                    persona_total=persona_total,
                )
            persona_texts.append((persona, response_text))

        tasks_async = [asyncio.create_task(self._limited(sem, generate_for_persona, persona)) for persona in personas]
        errors: List[Exception] = []
        for res in await asyncio.gather(*tasks_async, return_exceptions=True):
            if isinstance(res, Exception):
                errors.append(res)
        if errors:
            # 最初の例外のみ記録してタスクを失敗扱いにする
            task.status = "failed"
            task.error = str(errors[0])
            task.updated_at = datetime.utcnow()
            session.add(task)
            session.commit()
            session.close()
            return

        results: List[Result] = []
        for persona, response_text in persona_texts:
            for criterion in criteria:
                anchors = criterion.anchors or DEFAULT_ANCHORS
                distribution = compute_distribution(
                    response_text,
                    anchors,
                    method="embed" if method == "codex" else method,
                )
                rating = distribution_to_rating(distribution)
                summary = (
                    f"{persona.name} ({persona.age}/{persona.gender}) evaluated {criterion.label}."
                    f" {response_text}"
                ).strip()
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
        if persona_errors:
            task.error = "; ".join(persona_errors)
        task.status = "completed"
        task.updated_at = datetime.utcnow()
        session.add(task)
        session.commit()
        self._report_progress(kind="task_done", task=task, status=task.status)
        session.close()

    async def _limited(self, sem: asyncio.Semaphore, func, *args, **kwargs):
        async with sem:
            return await func(*args, **kwargs)

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


def list_session_files() -> List[Dict[str, str]]:
    files: List[Dict[str, str]] = []
    for root in SESSION_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.glob("**/*.jsonl")):
            rel = path.relative_to(root)
            files.append({"path": str(rel), "updated": datetime.utcfromtimestamp(path.stat().st_mtime).isoformat()})
    return files


def load_session_file(rel_path: str) -> Path:
    for root in SESSION_ROOTS:
        candidate = (root / rel_path).resolve()
        if candidate.exists():
            return candidate
    raise FileNotFoundError(rel_path)


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
