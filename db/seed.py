"""
APTG demo seed data.

Sourcing notes (kept here, not just in prose docs, so the provenance travels with the data):
  - Department/course codes, per-semester credits, and Core/DE/OE/HSS categorization for
    ME, AE, MSE are drawn from the official DOAA "Jan-25" curriculum templates:
      https://iitk.ac.in/doaa/data/template/ME-template.pdf
      https://iitk.ac.in/doaa/data/template/AE-template.pdf
      https://iitk.ac.in/doaa/data/template/MSE-template.pdf
    The demo uses a *consolidated subset* of each template (not every listed row) to keep the
    reference dataset legible; codes/credits kept for included courses are as fetched.
  - PREREQUISITE EDGES ARE ILLUSTRATIVE. The official templates do not publish a prerequisite
    registry (confirmed by inspection: MSE's template states none is provided; AE's template
    contains exactly one explicit prerequisite note, for AE341<-AE311). Edges below were
    authored by the team to produce a structurally sensible DAG for demonstration and are
    flagged prerequisite_group.is_illustrative = TRUE. They are NOT sourced from an official
    IITK prerequisite database and must not be presented to judges as verified institutional
    policy -- the AFR states this explicitly.
  - max_semesters_with_extension = 9 is a PLACEHOLDER pending confirmation of an actual DOAA
    extension policy. It exists so the engine has a bound to search against; generated
    explanations say "your allowed extension", never "IITK policy allows".
  - The three seeded students reproduce PS Examples 1, 2, 3 exactly (batch, department,
    semester, CPI, completion state, preferences) so the CSED/DPGR pipeline can be validated
    against the PS's own expected reasoning.
  - Modeling rule (explicit assumption): a prerequisite must be completed in a strictly EARLIER
    semester than the course that requires it -- concurrent enrollment does not satisfy a
    prerequisite.
"""
import os
import psycopg2

conn = psycopg2.connect(
    host=os.environ.get("APTG_DB_HOST", "localhost"),
    port=os.environ.get("APTG_DB_PORT", "5432"),
    dbname=os.environ.get("APTG_DB_NAME", "aptg"),
    user=os.environ.get("APTG_DB_USER", "postgres"),
    password=os.environ.get("APTG_DB_PASSWORD", "postgres"),
)
conn.autocommit = False
cur = conn.cursor()

# Idempotency guard: on container restart the DB volume persists, so re-running this script
# would otherwise crash on unique-constraint violations. Skip cleanly if already seeded.
cur.execute("select count(*) from department")
if cur.fetchone()[0] > 0:
    print("Seed skipped: department table is not empty (already seeded).")
    cur.close()
    conn.close()
    raise SystemExit(0)


def insert(table, **fields):
    cols = list(fields.keys())
    vals = [fields[c] for c in cols]
    placeholders = ",".join(["%s"] * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) RETURNING id"
    cur.execute(sql, vals)
    return cur.fetchone()[0]


