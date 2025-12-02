from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .eval import aggregate_task_panels, correlation_attainment, expected_rating, ks_similarity, normalize_distribution
from .jobs import JobManager, aggregate_scores, list_session_files, load_session_file
from .models import Criterion, HumanBenchmark, Persona, PromptTemplate, Result, Task, get_session, init_db
from .reports import build_task_report
from .ssr import DEFAULT_ANCHORS

app = FastAPI(title="SSR Strategy Codex", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
job_manager = JobManager()


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    await job_manager.start()


def get_db() -> Session:
    db = get_session()
    try:
        yield db
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    personas = db.exec(select(Persona)).all()
    criteria = db.exec(select(Criterion)).all()
    templates_q = db.exec(select(PromptTemplate)).all()
    tasks = db.exec(select(Task)).all()
    benchmarks = db.exec(select(HumanBenchmark)).all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "personas": personas,
            "criteria": criteria,
            "tasks": tasks,
            "default_anchors": DEFAULT_ANCHORS,
            "prompt_templates": templates_q,
            "benchmarks": benchmarks,
        },
    )


@app.get("/api/personas")
async def list_personas(db: Session = Depends(get_db)) -> List[Persona]:
    return db.exec(select(Persona)).all()


@app.post("/api/personas", status_code=201)
async def create_persona(payload: Persona, db: Session = Depends(get_db)) -> Persona:
    db.add(payload)
    db.commit()
    db.refresh(payload)
    return payload


