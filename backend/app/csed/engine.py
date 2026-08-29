"""
Top-level CSED + DPGR orchestration.

Order of operations matches the PS exactly:
    HARD CONSTRAINTS -> VALID SOLUTION SPACE -> SOFT OBJECTIVE OPTIMIZATION
search_placement() (hard constraints) is called for every candidate BEFORE dpgr.py
ever scores anything. Nothing here ever hands DPGR an unvalidated roadmap.

generate_roadmap() is a pure function of (curriculum, student, requested extras) --
no global state, same inputs always produce the same output, which is what "the core
result must be reproducible and verifiable" (PS Part 6.3) actually requires in code,
not just in a diagram.
"""
from .model import (Curriculum, StudentState, load_curriculum, load_student,
                     load_programme_requirement_cc_ids, load_career_relevance)
from .graph import check_cycles, compute_earliest_possible
from .search import search_placement, structurally_infeasible_nodes
from .selector import generate_pool_selections
from .dpgr import score_roadmap, rank_candidates
from .risk import compute_risk_flags


def _remaining_by_category(curriculum: Curriculum, student: StudentState, category: str):
    return [n for n in curriculum.nodes.values()
            if n.category == category and n.course_id not in student.passed_course_ids]


def _attempt(curriculum, student, mandatory_ids, de_pool, oe_pool, minor_ids,
             de_needed, oe_needed, relevance_by_cc, career_area_names,
             start_sem, end_sem, bounds, forced_cc_ids, max_de_candidates=12, max_oe_candidates=3):
    """Tries combinations of DE/OE pool selections (DE ranked by career relevance) on top of
    the fixed mandatory+minor+forced set. Returns list of (required_set, assignments, trace,
    de_selection, oe_selection) for every combination that search_placement validates."""
    excluded = forced_cc_ids | minor_ids
    de_selectable = [n for n in de_pool if n.id not in excluded]
    oe_selectable = [n for n in oe_pool if n.id not in excluded]

    de_relevance_scalar = {
        cc_id: sum(weights.get(tag, 0.0) for tag in career_area_names)
        for cc_id, weights in relevance_by_cc.items()
    }
    de_candidates = generate_pool_selections(de_selectable, de_needed, relevance=de_relevance_scalar,
                                              cap=max_de_candidates) if de_needed > 0 else [frozenset()]
    oe_candidates = generate_pool_selections(oe_selectable, oe_needed, relevance=None,
                                              cap=max_oe_candidates) if oe_needed > 0 else [frozenset()]

    results = []
    for de_sel in de_candidates:
        for oe_sel in oe_candidates:
            required = set(mandatory_ids) | set(minor_ids) | set(forced_cc_ids) | de_sel | oe_sel
            assignments, trace = search_placement(curriculum, student, required, start_sem, end_sem, bounds,
                                                    allow_summer=student.allow_summer)
            if assignments is not None:
                results.append((required, assignments, trace, de_sel, oe_sel))
    return results


def _score_all(results, curriculum, relevance_by_cc, career_area_names, standard_semesters):
    scored = []
    for required, assignments, trace, de_sel, oe_sel in results:
        total_sems = max(assignments.keys()) if assignments else standard_semesters
        s = score_roadmap(assignments, curriculum, de_sel, relevance_by_cc, career_area_names,
                           total_sems, standard_semesters)
        scored.append(((required, assignments, trace, de_sel, oe_sel), s))
    return rank_candidates(scored)


