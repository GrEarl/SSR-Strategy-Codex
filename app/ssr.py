from __future__ import annotations

import math
import random
from typing import Dict, List, Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


DEFAULT_ANCHORS = [
    "I have no interest at all and see no reason to buy.",
    "Not very appealing, though I might consider under certain conditions.",
    "Neutral – it seems fine overall.",
    "Generally positive; would purchase if prompted or discounted.",
    "Extremely appealing and I actively want to purchase.",
]

GAME_OPS_ANCHORS = [
    "The live-ops plans feel weak and I would not keep playing.",
    "Some initiatives are interesting, but I would neither spend nor stay long term.",
    "I could keep playing, but my impression depends on future operations.",
    "Compelling enough that I would likely continue and consider spending.",
    "Very attractive—I would actively continue and pay.",
]


def normalize_text(text: str) -> str:
    cleaned = text.replace("\n", " ").strip()
    return cleaned or "(no text)"


def compute_distribution(text: str, anchors: Sequence[str], method: str = "tfidf") -> List[float]:
    reference = [normalize_text(t) for t in anchors]
    stimulus = normalize_text(text)
    if method == "uniform":
        return [round(1 / len(reference), 4) for _ in reference]

    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform(reference + [stimulus])
    ref_vectors = matrix[:-1]
    stimulus_vec = matrix[-1]
    sims = cosine_similarity(stimulus_vec, ref_vectors)[0]
    min_sim = min(sims)
    max_sim = max(sims)
    if math.isclose(max_sim, min_sim):
        return [round(1 / len(anchors), 4) for _ in anchors]
    normalized = [(s - min_sim) / (max_sim - min_sim) for s in sims]
    total = sum(normalized)
    if total == 0:
        return [round(1 / len(anchors), 4) for _ in anchors]
    return [round(v / total, 4) for v in normalized]


def distribution_to_rating(distribution: Sequence[float]) -> int:
    if not distribution:
        return 3
    return int(distribution.index(max(distribution)) + 1)


def synthesize_response(
    persona: dict,
    criterion_label: str,
    guidance: str | None,
    stimulus: str,
    operation_context: Dict[str, str] | None = None,
    template_text: str | None = None,
    run_seed: int | None = None,
) -> str:
    rng = random.Random(run_seed)
    demographic = f"{persona.get('age', '?')}-year-old {persona.get('gender', 'unknown')}"
    lead = rng.choice(
        [
            "From my point of view",
            "Intuitively",
            "Frankly",
            "As a player",
            "Based on my habits",
            "Considering well-being",
            "As a gamer",
            "From how I play social games",
        ]
    )
    opinion = rng.choice(
        [
            "it seems useful",
            "pricing will decide it",
            "I want to try it",
            "I’d weigh it carefully",
            "it has appeal",
            "it feels promising",
            "there are challenges",
            "sustained support seems key",
            "timing of releases will sway me",
        ]
    )
    guide_text = f" {guidance}" if guidance else ""
    context_lines: List[str] = []
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
    context_text = " | ".join(context_lines)
    template_clause = f" {template_text}" if template_text else ""
    return (
        f"{lead}, viewing this as a {demographic}. {stimulus} {guide_text}"
        f" {template_clause}"
        f" As a result, from the lens of {criterion_label} I feel {opinion}."
        f" Ops context: {context_text}".strip()
    )
