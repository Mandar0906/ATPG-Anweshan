"""
Deterministic risk-flag generation. Runs only over the FINAL validated roadmap plus the
curriculum's own uncertainty metadata (course_offering.is_offering_uncertain /
is_seat_cap_uncertain, seat_cap) -- never invented, never inferred from course titles.
"""


def compute_risk_flags(rendered_roadmap, curriculum, credit_rule, status, adjustment):
    flags = []
    if rendered_roadmap is None:
        return flags

    scheduled_codes = {c["code"]: (sem, c) for sem, info in rendered_roadmap["semesters"].items()
                        for c in info["courses"]}

    for code, (sem, c) in scheduled_codes.items():
        node = next((n for n in curriculum.nodes.values() if n.code == code), None)
        if node is None or node.offering is None:
            continue
        off = node.offering
        if off.is_seat_cap_uncertain or (off.seat_cap is not None):
            flags.append({
                "risk_type": "SEAT_LIMITED", "course_code": code, "semester": sem,
                "severity": "MEDIUM" if off.is_seat_cap_uncertain else "LOW",
                "detail": f"{code} has a seat cap of {off.seat_cap if off.seat_cap is not None else 'unknown'}"
                          f"{' (not confirmed by the department -- treat as tentative)' if off.is_seat_cap_uncertain else ''}."
                          f" This roadmap assumes a seat will be available; it is not guaranteed.",
            })
        if off.is_offering_uncertain:
            flags.append({
                "risk_type": "UNCERTAIN_OFFERING", "course_code": code, "semester": sem,
                "severity": "HIGH",
                "detail": f"{code}'s offering in semester {sem} is not confirmed for every batch/year "
                          f"({off.notes or 'see course_offering.notes'}). If it is not actually offered, "
                          f"this roadmap will need to be regenerated.",
            })

    for sem, info in rendered_roadmap["semesters"].items():
        if info["total_credits"] >= 0.9 * credit_rule.max_credits_per_semester:
            flags.append({
                "risk_type": "NEAR_CREDIT_LIMIT", "course_code": None, "semester": sem,
                "severity": "LOW",
                "detail": f"Semester {sem} is loaded to {info['total_credits']} of "
                          f"{credit_rule.max_credits_per_semester} allowed credits -- little room left to "
                          f"absorb a failed course or an added requirement without displacing something else.",
            })

    if adjustment and "EXTENSION" in adjustment:
        flags.append({
            "risk_type": "DEGREE_EXTENSION", "course_code": None, "semester": None,
            "severity": "HIGH",
            "detail": "This roadmap graduates beyond the standard 8 semesters. The extension ceiling "
                      "used by the engine is a placeholder pending confirmation from an official DOAA "
                      "policy document -- verify before presenting this plan as final.",
        })

    for shift in rendered_roadmap.get("semester_shifts", []):
        flags.append({
            "risk_type": "UNRESOLVED_PREREQ", "course_code": shift["code"], "semester": shift["actual_semester"],
            "severity": "MEDIUM",
            "detail": f"{shift['code']} could not be placed in the requested semester "
                      f"{shift['requested_semester']} due to an unresolved prerequisite chain; it was "
                      f"rescheduled to semester {shift['actual_semester']}.",
        })

    return flags
