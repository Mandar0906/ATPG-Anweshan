"""
In-memory data model + Postgres loader for the CSED engine.

Deliberately decoupled from the DB after load: everything downstream (graph.py,
search.py, selector.py, dpgr.py) operates on these plain dataclasses, which is what
makes the core scheduler a pure function of (curriculum, student state, preferences)
-- no hidden I/O, fully deterministic, easy to unit test and to prove reproducible.
"""
from dataclasses import dataclass, field
from typing import Optional
import os
import psycopg2
import psycopg2.extras


def get_conn():
    return psycopg2.connect(
        host=os.environ.get("APTG_DB_HOST", "localhost"),
        port=os.environ.get("APTG_DB_PORT", "5432"),
        dbname=os.environ.get("APTG_DB_NAME", "aptg"),
        user=os.environ.get("APTG_DB_USER", "postgres"),
        password=os.environ.get("APTG_DB_PASSWORD", "postgres"),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


@dataclass
class Offering:
    semester_parity: str          # 'ODD' | 'EVEN' | 'BOTH' | 'SUMMER'
    seat_cap: Optional[int]
    is_offering_uncertain: bool
    is_seat_cap_uncertain: bool
    notes: Optional[str]

    def matches(self, semester_number: int, allow_summer: bool = False) -> bool:
        parity = "ODD" if semester_number % 2 == 1 else "EVEN"
        if self.semester_parity == "SUMMER":
            return allow_summer
        if self.semester_parity == "BOTH":
            return True
        return self.semester_parity == parity


@dataclass
class PrereqGroup:
    id: int
    logic: str                     # 'AND' | 'OR'
    prereq_course_ids: list        # list[int] -- global course.id
    is_illustrative: bool


@dataclass
class CurriculumCourse:
    id: int                        # curriculum_course.id -- the DAG node identity
    course_id: int
    code: str
    title: str
    category: str                  # CORE | DE | OE | HSS | MINOR_BASKET | UGP
    credits: int
    nominal_semester: Optional[int]
    offering: Optional[Offering]
    prereq_groups: list = field(default_factory=list)   # list[PrereqGroup]


@dataclass
class CreditRule:
    min_credits_per_semester: int
    max_credits_per_semester: int
    min_core_credits_total: int
    min_de_credits_total: int
    min_oe_credits_total: int
    max_semesters_standard: int
    max_semesters_with_extension: Optional[int]


@dataclass
class Curriculum:
    curriculum_version_id: int
    department_code: str
    batch_year: int
    nodes: dict                    # curriculum_course_id -> CurriculumCourse
    course_id_to_cc_id: dict       # global course_id -> curriculum_course_id (within this version)
    credit_rule: CreditRule


@dataclass
class StudentState:
    id: int
    name: str
    current_semester: int
    cpi: float
    curriculum_version_id: int
    passed_course_ids: set          # global course_id, grade_status = PASSED
    failed_course_ids: set          # grade_status = FAILED (still owed)
    in_progress_course_ids: set
    e_grade_course_ids: set
    satisfied_slot_ids: set
    target_programme_ids: list
    declared_programme_ids: list
    max_credits_per_semester: Optional[int]
    allow_summer: bool
    willing_to_extend: bool
    career_interest_tags: list


def load_curriculum(cv_id: int) -> Curriculum:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        select cv.id as cv_id, d.code as dept_code, cv.batch_year
        from curriculum_version cv join department d on d.id = cv.department_id
        where cv.id = %s
    """, (cv_id,))
    meta = cur.fetchone()

    cur.execute("""
        select id, min_credits_per_semester, max_credits_per_semester,
               min_core_credits_total, min_de_credits_total, min_oe_credits_total,
               max_semesters_standard, max_semesters_with_extension
        from credit_rule where curriculum_version_id = %s
    """, (cv_id,))
    cr = cur.fetchone()
    credit_rule = CreditRule(
        min_credits_per_semester=cr["min_credits_per_semester"],
        max_credits_per_semester=cr["max_credits_per_semester"],
        min_core_credits_total=cr["min_core_credits_total"],
        min_de_credits_total=cr["min_de_credits_total"],
        min_oe_credits_total=cr["min_oe_credits_total"],
        max_semesters_standard=cr["max_semesters_standard"],
        max_semesters_with_extension=cr["max_semesters_with_extension"],
    )

    cur.execute("""
        select cc.id as cc_id, cc.course_id, c.code, c.title, cc.category, cc.credits, cc.nominal_semester
        from curriculum_course cc join course c on c.id = cc.course_id
        where cc.curriculum_version_id = %s
    """, (cv_id,))
    nodes = {}
    course_id_to_cc_id = {}
    for row in cur.fetchall():
        nodes[row["cc_id"]] = CurriculumCourse(
            id=row["cc_id"], course_id=row["course_id"], code=row["code"], title=row["title"],
            category=row["category"], credits=row["credits"], nominal_semester=row["nominal_semester"],
            offering=None, prereq_groups=[],
        )
        course_id_to_cc_id[row["course_id"]] = row["cc_id"]

    cur.execute("""
        select course_id, semester_parity, seat_cap, is_offering_uncertain, is_seat_cap_uncertain, notes
        from course_offering where curriculum_version_id = %s
    """, (cv_id,))
    for row in cur.fetchall():
        cc_id = course_id_to_cc_id.get(row["course_id"])
        if cc_id is None:
            continue
        nodes[cc_id].offering = Offering(
            semester_parity=row["semester_parity"], seat_cap=row["seat_cap"],
            is_offering_uncertain=row["is_offering_uncertain"],
            is_seat_cap_uncertain=row["is_seat_cap_uncertain"], notes=row["notes"],
        )

    cur.execute("""
        select pg.id as group_id, pg.curriculum_course_id, pg.logic, pg.is_illustrative, pe.prerequisite_course_id
        from prerequisite_group pg join prerequisite_edge pe on pe.group_id = pg.id
        where pg.curriculum_course_id in (select id from curriculum_course where curriculum_version_id = %s)
        order by pg.id
    """, (cv_id,))
    groups = {}
    for row in cur.fetchall():
        gid = row["group_id"]
        if gid not in groups:
            groups[gid] = PrereqGroup(id=gid, logic=row["logic"], prereq_course_ids=[],
                                       is_illustrative=row["is_illustrative"])
            nodes[row["curriculum_course_id"]].prereq_groups.append(groups[gid])
        groups[gid].prereq_course_ids.append(row["prerequisite_course_id"])

    conn.close()
    return Curriculum(
        curriculum_version_id=cv_id, department_code=meta["dept_code"], batch_year=meta["batch_year"],
        nodes=nodes, course_id_to_cc_id=course_id_to_cc_id, credit_rule=credit_rule,
    )


def load_student(student_id: int) -> StudentState:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select * from student where id = %s", (student_id,))
    s = cur.fetchone()

    cur.execute("select course_id, grade_status from student_completed_course where student_id = %s", (student_id,))
    passed, failed, in_progress, e_grade = set(), set(), set(), set()
    for row in cur.fetchall():
        if row["grade_status"] == "PASSED":
            passed.add(row["course_id"])
        elif row["grade_status"] == "FAILED":
            failed.add(row["course_id"])
        elif row["grade_status"] == "E_GRADE":
            e_grade.add(row["course_id"])
        else:
            in_progress.add(row["course_id"])

    cur.execute("select curriculum_course_id from student_satisfied_slot where student_id = %s", (student_id,))
    satisfied_slots = {row["curriculum_course_id"] for row in cur.fetchall()}

    cur.execute("select programme_id, status from student_declared_programme where student_id = %s", (student_id,))
    target, declared = [], []
    for row in cur.fetchall():
        (target if row["status"] == "TARGET" else declared).append(row["programme_id"])

    cur.execute("select * from student_preference where student_id = %s", (student_id,))
    pref = cur.fetchone() or {}

    conn.close()
    return StudentState(
        id=s["id"], name=s["name"], current_semester=s["current_semester"], cpi=float(s["cpi"]),
        curriculum_version_id=s["curriculum_version_id"],
        passed_course_ids=passed, failed_course_ids=failed, in_progress_course_ids=in_progress,
        e_grade_course_ids=e_grade, satisfied_slot_ids=satisfied_slots,
        target_programme_ids=target, declared_programme_ids=declared,
        max_credits_per_semester=pref.get("max_credits_per_semester"),
        allow_summer=pref.get("allow_summer", False),
        willing_to_extend=pref.get("willing_to_extend", False),
        career_interest_tags=pref.get("career_interest_tags") or [],
    )


def load_programme_requirement_cc_ids(programme_id: int, cv_id: int) -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        select curriculum_course_id from programme_requirement
        where programme_id = %s and curriculum_version_id = %s and curriculum_course_id is not null
    """, (programme_id, cv_id))
    ids = [row["curriculum_course_id"] for row in cur.fetchall()]
    conn.close()
    return ids


def load_career_relevance(cv_id: int) -> dict:
    """Returns {curriculum_course_id: {career_interest_area_name: weight}}."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        select ccr.curriculum_course_id, cia.name, ccr.relevance_weight
        from course_career_relevance ccr
        join career_interest_area cia on cia.id = ccr.career_interest_area_id
        join curriculum_course cc on cc.id = ccr.curriculum_course_id
        where cc.curriculum_version_id = %s
    """, (cv_id,))
    out = {}
    for row in cur.fetchall():
        out.setdefault(row["curriculum_course_id"], {})[row["name"]] = float(row["relevance_weight"])
    conn.close()
    return out