def generate_roadmap(student_id: int, forced_elective_codes=None, requested_semester_hints=None,
                      max_de_candidates=12):
    """
    forced_elective_codes: course codes the student explicitly wants included (e.g. a
        specific requested elective), on top of whatever their target programme requires.
    requested_semester_hints: {course_code: semester_number} -- used only to generate the
        "requested vs actual placement" explanation; never treated as a hard constraint.
    """
    forced_elective_codes = forced_elective_codes or []
    requested_semester_hints = requested_semester_hints or {}

    student = load_student(student_id)
    curriculum = load_curriculum(student.curriculum_version_id)
    check_cycles(curriculum)  # raises CycleError on corrupted data -- never silently ignored

    # ASSUMPTION (PS does not define this precisely): "current_semester" is the semester the
    # student is about to plan from, inclusive -- not "already irrevocably fixed". A semester
    # whose courses are all mandatory/fixed core naturally has nothing left to decide, so it
    # is scheduled trivially and simply doesn't appear as a noteworthy explanation; a semester
    # that still has open elective/requirement choices (e.g. Example 2's Sem5) is planned by
    # the engine like any other. This reconciles the PS's own three examples, which show the
    # "first interesting" semester, not always current_semester+1.
    start_sem = student.current_semester
    standard_end = curriculum.credit_rule.max_semesters_standard
    ext_end = curriculum.credit_rule.max_semesters_with_extension if student.willing_to_extend else None
    bounds = compute_earliest_possible(curriculum, student, start_sem)

    mandatory = {n.id for n in curriculum.nodes.values()
                 if n.category in ("CORE", "HSS") and n.course_id not in student.passed_course_ids}

    de_pool_all = _remaining_by_category(curriculum, student, "DE")
    oe_pool_all = _remaining_by_category(curriculum, student, "OE")

    forced_cc_ids = set()
    for code in forced_elective_codes:
        for n in curriculum.nodes.values():
            if n.code == code:
                forced_cc_ids.add(n.id)
    forced_credits = sum(curriculum.nodes[cc].credits for cc in forced_cc_ids)

    de_needed = max(0, curriculum.credit_rule.min_de_credits_total - forced_credits)
    oe_needed = curriculum.credit_rule.min_oe_credits_total

    relevance_by_cc = load_career_relevance(curriculum.curriculum_version_id)
    career_area_names = set(student.career_interest_tags)

    minor_ids_by_programme = {}
    for prog_id in student.target_programme_ids:
        minor_ids_by_programme[prog_id] = set(
            load_programme_requirement_cc_ids(prog_id, curriculum.curriculum_version_id)
        )
    all_minor_ids = set().union(*minor_ids_by_programme.values()) if minor_ids_by_programme else set()

    log = {"attempts": []}

    def try_tier(include_minor, end_sem, label):
        minor_ids = all_minor_ids if include_minor else set()
        results = _attempt(curriculum, student, mandatory, de_pool_all, oe_pool_all, minor_ids,
                            de_needed, oe_needed, relevance_by_cc, career_area_names,
                            start_sem, end_sem, bounds, forced_cc_ids, max_de_candidates=max_de_candidates)
        log["attempts"].append({"label": label, "include_minor": include_minor, "end_sem": end_sem,
                                 "n_candidates_found": len(results)})
        return results

    # Tier A: exact request, standard horizon
    tier_a = try_tier(include_minor=bool(all_minor_ids), end_sem=standard_end, label="A: requested @ standard")
    # Tier B: exact request, extended horizon (only if a target minor exists and student allows extension)
    tier_b = try_tier(include_minor=bool(all_minor_ids), end_sem=ext_end, label="B: requested @ extension") \
        if (not tier_a and all_minor_ids and ext_end) else []
    # Tier C: drop minor, standard horizon (the "alternative pathway" / fallback)
    tier_c = try_tier(include_minor=False, end_sem=standard_end, label="C: no-minor @ standard") \
        if all_minor_ids else []
    # Tier D: drop minor, extended horizon (last resort)
    tier_d = try_tier(include_minor=False, end_sem=ext_end, label="D: no-minor @ extension") \
        if (not tier_a and not tier_b and not tier_c and ext_end) else []

    def build_roadmap(results, status, adjustment, end_sem):
        scored = _score_all(results, curriculum, relevance_by_cc, career_area_names, standard_end)
        primary = scored[0]
        alternative = scored[1] if len(scored) > 1 else None
        primary_rendered = _render(primary, curriculum, requested_semester_hints)
        return {
            "status": status,
            "adjustment": adjustment,
            "requested_end_sem": end_sem,
            "primary": primary_rendered,
            "alternative": _render(alternative, curriculum, requested_semester_hints) if alternative else None,
            "n_valid_candidates_found": len(results),
            "risk_flags": compute_risk_flags(primary_rendered, curriculum, curriculum.credit_rule,
                                              status, adjustment),
            "engine_log": log,
        }

    if tier_a:
        # if a fallback/breadth alternative exists, surface it too even though the exact request succeeded
        alt_pool = tier_c if tier_c else []
        result = build_roadmap(tier_a, "FEASIBLE", None, standard_end)
        if alt_pool and not result["alternative"]:
            alt_scored = _score_all(alt_pool, curriculum, relevance_by_cc, career_area_names, standard_end)
            result["alternative"] = _render(alt_scored[0], curriculum, requested_semester_hints)
        # a fully valid plan can still diverge from an explicit requested-semester preference for
        # one course (PS Example 3: "Requested Plan Infeasible; Modified Plan Feasible") -- that is
        # its own adjustment category, distinct from dropping a requirement or needing extension.
        if result["primary"]["semester_shifts"]:
            result["status"] = "FEASIBLE_WITH_ADJUSTMENT"
            result["adjustment"] = "SEMESTER_SHIFT"
        return result

    if tier_b:
        result = build_roadmap(tier_b, "FEASIBLE_WITH_ADJUSTMENT", "DEGREE_EXTENSION", ext_end)
        if tier_c:
            alt_scored = _score_all(tier_c, curriculum, relevance_by_cc, career_area_names, standard_end)
            result["alternative"] = _render(alt_scored[0], curriculum, requested_semester_hints)
        else:
            result["alternative"] = None
        # explain WHY standard horizon failed, from tier_a's structural rejections
        blocking = []
        for req, *_ in [(mandatory | all_minor_ids | forced_cc_ids)]:
            pass
        never, exceeds = structurally_infeasible_nodes(
            curriculum, student, mandatory | all_minor_ids | forced_cc_ids, bounds, standard_end)
        result["why_standard_failed"] = [d for _, _, d in (never + exceeds)]
        return result

    if tier_c:
        adjustment = "REQUIREMENT_DROPPED"
        return build_roadmap(tier_c, "FEASIBLE_WITH_ADJUSTMENT", adjustment, standard_end)

    if tier_d:
        return build_roadmap(tier_d, "FEASIBLE_WITH_ADJUSTMENT", "DEGREE_EXTENSION+REQUIREMENT_DROPPED", ext_end)

    return {
        "status": "CURRENTLY_INFEASIBLE",
        "adjustment": None,
        "primary": None,
        "alternative": None,
        "n_valid_candidates_found": 0,
        "engine_log": log,
        "reason": "No valid roadmap exists even after dropping optional/target programme "
                  "requirements and applying the maximum allowed extension. Graduation itself "
                  "is at risk under current hard constraints.",
    }


def _render(scored_pair, curriculum, requested_semester_hints):
    (required, assignments, trace, de_sel, oe_sel), score = scored_pair
    semesters = {}
    for sem, cc_ids in sorted(assignments.items()):
        semesters[sem] = {
            "courses": [
                {"code": curriculum.nodes[cc].code, "title": curriculum.nodes[cc].title,
                 "category": curriculum.nodes[cc].category, "credits": curriculum.nodes[cc].credits}
                for cc in sorted(cc_ids, key=lambda c: curriculum.nodes[c].code)
            ],
            "total_credits": sum(curriculum.nodes[cc].credits for cc in cc_ids),
        }
    shifts = []
    for code, requested_sem in requested_semester_hints.items():
        actual_sem = next((s for s, info in semesters.items()
                            if any(c["code"] == code for c in info["courses"])), None)
        if actual_sem is not None and actual_sem != requested_sem:
            shifts.append({"code": code, "requested_semester": requested_sem, "actual_semester": actual_sem})
    return {"semesters": semesters, "score": score, "trace": trace, "semester_shifts": shifts}