def insert_plain(table, **fields):
    cols = list(fields.keys())
    vals = [fields[c] for c in cols]
    placeholders = ",".join(["%s"] * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    cur.execute(sql, vals)


def get_or_create_course(code, title, credits):
    cur.execute("SELECT id FROM course WHERE code=%s", (code,))
    row = cur.fetchone()
    if row:
        return row[0]
    return insert("course", code=code, title=title, default_credits=credits)


def curriculum_course(cv_id, course_id, category, credits, nominal_sem):
    return insert(
        "curriculum_course",
        curriculum_version_id=cv_id,
        course_id=course_id,
        category=category,
        credits=credits,
        nominal_semester=nominal_sem,
    )


def offering(cv_id, course_id, parity, seat_cap=None, off_unc=False, seat_unc=False, notes=None):
    insert(
        "course_offering",
        curriculum_version_id=cv_id,
        course_id=course_id,
        semester_parity=parity,
        seat_cap=seat_cap,
        is_offering_uncertain=off_unc,
        is_seat_cap_uncertain=seat_unc,
        notes=notes,
    )


def prereq(curriculum_course_id, prereq_course_ids, logic="AND", illustrative=True):
    gid = insert(
        "prerequisite_group",
        curriculum_course_id=curriculum_course_id,
        logic=logic,
        is_illustrative=illustrative,
    )
    for pc in prereq_course_ids:
        insert("prerequisite_edge", group_id=gid, prerequisite_course_id=pc)
    return gid


SRC = "DOAA Jan-25 template (iitk.ac.in/doaa/data/template); consolidated subset, see seed.py docstring"

# ---------------------------------------------------------------------------
# Departments + curriculum versions
# ---------------------------------------------------------------------------
dept_me = insert("department", code="ME", name="Mechanical Engineering")
dept_ae = insert("department", code="AE", name="Aerospace Engineering")
dept_mse = insert("department", code="MSE", name="Materials Science and Engineering")

cv_me_y24 = insert("curriculum_version", department_id=dept_me, batch_year=2024, source_note=SRC)
cv_ae_y23 = insert("curriculum_version", department_id=dept_ae, batch_year=2023, source_note=SRC)
cv_mse_y24 = insert(
    "curriculum_version",
    department_id=dept_mse,
    batch_year=2024,
    source_note=SRC + "; MSE template states applicability 'as per new UGARC implemented from Y22 onward'",
)

for cv, mx in ((cv_me_y24, 50), (cv_ae_y23, 55), (cv_mse_y24, 55)):
    insert(
        "credit_rule",
        curriculum_version_id=cv,
        min_credits_per_semester=30,
        max_credits_per_semester=mx,
        min_core_credits_total=90,
        min_de_credits_total=18,
        min_oe_credits_total=27,
        max_semesters_standard=8,
        max_semesters_with_extension=9,  # PLACEHOLDER, see docstring
    )

# ---------------------------------------------------------------------------
# Shared first-year institute courses (Sem 1-2)
# ---------------------------------------------------------------------------
shared_courses = [
    ("MTH101", "Calculus", 6, 1),
    ("PHY101", "Physics I", 11, 1),
    ("CHM101", "Chemistry", 4, 1),
    ("TA101", "Workshop / Technical Arts", 9, 1),
    ("MTH102", "Differential Equations", 6, 2),
    ("PHY102", "Physics II", 11, 2),
    ("ESC101", "Fundamentals of Computing", 7, 2),
]
shared_ids = {}
for code, title, credits, sem in shared_courses:
    cid = get_or_create_course(code, title, credits)
    shared_ids[code] = cid
    for cv in (cv_me_y24, cv_ae_y23, cv_mse_y24):
        curriculum_course(cv, cid, "CORE", credits, sem)
        offering(cv, cid, "BOTH")

course_id = dict(shared_ids)  # global code -> course_id registry
cc_id = {}  # (cv_id, code) -> curriculum_course_id registry


def add_course(cv, code, title, credits, category, nominal_sem, parity, **off_kwargs):
    cid = get_or_create_course(code, title, credits)
    course_id[code] = cid
    ccid = curriculum_course(cv, cid, category, credits, nominal_sem)
    cc_id[(cv, code)] = ccid
    offering(cv, cid, parity, **off_kwargs)
    return cid, ccid


# ---------------------------------------------------------------------------
# ME (Y24) -- reproduces PS Example 1 (Late Minor Aspirant)
# ---------------------------------------------------------------------------
add_course(cv_me_y24, "MSO202M", "Manufacturing Processes", 6, "CORE", 3, "ODD")
add_course(cv_me_y24, "ESO201", "Engineering Sciences", 11, "CORE", 3, "ODD")
add_course(cv_me_y24, "ME209", "Thermodynamics", 9, "CORE", 3, "ODD")

add_course(cv_me_y24, "ME231", "Fluid Mechanics", 8, "CORE", 4, "EVEN")
add_course(cv_me_y24, "ME222", "Mechanics of Solids", 6, "CORE", 4, "EVEN")
add_course(cv_me_y24, "ME252", "Manufacturing Science", 9, "CORE", 4, "EVEN")

add_course(cv_me_y24, "ME301", "Heat Transfer", 9, "CORE", 5, "ODD")
add_course(cv_me_y24, "ME321", "Machine Design", 9, "CORE", 5, "ODD")
add_course(cv_me_y24, "ME331", "Dynamics of Machinery", 9, "CORE", 5, "ODD")

add_course(cv_me_y24, "ME302", "Turbomachinery", 9, "CORE", 6, "EVEN")
add_course(cv_me_y24, "ME341", "Control Systems", 9, "CORE", 6, "EVEN")
add_course(cv_me_y24, "ME354", "Design Project I", 9, "CORE", 6, "EVEN")

_, ccid = add_course(cv_me_y24, "MEHSS2", "HSS Elective II", 9, "HSS", 7, "ODD")
_, ccid = add_course(cv_me_y24, "MEDE1", "Departmental Elective I", 9, "DE", 7, "ODD")
add_course(cv_me_y24, "MEOE1", "Open Elective (OE-1)", 9, "OE", 7, "ODD")
add_course(cv_me_y24, "MEOE2", "Open Elective (OE-2)", 9, "OE", 7, "ODD")

add_course(cv_me_y24, "MEDE2", "Departmental Elective II", 9, "DE", 8, "EVEN")
add_course(cv_me_y24, "MEDE3", "Departmental Elective III / UGP", 9, "DE", 8, "EVEN")
add_course(cv_me_y24, "MEOE3", "Open Elective (OE-3)", 9, "OE", 8, "EVEN")

prereq(cc_id[(cv_me_y24, "ME301")], [course_id["ME209"]])
prereq(cc_id[(cv_me_y24, "ME321")], [course_id["ME231"]])
prereq(cc_id[(cv_me_y24, "ME302")], [course_id["ME301"]])
prereq(cc_id[(cv_me_y24, "ME341")], [course_id["ME321"]])

# Data Science Minor basket: 3-course prerequisite chain, deliberately parity-locked so that
# starting from Sem7 (the earliest a Y24-ME student in Sem6 can begin it) the chain cannot
# complete before Sem9 -- this is what reproduces the PS's "prerequisite chain, not credit
# shortage, forces the extension" reasoning.
_, ds101_cc = add_course(cv_me_y24, "DS101", "Foundations of Data Science", 9, "MINOR_BASKET", None, "ODD")
_, ds201_cc = add_course(cv_me_y24, "DS201", "Applied Machine Learning", 9, "MINOR_BASKET", None, "EVEN")
_, ds301_cc = add_course(cv_me_y24, "DS301", "Advanced Data Science", 9, "MINOR_BASKET", None, "ODD", seat_cap=30, seat_unc=True, notes="Seat cap not confirmed by department; treat as tentative")
prereq(ds201_cc, [course_id["DS101"]])
prereq(ds301_cc, [course_id["DS201"]])

prog_ds_minor = insert("programme", name="Data Science Minor", type="MINOR")
for code in ("DS101", "DS201", "DS301"):
    insert(
        "programme_requirement",
        programme_id=prog_ds_minor,
        curriculum_version_id=cv_me_y24,
        curriculum_course_id=cc_id[(cv_me_y24, code)],
        min_credits=None,
        min_courses=None,
    )

# ---------------------------------------------------------------------------
# AE (Y23) -- reproduces PS Example 2 (Career-Focused, Conflicting Electives)
# ---------------------------------------------------------------------------
add_course(cv_ae_y23, "MSO202M", "Manufacturing Processes", 6, "CORE", 3, "ODD")
add_course(cv_ae_y23, "AE201M", "Aerodynamics I", 5, "CORE", 3, "ODD")
add_course(cv_ae_y23, "AE209", "Flight Mechanics", 8, "CORE", 3, "ODD")

add_course(cv_ae_y23, "AE211", "Aerodynamics II", 9, "CORE", 4, "EVEN")
add_course(cv_ae_y23, "AE233M", "Structures I", 5, "CORE", 4, "EVEN")

add_course(cv_ae_y23, "AE311", "Structures II", 9, "CORE", 5, "ODD")
add_course(cv_ae_y23, "AE321", "Propulsion", 9, "CORE", 5, "ODD")

add_course(cv_ae_y23, "AE341", "Flight Control", 11, "CORE", 6, "EVEN")
add_course(cv_ae_y23, "AE322", "Propulsion II", 9, "CORE", 6, "EVEN")

add_course(cv_ae_y23, "AE421", "Capstone Design I", 3, "CORE", 7, "ODD")
add_course(cv_ae_y23, "AE462", "Capstone Design II", 4, "CORE", 8, "EVEN")

prereq(cc_id[(cv_ae_y23, "AE211")], [course_id["AE201M"]])
prereq(cc_id[(cv_ae_y23, "AE311")], [course_id["AE211"]])
prereq(cc_id[(cv_ae_y23, "AE341")], [course_id["AE311"]])  # matches the one real prereq note found in the official AE template

# Robotics & Autonomy elective chain -- deliberately structured so several valid roadmaps
# exist (multi-objective ranking, not a single answer), and one high-relevance course is
# genuinely unschedulable (offered exactly once, before its own prerequisite can complete).
add_course(cv_ae_y23, "AECTRL1", "Control Systems Fundamentals", 9, "DE", 5, "ODD")
add_course(cv_ae_y23, "AESIG1", "Signals & Systems", 9, "DE", 5, "ODD")
add_course(cv_ae_y23, "AEMATL1", "Aerospace Materials", 9, "DE", 6, "EVEN")
add_course(cv_ae_y23, "AEROBO1", "Introduction to Robotics", 9, "DE", 6, "EVEN")
add_course(cv_ae_y23, "AEROBOADV", "Advanced Autonomous Systems", 9, "DE", 7, "ODD")
add_course(cv_ae_y23, "AEROBOADV2", "Autonomous Systems Capstone", 9, "DE", 8, "EVEN")
add_course(cv_ae_y23, "AESTRUCTDE", "Advanced Structures Elective", 9, "DE", 8, "EVEN")
# Impossible-by-construction: only ever offered in Sem5(ODD), but requires a course that
# itself is only offered Sem6(EVEN) -- no valid order exists. Used to demonstrate rejection
# explanations for a structurally-impossible-though-highly-relevant course.
add_course(cv_ae_y23, "AEADVMATH", "Advanced Applied Mathematics for Controls", 9, "DE", 6, "EVEN")
add_course(cv_ae_y23, "AEROBOELITE", "Elite Robotics Seminar", 9, "DE", 5, "ODD", off_unc=True, notes="Offered at most once; not confirmed for every AE batch")

prereq(cc_id[(cv_ae_y23, "AEROBO1")], [course_id["AECTRL1"]])
prereq(cc_id[(cv_ae_y23, "AEROBOADV")], [course_id["AEROBO1"]])
prereq(cc_id[(cv_ae_y23, "AEROBOADV2")], [course_id["AEROBOADV"]])
prereq(cc_id[(cv_ae_y23, "AEROBOELITE")], [course_id["AEADVMATH"]])  # impossible ordering by construction

# Generic Open Elective slots, Sem5-8, modest relevance
for sem, parity, code in [(5, "ODD", "OE1"), (6, "EVEN", "OE2"), (7, "ODD", "OE3"), (8, "EVEN", "OE4")]:
    add_course(cv_ae_y23, f"AE-{code}", f"Open Elective ({code})", 9, "OE", sem, parity)

career_robotics = insert("career_interest_area", name="Robotics & Autonomy")
for code, weight in [
    ("AECTRL1", 0.6), ("AESIG1", 0.3), ("AEMATL1", 0.2), ("AEROBO1", 0.9),
    ("AEROBOADV", 0.97), ("AEROBOADV2", 0.99), ("AESTRUCTDE", 0.1), ("AEROBOELITE", 0.99),
]:
    insert_plain(
        "course_career_relevance",
        career_interest_area_id=career_robotics,
        curriculum_course_id=cc_id[(cv_ae_y23, code)],
        relevance_weight=weight,
    )

# ---------------------------------------------------------------------------
# MSE (Y24) -- reproduces PS Example 3 (Prerequisite Bottleneck)
# ---------------------------------------------------------------------------
add_course(cv_mse_y24, "MSE201", "Structure of Materials", 11, "CORE", 3, "ODD")
add_course(cv_mse_y24, "MSE203", "Thermodynamics of Materials", 9, "CORE", 3, "ODD")

add_course(cv_mse_y24, "MSE202", "Phase Transformations", 11, "CORE", 4, "EVEN")
add_course(cv_mse_y24, "MSE205", "Mechanical Behavior of Materials", 8, "CORE", 4, "EVEN")

add_course(cv_mse_y24, "MSE301", "Materials Characterization", 9, "CORE", 5, "ODD")
add_course(cv_mse_y24, "MSE302", "Electronic Materials", 9, "CORE", 5, "ODD")

add_course(cv_mse_y24, "MSE306", "Materials Processing", 9, "CORE", 6, "EVEN")
add_course(cv_mse_y24, "MSEDE1", "Departmental Elective I", 9, "DE", 6, "EVEN")

add_course(cv_mse_y24, "MSEDE2", "Departmental Elective II", 9, "DE", 7, "ODD")
add_course(cv_mse_y24, "MSEOE1", "Open Elective", 9, "OE", 7, "ODD")
add_course(cv_mse_y24, "MSE401", "Capstone Design I", 9, "CORE", 7, "ODD")

add_course(cv_mse_y24, "MSEOE2", "Open Elective", 9, "OE", 8, "EVEN")
add_course(cv_mse_y24, "MSEOE3", "Open Elective", 9, "OE", 8, "EVEN")
add_course(cv_mse_y24, "MSE402", "Capstone Design II", 9, "CORE", 8, "EVEN")
prereq(cc_id[(cv_mse_y24, "MSE401")], [course_id["MSE306"]])
prereq(cc_id[(cv_mse_y24, "MSE402")], [course_id["MSE401"]])

# The requested advanced interdisciplinary elective: only offered ODD, requires MSE201.
add_course(cv_mse_y24, "MSEADVELEC", "Interdisciplinary Materials Elective", 9, "DE", 5, "ODD")
prereq(cc_id[(cv_mse_y24, "MSEADVELEC")], [course_id["MSE201"]])

conn.commit()

# ---------------------------------------------------------------------------
# Students -- exact reproductions of PS Examples 1, 2, 3
# ---------------------------------------------------------------------------
stu_me = insert("student", name="Example1_LateMinorAspirant", curriculum_version_id=cv_me_y24, current_semester=6, cpi=8.5)
stu_ae = insert("student", name="Example2_CareerFocused", curriculum_version_id=cv_ae_y23, current_semester=5, cpi=8.0)
stu_mse = insert("student", name="Example3_PrereqBottleneck", curriculum_version_id=cv_mse_y24, current_semester=4, cpi=7.6)
stu_egrade = insert("student", name="Example4_EGrade_SatisfiedSlot", curriculum_version_id=cv_mse_y24, current_semester=5, cpi=7.2)

# ME student: passed everything through Sem5, Sem6 core in progress, no minor declared yet.
me_passed_codes = ["MTH101", "PHY101", "CHM101", "TA101", "MTH102", "PHY102", "ESC101",
                    "MSO202M", "ESO201", "ME209", "ME231", "ME222", "ME252",
                    "ME301", "ME321", "ME331"]
for code in me_passed_codes:
    insert("student_completed_course", student_id=stu_me, course_id=course_id[code], semester_taken=5, grade_status="PASSED")
insert_plain("student_declared_programme", student_id=stu_me, programme_id=prog_ds_minor, status="TARGET")
insert("student_preference", student_id=stu_me, max_credits_per_semester=50, allow_summer=False, willing_to_extend=True, career_interest_tags=["Data Science"])

# AE student: mandatory courses through Sem4 completed.
ae_passed_codes = ["MTH101", "PHY101", "CHM101", "TA101", "MTH102", "PHY102", "ESC101",
                    "MSO202M", "AE201M", "AE209", "AE211", "AE233M"]
for code in ae_passed_codes:
    insert("student_completed_course", student_id=stu_ae, course_id=course_id[code], semester_taken=4, grade_status="PASSED")
insert("student_preference", student_id=stu_ae, max_credits_per_semester=48, allow_summer=False, willing_to_extend=False, career_interest_tags=["Robotics & Autonomy"])

# MSE student: passed through Sem3 EXCEPT MSE201 (failed); Sem4 core in progress.
mse_passed_codes = ["MTH101", "PHY101", "CHM101", "TA101", "MTH102", "PHY102", "ESC101", "MSE203"]
for code in mse_passed_codes:
    insert("student_completed_course", student_id=stu_mse, course_id=course_id[code], semester_taken=3, grade_status="PASSED")
insert("student_completed_course", student_id=stu_mse, course_id=course_id["MSE201"], semester_taken=3, grade_status="FAILED")
insert("student_preference", student_id=stu_mse, max_credits_per_semester=55, allow_summer=False, willing_to_extend=False, career_interest_tags=[])

# MSE student 2 (Example 4): E_GRADE in MSE201, satisfied slot for MSEDE1
mse4_passed_codes = ["MTH101", "PHY101", "CHM101", "TA101", "MTH102", "PHY102", "ESC101", "MSE203", "MSE202", "MSE205"]
for code in mse4_passed_codes:
    insert("student_completed_course", student_id=stu_egrade, course_id=course_id[code], semester_taken=3, grade_status="PASSED")
insert("student_completed_course", student_id=stu_egrade, course_id=course_id["MSE201"], semester_taken=3, grade_status="E_GRADE")
insert("student_satisfied_slot", student_id=stu_egrade, curriculum_course_id=cc_id[(cv_mse_y24, "MSEDE1")])
insert("student_preference", student_id=stu_egrade, max_credits_per_semester=55, allow_summer=False, willing_to_extend=True, career_interest_tags=[])

conn.commit()
print("Seed complete.")
print(f"student ids -> ME(Example1)={stu_me}  AE(Example2)={stu_ae}  MSE(Example3)={stu_mse}  MSE(Example4)={stu_egrade}")
cur.close()
conn.close()
