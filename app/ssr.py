from __future__ import annotations

import math
import os
import random
from typing import Dict, List, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


GAME_OPS_ANCHORS = [
    "この施策ではプレイを継続しない。",
    "やや魅力が足りず長くは続けない。",
    "どちらとも言えず、今後の運営次第で決める。",
    "わりと良いのでしばらくは続けたい。",
    "とても魅力的で積極的に遊び続けたい。",
]

SPEND_ANCHORS = [
    "全く課金する気はない。",
    "大幅割引などがない限り課金したくない。",
    "条件次第では少額なら課金してもよい。",
    "報酬が維持されるならパスやガチャに課金したい。",
    "早く進めるため積極的にプレミアム課金したい。",
]

# デフォルトはソーシャルゲーム運営評価向けのアンカーを採用する
DEFAULT_ANCHORS = GAME_OPS_ANCHORS

_EMBED_MODEL = None


def _get_embed_model() -> SentenceTransformer:
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        # 軽量かつ汎用の多言語対応モデルを採用
        _EMBED_MODEL = SentenceTransformer(os.getenv("SSR_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    return _EMBED_MODEL


def normalize_text(text: str) -> str:
    cleaned = text.replace("\n", " ").strip()
    return cleaned or "(no text)"


def compute_distribution(text: str, anchors: Sequence[str], method: str = "tfidf") -> List[float]:
    reference = [normalize_text(t) for t in anchors]
    stimulus = normalize_text(text)
    if method == "uniform":
        return [round(1 / len(reference), 4) for _ in reference]

    if method == "embed":
        model = _get_embed_model()
        emb = model.encode(reference + [stimulus], convert_to_numpy=True, normalize_embeddings=True)
        ref_vectors = emb[:-1]
        stim_vec = emb[-1]
        sims = np.dot(ref_vectors, stim_vec)
    else:  # tfidf
        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform(reference + [stimulus])
        ref_vectors = matrix[:-1]
        stimulus_vec = matrix[-1]
        sims = cosine_similarity(stimulus_vec, ref_vectors)[0]

    max_sim = max(sims) if len(sims) else 0.0
    exp_scores = [math.exp(s - max_sim) for s in sims]
    total = sum(exp_scores)
    if total == 0:
        return [round(1 / len(anchors), 4) for _ in anchors]
    return [round(v / total, 4) for v in exp_scores]


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
    seed_value = (run_seed or 0) + int(persona.get("id", 0))
    rng = random.Random(seed_value)
    anchors = SPEND_ANCHORS if "課金" in criterion_label else GAME_OPS_ANCHORS
    stance_idx = rng.randint(1, len(anchors))
    anchor_phrase = anchors[stance_idx - 1]
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
        f" Ops context: {context_text}. Likert stance clue: {anchor_phrase}"
        f" (rating seed {stance_idx}).".strip()
    )
