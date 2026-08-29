"""
CSED backtracking search core: given a fixed set of required nodes (mandatory
graduation requirements + whatever elective/minor pool selection is being tried),
find a semester-by-semester placement that satisfies every hard constraint, or
prove none exists within the given horizon.

This module never decides WHICH electives to attempt (that's selector.py) and never
ranks results (that's dpgr.py) -- it only answers "can this exact required set be
scheduled between start_sem and end_sem", which is what keeps validation and
optimization cleanly separated per the PS's required ordering.
"""
from itertools import combinations
from .model import Curriculum, StudentState
from .graph import node_prereqs_satisfied, compute_earliest_possible

MAX_SEARCH_CALLS = 200_000


class SearchBudgetExceeded(Exception):
    pass


def structurally_infeasible_nodes(curriculum: Curriculum, student: StudentState,
                                   required_cc_ids: set, bounds: dict, end_sem: int):
    """Nodes that can never be scheduled at all (earliest_complete is None), and nodes
    that could be scheduled in principle but not within end_sem. Returns two lists of
    (cc_id, reason_code, detail)."""
    never = []
    exceeds_horizon = []
    for cc_id in required_cc_ids:
        node = curriculum.nodes[cc_id]
        if node.course_id in student.passed_course_ids:
            continue
        ee, ec = bounds[cc_id]
        if ec is None:
            never.append((cc_id, "NO_VALID_SEMESTER",
                          f"{node.code}: no offering pattern + prerequisite-completion combination "
                          f"exists that would ever make this course eligible and offered."))
        elif ec > end_sem:
            exceeds_horizon.append((cc_id, "EXCEEDS_HORIZON",
                                     f"{node.code}: earliest possible completion is semester {ec}, "
                                     f"which exceeds the {end_sem}-semester horizon being evaluated."))
    return never, exceeds_horizon


def _credit_capped_subsets(eligible_nodes, max_credits):
    """All subsets of eligible_nodes whose total credits fit under max_credits, yielded
    largest-total-credits-first (then largest-count, then deterministic by code) so the
    search tries to load each semester as full as possible before backtracking."""
    n = len(eligible_nodes)
    all_subsets = []
    for k in range(n, -1, -1):
        for combo in combinations(sorted(eligible_nodes, key=lambda nd: nd.code), k):
            total = sum(c.credits for c in combo)
            if total <= max_credits:
                all_subsets.append(combo)
    # stable sort: highest credit total first, ties by count then by code tuple
    all_subsets.sort(key=lambda combo: (-sum(c.credits for c in combo), -len(combo),
                                         tuple(c.code for c in combo)))
    return all_subsets


def search_placement(curriculum: Curriculum, student: StudentState, required_cc_ids: set,
                      start_sem: int, end_sem: int, bounds: dict, allow_summer: bool = False):
    """
    Returns (assignments, trace) on success, where assignments = {semester_number: [cc_id,...]}
    covering exactly required_cc_ids (nodes already PASSED are excluded). Returns (None, trace)
    if no valid placement exists within [start_sem, end_sem].
    """
    trace = []
    never, exceeds = structurally_infeasible_nodes(curriculum, student, required_cc_ids, bounds, end_sem)
    for cc_id, code, detail in never + exceeds:
        trace.append({"decision_type": "REJECTED", "cc_id": cc_id, "reason_code": code, "detail": detail})
    if never or exceeds:
        return None, trace

    to_place = {cc_id for cc_id in required_cc_ids if curriculum.nodes[cc_id].course_id not in student.passed_course_ids}
    max_credits = curriculum.credit_rule.max_credits_per_semester
    if student.max_credits_per_semester is not None:
        max_credits = min(max_credits, student.max_credits_per_semester)

    call_count = {"n": 0}

    def satisfied_course_ids(scheduled_by_earlier_sem: dict):
        return student.passed_course_ids | set(scheduled_by_earlier_sem.keys())

    def recurse(sem, remaining, scheduled_completion, assignments):
        call_count["n"] += 1
        if call_count["n"] > MAX_SEARCH_CALLS:
            raise SearchBudgetExceeded()
        if not remaining:
            return dict(assignments)
        if sem > end_sem:
            return None

        already_satisfied = satisfied_course_ids(scheduled_completion)
        # ASSUMPTION (not stated in the PS, adopted as a reasonable default representing normal
        # cohort-paced progression): a course cannot be taken before its curriculum's nominal
        # semester, even if its prerequisites are already satisfied. Courses with no nominal
        # semester (electives/minor-basket courses) are unaffected.
        eligible = [
            curriculum.nodes[cc_id] for cc_id in remaining
            if node_prereqs_satisfied(curriculum.nodes[cc_id], already_satisfied)
            and curriculum.nodes[cc_id].offering is not None
            and curriculum.nodes[cc_id].offering.matches(sem, allow_summer=allow_summer)
            and (curriculum.nodes[cc_id].nominal_semester is None
                 or sem >= curriculum.nodes[cc_id].nominal_semester)
        ]
        if not eligible:
            # nothing placeable this semester; move on (e.g. an odd-only course in an even semester)
            return recurse(sem + 1, remaining, scheduled_completion, assignments)

        for subset in _credit_capped_subsets(eligible, max_credits):
            chosen_ids = {c.id for c in subset}
            new_remaining = remaining - chosen_ids
            new_completion = dict(scheduled_completion)
            for c in subset:
                new_completion[c.course_id] = sem
            assignments[sem] = [c.id for c in subset]
            result = recurse(sem + 1, new_remaining, new_completion, assignments)
            if result is not None:
                return result
            del assignments[sem]
        return None

    try:
        result = recurse(start_sem, to_place, {}, {})
    except SearchBudgetExceeded:
        trace.append({"decision_type": "REJECTED", "cc_id": None, "reason_code": "SEARCH_BUDGET_EXCEEDED",
                      "detail": "Search exceeded its call budget; treated as infeasible for this horizon."})
        return None, trace

    if result is None:
        trace.append({"decision_type": "REJECTED", "cc_id": None, "reason_code": "NO_COMBINATION_FOUND",
                      "detail": f"No valid placement of the required course set exists within "
                                f"semesters {start_sem}-{end_sem} given credit and slot constraints."})
        return None, trace

    for sem, cc_ids in result.items():
        for cc_id in cc_ids:
            node = curriculum.nodes[cc_id]
            trace.append({
                "decision_type": "PLACED", "cc_id": cc_id, "semester": sem,
                "reason_code": "SCHEDULED",
                "detail": f"{node.code} placed in semester {sem}: prerequisites satisfied, "
                          f"offered ({node.offering.semester_parity}), within credit limit.",
            })
    return result, trace