@app.delete("/api/personas/{persona_id}", status_code=204)
async def delete_persona(persona_id: int, db: Session = Depends(get_db)) -> None:
    persona = db.get(Persona, persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    db.delete(persona)
    db.commit()


@app.get("/api/criteria")
async def list_criteria(db: Session = Depends(get_db)) -> List[Criterion]:
    return db.exec(select(Criterion)).all()


class CriterionPayload(Criterion):
    anchors: Optional[List[str]] = None


@app.post("/api/criteria", status_code=201)
async def create_criterion(payload: CriterionPayload, db: Session = Depends(get_db)) -> Criterion:
    anchors = payload.anchors or DEFAULT_ANCHORS
    criterion = Criterion(label=payload.label, question=payload.question, anchors=anchors)
    db.add(criterion)
    db.commit()
    db.refresh(criterion)
    return criterion


@app.delete("/api/criteria/{criterion_id}", status_code=204)
async def delete_criterion(criterion_id: int, db: Session = Depends(get_db)) -> None:
    criterion = db.get(Criterion, criterion_id)
    if not criterion:
        raise HTTPException(status_code=404, detail="Criterion not found")
    db.delete(criterion)
    db.commit()


@app.get("/api/benchmarks")
async def list_benchmarks(db: Session = Depends(get_db)) -> List[HumanBenchmark]:
    return db.exec(select(HumanBenchmark)).all()


class BenchmarkPayload(HumanBenchmark):
    distribution: List[float]


@app.post("/api/benchmarks", status_code=201)
async def create_benchmark(payload: BenchmarkPayload, db: Session = Depends(get_db)) -> HumanBenchmark:
    dist = normalize_distribution(payload.distribution or [])
    if len(dist) != 5:
        raise HTTPException(status_code=400, detail="Distribution must contain 5 values")
    benchmark = HumanBenchmark(
        label=payload.label,
        session_label=payload.session_label,
        criterion_label=payload.criterion_label,
        distribution=dist,
        sample_size=payload.sample_size or 100,
    )
    db.add(benchmark)
    db.commit()
    db.refresh(benchmark)
    return benchmark


@app.delete("/api/benchmarks/{benchmark_id}", status_code=204)
async def delete_benchmark(benchmark_id: int, db: Session = Depends(get_db)) -> None:
    benchmark = db.get(HumanBenchmark, benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    db.delete(benchmark)
    db.commit()


@app.get("/api/prompt-templates")
async def list_prompt_templates(db: Session = Depends(get_db)) -> List[PromptTemplate]:
    return db.exec(select(PromptTemplate)).all()


class TemplatePayload(PromptTemplate):
    pass


@app.post("/api/prompt-templates", status_code=201)
async def create_prompt_template(payload: TemplatePayload, db: Session = Depends(get_db)) -> PromptTemplate:
    template = PromptTemplate(name=payload.name, description=payload.description, content=payload.content)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@app.delete("/api/prompt-templates/{template_id}", status_code=204)
async def delete_prompt_template(template_id: int, db: Session = Depends(get_db)) -> None:
    template = db.get(PromptTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()


class TaskPayload(Task):
    persona_ids: List[int]
    criterion_ids: List[int]


@app.post("/api/tasks", status_code=201)
async def create_task(payload: TaskPayload, db: Session = Depends(get_db)) -> Task:
    personas = db.exec(select(Persona).where(Persona.id.in_(payload.persona_ids))).all()
    criteria = db.exec(select(Criterion).where(Criterion.id.in_(payload.criterion_ids))).all()
    template = None
    if payload.prompt_template_id:
        template = db.get(PromptTemplate, payload.prompt_template_id)
        if not template:
            raise HTTPException(status_code=400, detail="Invalid prompt template ID")
    if len(personas) != len(payload.persona_ids):
        raise HTTPException(status_code=400, detail="Invalid persona IDs")
    if len(criteria) != len(payload.criterion_ids):
        raise HTTPException(status_code=400, detail="Invalid criterion IDs")

    task = Task(
        title=payload.title,
        stimulus_text=payload.stimulus_text,
        image_name=payload.image_name,
        image_data=payload.image_data,
        persona_ids=payload.persona_ids,
        criterion_ids=payload.criterion_ids,
        guidance=payload.guidance,
        session_label=payload.session_label,
        operation_context=payload.operation_context or {},
        prompt_template_id=payload.prompt_template_id,
        similarity_method=payload.similarity_method or "codex",
        run_seed=payload.run_seed,
        status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    await job_manager.enqueue(task.id)
    return task


@app.get("/api/tasks")
async def list_tasks(db: Session = Depends(get_db)) -> List[dict]:
    tasks = db.exec(select(Task)).all()
    task_ids = [t.id for t in tasks]
    results_map: Dict[int, List[Result]] = {tid: [] for tid in task_ids}
    if task_ids:
        res_statement = select(Result).where(Result.task_id.in_(task_ids))
        for res in db.exec(res_statement).all():
            results_map[res.task_id].append(res)
    output = []
    for task in tasks:
        output.append(
            {
                "task": task,
                "results": results_map.get(task.id, []),
            }
        )
    return output


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: int, db: Session = Depends(get_db)) -> dict:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    results = db.exec(select(Result).where(Result.task_id == task_id)).all()
    return {"task": task, "results": results}


@app.post("/api/tasks/{task_id}/enqueue")
async def enqueue_task(task_id: int, db: Session = Depends(get_db)) -> dict:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "pending"
    task.updated_at = datetime.utcnow()
    task.error = None
    db.add(task)
    db.commit()
    await job_manager.enqueue(task_id)
    return {"status": "enqueued"}


@app.get("/api/evaluate")
async def evaluate(db: Session = Depends(get_db)) -> dict:
    benchmarks = db.exec(select(HumanBenchmark)).all()
    if not benchmarks:
        return {"matches": [], "correlation_attainment": 0.0, "ceiling": 0.0}
    criteria = {c.id: c for c in db.exec(select(Criterion)).all()}
    tasks = db.exec(select(Task).where(Task.status == "completed")).all()
    task_ids = [t.id for t in tasks]
    results_map: Dict[int, List[Result]] = {tid: [] for tid in task_ids}
    if task_ids:
        res_statement = select(Result).where(Result.task_id.in_(task_ids))
        for res in db.exec(res_statement).all():
            results_map[res.task_id].append(res)

    matches: List[dict] = []
    synthetic_means: List[float] = []
    matched_benchmarks: List[HumanBenchmark] = []
    for bench in benchmarks:
        matched_task = next(
            (
                t
                for t in tasks
                if (bench.session_label and t.session_label == bench.session_label)
                or (bench.session_label is None and bench.label == t.title)
            ),
            None,
        )
        if not matched_task:
            continue
        panels = aggregate_task_panels(matched_task, results_map.get(matched_task.id, []), criteria)
        panel = panels.get(bench.criterion_label)
        if not panel:
            continue
        ks = ks_similarity(bench.distribution, panel["distribution"])
        human_mean = expected_rating(bench.distribution)
        synthetic_means.append(panel["mean_rating"])
        matched_benchmarks.append(bench)
        matches.append(
            {
                "benchmark_id": bench.id,
                "task_id": matched_task.id,
                "title": matched_task.title,
                "session_label": bench.session_label,
                "criterion": bench.criterion_label,
                "ks_similarity": ks,
                "human_mean": human_mean,
                "synthetic_mean": panel["mean_rating"],
                "sample_size": panel["sample_size"],
            }
        )
    attainment, ceiling = correlation_attainment(matched_benchmarks, synthetic_means, trials=300)
    return {"matches": matches, "correlation_attainment": attainment, "ceiling": ceiling}


@app.get("/api/tasks/{task_id}/report")
async def report_task(task_id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    personas = db.exec(select(Persona).where(Persona.id.in_(task.persona_ids))).all()
    criteria = db.exec(select(Criterion).where(Criterion.id.in_(task.criterion_ids))).all()
    results = db.exec(select(Result).where(Result.task_id == task_id)).all()
    pdf_bytes = build_task_report(task, personas, criteria, results)
    headers = {"Content-Disposition": f"attachment; filename=task-{task_id}.pdf"}
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers=headers)


@app.get("/api/aggregates")
async def aggregates() -> List[dict]:
    return aggregate_scores()


@app.get("/api/sessions")
async def sessions() -> List[dict]:
    return list_session_files()


@app.get("/api/sessions/{session_path:path}")
async def download_session(session_path: str) -> FileResponse:
    file_path = load_session_file(session_path)
    return FileResponse(file_path)


@app.post("/api/bootstrap")
async def bootstrap(db: Session = Depends(get_db)) -> dict:
    if db.exec(select(Persona)).first():
        return {"status": "skipped", "reason": "Data already present"}
    personas = [
        Persona(name="Casual A", age=19, gender="Female", notes="Plays daily, no spending"),
        Persona(name="Core B", age=32, gender="Male", notes="Spends $100-200 per month"),
        Persona(name="Returnee C", age=28, gender="Female", notes="Comes back only for events"),
    ]
    criteria = [
        Criterion(
            label="Retention intent",
            question="Would you keep playing this game after this initiative?",
            anchors=[
                "Would not continue at all",
                "Unlikely to continue",
                "Neutral",
                "Somewhat likely to continue",
                "Very likely to continue",
            ],
        ),
        Criterion(
            label="Spend intent",
            question="Would you want to pay after this initiative?",
            anchors=[
                "No intent to spend",
                "Prefer not to spend now",
                "Might spend depending on conditions",
                "Would spend with discounts or perks",
                "Eager to spend",
            ],
        ),
    ]
    templates = [
        PromptTemplate(
            name="LiveOps baseline",
            description="Default LiveOps evaluation prompt",
            content="Share a candid view on retention and monetization impact for players.",
        )
    ]
    for p in personas:
        db.add(p)
    for c in criteria:
        db.add(c)
    for t in templates:
        db.add(t)
    db.commit()
    return {"status": "seeded", "personas": len(personas), "criteria": len(criteria), "templates": len(templates)}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
