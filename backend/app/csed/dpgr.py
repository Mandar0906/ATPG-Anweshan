"""
DPGR: Dynamic Personalization & Graph Routing -- the optimization layer.

Operates ONLY on roadmaps that have already passed search_placement's hard-constraint
check (see engine.py). Never invoked on, and never capable of producing, an invalid
roadmap -- it can only choose among validated candidates.

Objective (documented, not a black box): maximize career-interest alignment of chosen
electives, minimize inter-semester workload imbalance, and heavily penalize degree
extension (only ever chosen when no non-extended valid roadmap exists at all -- that
gating happens in engine.py, this score is what then ranks WITHIN a feasibility tier).
"""
import statistics


def relevance_score(chosen_cc_ids, relevance_by_cc_id, tag_to_area_name):
    """Sum of relevance weights for the student's declared career interest area(s)
    across whichever pool courses were chosen. Only areas the student actually stated
    (career_interest_tags, mapped via course_career_relevance -- never a raw keyword
    match against course titles) contribute."""
    total = 0.0
    for cc_id in chosen_cc_ids:
        weights = relevance_by_cc_id.get(cc_id, {})
        for tag in tag_to_area_name:
            total += weights.get(tag, 0.0)
    return total


def workload_imbalance_penalty(assignments: dict):
    totals = [sum(1 for _ in cc_ids) for cc_ids in assignments.values()]  # placeholder, replaced below
    return 0.0


def workload_imbalance_penalty_credits(assignments: dict, curriculum):
    per_sem_credits = [
        sum(curriculum.nodes[cc_id].credits for cc_id in cc_ids)
        for cc_ids in assignments.values()
    ]
    if len(per_sem_credits) < 2:
        return 0.0
    return statistics.pstdev(per_sem_credits)


def score_roadmap(assignments, curriculum, chosen_elective_cc_ids, relevance_by_cc_id,
                   career_tags, total_semesters_used, standard_semesters):
    career = relevance_score(chosen_elective_cc_ids, relevance_by_cc_id, career_tags)
    imbalance = workload_imbalance_penalty_credits(assignments, curriculum)
    extension_penalty = 25.0 * max(0, total_semesters_used - standard_semesters)
    score = (10.0 * career) - (0.5 * imbalance) - extension_penalty
    return {
        "score": round(score, 3),
        "career_alignment": round(career, 3),
        "workload_imbalance_stdev": round(imbalance, 3),
        "extension_penalty": extension_penalty,
        "total_semesters_used": total_semesters_used,
    }


def rank_candidates(scored_candidates):
    """scored_candidates: list of (candidate_dict, score_dict). Returns sorted
    best-first, stable on score then fewer semesters then career_alignment desc."""
    return sorted(
        scored_candidates,
        key=lambda pair: (-pair[1]["score"], pair[1]["total_semesters_used"], -pair[1]["career_alignment"]),
    )
