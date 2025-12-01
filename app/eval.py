from __future__ import annotations

import math
import random
from typing import Dict, Iterable, List, Sequence, Tuple

from .models import Criterion, HumanBenchmark, Result, Task


def normalize_distribution(values: Sequence[float]) -> List[float]:
    total = float(sum(values))
    if total <= 0:
        n = max(len(values), 1)
        return [1 / n for _ in range(n)]
    return [float(v) / total for v in values]


def expected_rating(distribution: Sequence[float]) -> float:
    if not distribution:
        return 0.0
    probs = normalize_distribution(distribution)
    return sum((idx + 1) * p for idx, p in enumerate(probs))


def ks_similarity(human: Sequence[float], synthetic: Sequence[float]) -> float:
    human_norm = normalize_distribution(human)
    synthetic_norm = normalize_distribution(synthetic)
    cumulative_h = []
    cumulative_s = []
    running_h = 0.0
    running_s = 0.0
    for h, s in zip(human_norm, synthetic_norm):
        running_h += h
        running_s += s
        cumulative_h.append(running_h)
        cumulative_s.append(running_s)
    max_diff = max(abs(h - s) for h, s in zip(cumulative_h, cumulative_s))
    return max(0.0, 1.0 - max_diff)


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) == 0:
        return 0.0
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    num = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    den_x = math.sqrt(sum((a - mean_x) ** 2 for a in x))
    den_y = math.sqrt(sum((b - mean_y) ** 2 for b in y))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def simulate_means(distribution: Sequence[float], sample_size: int, rng: random.Random) -> float:
    weights = normalize_distribution(distribution)
    outcomes = rng.choices(population=[1, 2, 3, 4, 5], weights=weights, k=sample_size)
    return sum(outcomes) / sample_size


def correlation_attainment(
    benchmarks: Sequence[HumanBenchmark],
    synthetic_means: Sequence[float],
    trials: int = 500,
    seed: int | None = None,
) -> Tuple[float, float]:
    if not benchmarks or len(benchmarks) != len(synthetic_means):
        return 0.0, 0.0
    rng = random.Random(seed)
    rho_samples: List[float] = []
    ceiling_samples: List[float] = []
    for _ in range(trials):
        human_draw = [simulate_means(b.distribution, b.sample_size, rng) for b in benchmarks]
        human_draw_control = [simulate_means(b.distribution, b.sample_size, rng) for b in benchmarks]
        corr_xy = pearson(human_draw, synthetic_means)
        corr_xx = pearson(human_draw, human_draw_control)
        rho_samples.append(corr_xy)
        ceiling_samples.append(corr_xx)
    mean_rho = sum(rho_samples) / len(rho_samples)
    mean_ceiling = sum(ceiling_samples) / len(ceiling_samples)
    attainment = (mean_rho / mean_ceiling) if mean_ceiling else 0.0
    return attainment, mean_ceiling


def aggregate_task_panels(
    task: Task,
    results: Sequence[Result],
    criteria: Dict[int, Criterion],
) -> Dict[str, Dict[str, object]]:
    panels: Dict[str, Dict[str, object]] = {}
    for result in results:
        criterion = criteria.get(result.criterion_id)
        if not criterion:
            continue
        bucket = panels.setdefault(
            criterion.label,
            {"criterion": criterion.label, "distributions": [], "ratings": []},
        )
        bucket["distributions"].append(result.distribution)
        bucket["ratings"].append(result.rating)
    aggregated: Dict[str, Dict[str, object]] = {}
    for label, bucket in panels.items():
        if not bucket["distributions"]:
            continue
        dist_len = len(bucket["distributions"][0])
        summed = [0.0 for _ in range(dist_len)]
        for dist in bucket["distributions"]:
            for idx, val in enumerate(normalize_distribution(dist)):
                summed[idx] += val
        averaged = [v / len(bucket["distributions"]) for v in summed]
        aggregated[label] = {
            "criterion": label,
            "distribution": averaged,
            "mean_rating": expected_rating(averaged),
            "sample_size": len(bucket["ratings"]),
        }
    return aggregated
