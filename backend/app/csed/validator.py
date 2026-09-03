from .model import Curriculum, StudentState
from .graph import node_prereqs_satisfied

def validate_roadmap(roadmap, curriculum: Curriculum, student: StudentState, include_minor: bool, all_minor_ids: set, forced_elective_codes: list):
    errors = []
    if not roadmap:
        return errors

    placed_courses = {}
    for sem_str, info in roadmap["semesters"].items():
        sem = int(sem_str)
        max_credits = curriculum.credit_rule.max_credits_per_semester
        if student.max_credits_per_semester is not None:
            max_credits = min(max_credits, student.max_credits_per_semester)
            
        if info["total_credits"] > max_credits:
            errors.append(f"Load violation in semester {sem}: {info['total_credits']} exceeds max {max_credits}")

        for course in info["courses"]:
            code = course["code"]
            if code in placed_courses:
                errors.append(f"Course duplicated: {code}")
            placed_courses[code] = sem

    passed_codes = {n.code for n in curriculum.nodes.values() if n.course_id in student.passed_course_ids}
    satisfied_codes = {n.code for n in curriculum.nodes.values() if n.id in student.satisfied_slot_ids}
    for code in placed_courses:
        if code in passed_codes:
            errors.append(f"Course already completed: {code}")
        if code in satisfied_codes:
            errors.append(f"Course corresponds to an already satisfied slot: {code}")

    scheduled_by_earlier_sem = {}
    code_to_node = {n.code: n for n in curriculum.nodes.values()}

    for sem in sorted([int(s) for s in roadmap["semesters"].keys()]):
        info = roadmap["semesters"][str(sem)]
        current_sem_course_ids = []
        for course in info["courses"]:
            code = course["code"]
            node = code_to_node.get(code)
            if not node:
                errors.append(f"Unknown course {code}")
                continue
            
            current_sem_course_ids.append(node.course_id)
            satisfied = student.passed_course_ids | student.e_grade_course_ids | set(scheduled_by_earlier_sem.keys())
            if not node_prereqs_satisfied(node, satisfied):
                errors.append(f"Missing prerequisite for {code} in semester {sem}")
            
            if node.offering:
                if not node.offering.matches(sem, allow_summer=student.allow_summer):
                    errors.append(f"Known offering mismatch: {code} not offered in sem {sem}")
                    
        for cid in current_sem_course_ids:
            scheduled_by_earlier_sem[cid] = sem

    for node in curriculum.nodes.values():
        if node.category in ("CORE", "HSS"):
            if node.course_id not in student.passed_course_ids and node.id not in student.satisfied_slot_ids:
                if node.code not in placed_courses:
                    errors.append(f"Requirement left incomplete: {node.code}")

    placed_de = sum(c["credits"] for sem in roadmap["semesters"].values() for c in sem["courses"] if c["category"] == "DE")
    placed_oe = sum(c["credits"] for sem in roadmap["semesters"].values() for c in sem["courses"] if c["category"] == "OE")
    
    passed_de = sum(n.credits for n in curriculum.nodes.values() if n.category == "DE" and (n.course_id in student.passed_course_ids or n.id in student.satisfied_slot_ids))
    passed_oe = sum(n.credits for n in curriculum.nodes.values() if n.category == "OE" and (n.course_id in student.passed_course_ids or n.id in student.satisfied_slot_ids))
    
    forced_credits = sum(n.credits for n in curriculum.nodes.values() if n.code in forced_elective_codes)
    
    if placed_de + passed_de + forced_credits < curriculum.credit_rule.min_de_credits_total:
        errors.append(f"Requirement left incomplete: DE credits short")
        
    if placed_oe + passed_oe < curriculum.credit_rule.min_oe_credits_total:
        errors.append(f"Requirement left incomplete: OE credits short")

    for code in forced_elective_codes:
        if code not in placed_courses and code not in passed_codes and code not in satisfied_codes:
            errors.append(f"Forced elective {code} was not placed")

    if include_minor:
        for mid in all_minor_ids:
            node = curriculum.nodes[mid]
            if node.course_id not in student.passed_course_ids and node.id not in student.satisfied_slot_ids:
                if node.code not in placed_courses:
                    errors.append(f"Minor requirement violation: {node.code} not placed")

    return errors
