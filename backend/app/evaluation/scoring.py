"""Named metrics with explicit zero-relevance and empty-set behavior."""
from statistics import median


def retrieval_case(ranked: list[str], relevant: set[str], forbidden: set[str], k: int = 5) -> dict:
    top = ranked[:k]
    first = next((i + 1 for i, identifier in enumerate(top) if identifier in relevant), None)
    return {
        'hit_at_5': int(first is not None) if relevant else None,
        'recall_at_5': round(len(set(top) & relevant) / len(relevant), 4) if relevant else None,
        'reciprocal_rank_at_5': round(1 / first, 4) if first else (0.0 if relevant else None),
        'forbidden_exposure_count': sum(identifier in forbidden for identifier in ranked),
        'expected_empty': (len(ranked) == 0) if not relevant else None,
        'returned_count': len(ranked),
    }


def aggregate_retrieval(cases: list[dict]) -> dict:
    labelled = [item for item in cases if item['hit_at_5'] is not None]
    return {
        'status': 'measured',
        'labelled_positive_queries': len(labelled),
        'hit_at_5': round(sum(item['hit_at_5'] for item in labelled) / len(labelled), 4)
                    if labelled else None,
        'mrr_at_5': round(sum(item['reciprocal_rank_at_5'] for item in labelled) / len(labelled), 4)
                    if labelled else None,
        'mean_recall_at_5': round(sum(item['recall_at_5'] for item in labelled) / len(labelled), 4)
                            if labelled else None,
        'forbidden_exposure_count': sum(item['forbidden_exposure_count'] for item in cases),
        'negative_queries_empty': all(item['expected_empty'] for item in cases
                                      if item['expected_empty'] is not None),
    }


def latency_summary(samples: list[float]) -> dict:
    return {'count': len(samples), 'median_ms': round(median(samples), 3) if samples else None,
            'max_ms': round(max(samples), 3) if samples else None}
