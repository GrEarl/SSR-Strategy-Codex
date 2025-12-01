from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, Session, SQLModel, create_engine, select


DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Persona(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    age: int
    gender: str
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Criterion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str
    question: str
    anchors: List[str] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HumanBenchmark(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str
    session_label: Optional[str] = None
    criterion_label: str
    distribution: List[float] = Field(sa_column=Column(JSON))
    sample_size: int = 100
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PromptTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    stimulus_text: Optional[str] = None
    image_name: Optional[str] = None
    image_data: Optional[str] = None
    persona_ids: List[int] = Field(sa_column=Column(JSON))
    criterion_ids: List[int] = Field(sa_column=Column(JSON))
    guidance: Optional[str] = None
    session_label: Optional[str] = None
    operation_context: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    prompt_template_id: Optional[int] = Field(default=None, foreign_key="prompttemplate.id")
    similarity_method: str = Field(default="tfidf")
    run_seed: Optional[int] = None
    status: str = Field(default="pending")
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Result(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id")
    persona_id: int = Field(foreign_key="persona.id")
    criterion_id: int = Field(foreign_key="criterion.id")
    summary: str
    distribution: List[float] = Field(sa_column=Column(JSON))
    rating: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def get_persona_map(session: Session, persona_ids: List[int]) -> List[Persona]:
    statement = select(Persona).where(Persona.id.in_(persona_ids))
    return list(session.exec(statement).all())


def get_criteria_map(session: Session, criterion_ids: List[int]) -> List[Criterion]:
    statement = select(Criterion).where(Criterion.id.in_(criterion_ids))
    return list(session.exec(statement).all())


def get_prompt_template(session: Session, template_id: Optional[int]) -> Optional[PromptTemplate]:
    if template_id is None:
        return None
    return session.get(PromptTemplate, template_id)
