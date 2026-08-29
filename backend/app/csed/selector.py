"""
Enumerates candidate elective/minor "requirement sets" to hand to search.py.

This is deliberately separate from search.py: selector.py decides WHICH courses a
candidate roadmap should attempt to include (the DPGR-relevant choice), search.py
only ever answers WHEN/whether a fixed set can be scheduled. Nothing here ever
returns a result to the caller directly -- every candidate must still pass
search_placement's hard-constraint check before it is considered a valid roadmap.
"""
from itertools import combinations
import math


def generate_pool_selections(pool_nodes, min_credits_threshold, relevance=None, max_extra=2, cap=40):
    """
    pool_nodes: list[CurriculumCourse] all sharing one category (e.g. all DE nodes not yet passed).
    min_credits_threshold: remaining credits needed from this pool (already-earned credits
        subtracted by the caller).
    relevance: optional {cc_id: score} used only to ORDER candidates so the most promising
        (highest total relevance) are tried -- and therefore found -- first; never used to
        exclude a combination.
    max_extra: how many courses beyond the minimum count may be included, to allow
        "maximize relevant electives" style requests real headroom rather than stopping at
        the bare graduation minimum.
    cap: hard cap on how many candidate combinations are returned, to bound search cost.

    Returns a list of frozenset(cc_id) candidates, largest-relevance-first, always including
    the empty set first if the threshold is already <= 0.
    """
    if min_credits_threshold <= 0:
        return [frozenset()]
    if not pool_nodes:
        return []

    avg_credit = sum(n.credits for n in pool_nodes) / len(pool_nodes)
    min_size = max(1, math.ceil(min_credits_threshold / max(pool_nodes, key=lambda n: n.credits).credits))
    # be generous: scan a small range of sizes around the theoretical minimum
    size_lo = max(1, min_size)
    size_hi = min(len(pool_nodes), min_size + max_extra)

    def score(combo):
        if relevance is None:
            return 0.0
        return sum(relevance.get(n.id, 0.0) for n in combo)

    candidates = []
    for k in range(size_lo, size_hi + 1):
        for combo in combinations(pool_nodes, k):
            if sum(n.credits for n in combo) < min_credits_threshold:
                continue
            candidates.append(combo)

    candidates.sort(key=lambda combo: (-score(combo), sum(n.credits for n in combo),
                                        tuple(n.code for n in combo)))
    seen = set()
    out = []
    for combo in candidates:
        key = frozenset(n.id for n in combo)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= cap:
            break
    return out
