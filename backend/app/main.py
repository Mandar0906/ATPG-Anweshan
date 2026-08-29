"""
FastAPI layer over the CSED/DPGR engine. Thin by design: every endpoint either reads
plain reference/student data or calls engine.generate_roadmap() -- no scheduling logic
lives here, so the API can never diverge from what the deterministic engine actually
computed.
"""
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .csed.model import get_conn
from .csed.engine import generate_roadmap
from .csed.graph import CycleError

app = FastAPI(title="APTG API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prototype-scope: tighten to the deployed frontend origin before submission
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/students")
def list_students():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        select s.id, s.name, d.code as department, cv.batch_year, s.curriculum_version_id,
               s.current_semester, s.cpi
        from student s
        join curriculum_version cv on cv.id = s.curriculum_version_id
        join department d on d.id = cv.department_id
        order by s.id
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/students/{student_id}")
def get_student(student_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        select s.id, s.name, d.code as department, cv.batch_year, s.curriculum_version_id,
               s.current_semester, s.cpi
        from student s
        join curriculum_version cv on cv.id = s.curriculum_version_id
        join department d on d.id = cv.department_id
        where s.id = %s
    """, (student_id,))
    student = cur.fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")

    cur.execute("""
        select c.code, c.title, scc.grade_status, scc.semester_taken
        from student_completed_course scc join course c on c.id = scc.course_id
        where scc.student_id = %s order by scc.semester_taken, c.code
    """, (student_id,))
    student["completed_courses"] = cur.fetchall()

    cur.execute("""
        select p.id as programme_id, p.name, p.type, sdp.status
        from student_declared_programme sdp join programme p on p.id = sdp.programme_id
        where sdp.student_id = %s
    """, (student_id,))
    programmes = cur.fetchall()
    student["programmes"] = programmes

    cur.execute("select * from student_preference where student_id = %s", (student_id,))
    preference = cur.fetchone()
    if preference is not None:
        target = next((p for p in programmes if p["status"] == "TARGET"), None)
        preference["target_programme_id"] = target["programme_id"] if target else None
    student["preference"] = preference

    conn.close()
    return student


@app.get("/courses")
def list_courses(curriculum_version_id: Optional[int] = None):
    conn = get_conn()
    cur = conn.cursor()
    if curriculum_version_id:
        cur.execute("""
            select cc.id, c.code, c.title, cc.category, cc.credits, cc.nominal_semester
            from curriculum_course cc join course c on c.id = cc.course_id
            where cc.curriculum_version_id = %s order by cc.nominal_semester nulls last, c.code
        """, (curriculum_version_id,))
    else:
        cur.execute("select id, code, title, default_credits from course order by code")
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/programmes")
def list_programmes(curriculum_version_id: Optional[int] = None):
    conn = get_conn()
    cur = conn.cursor()
    if curriculum_version_id:
        # Only programmes that actually have defined requirements for this curriculum
        # version -- offering a minor with no requirement data would let a student
        # "target" it and have the engine treat it as trivially already satisfied,
        # which is misleading rather than merely incomplete.
        cur.execute("""
            select distinct p.id, p.name, p.type
            from programme p join programme_requirement pr on pr.programme_id = p.id
            where pr.curriculum_version_id = %s
            order by p.id
        """, (curriculum_version_id,))
    else:
        cur.execute("select id, name, type from programme order by id")
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/curriculum-versions")
def list_curriculum_versions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        select cv.id, d.code as department, cv.batch_year
        from curriculum_version cv join department d on d.id = cv.department_id
        order by d.code, cv.batch_year
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/career-interest-areas")
def list_career_interest_areas():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select id, name from career_interest_area order by name")
    rows = cur.fetchall()
    conn.close()
    return rows


class PreferenceUpdate(BaseModel):
    max_credits_per_semester: Optional[int] = None
    allow_summer: bool = False
    willing_to_extend: bool = False
    career_interest_tags: list[str] = []
    target_programme_id: Optional[int] = None  # None = no target minor/major


@app.put("/students/{student_id}/preferences")
def update_preferences(student_id: int, pref: PreferenceUpdate):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select id from student where id = %s", (student_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")

    cur.execute("select 1 from student_preference where student_id = %s", (student_id,))
    if cur.fetchone():
        cur.execute("""
            update student_preference
            set max_credits_per_semester = %s, allow_summer = %s,
                willing_to_extend = %s, career_interest_tags = %s
            where student_id = %s
        """, (pref.max_credits_per_semester, pref.allow_summer, pref.willing_to_extend,
              pref.career_interest_tags, student_id))
    else:
        cur.execute("""
            insert into student_preference
                (student_id, max_credits_per_semester, allow_summer, willing_to_extend, career_interest_tags)
            values (%s, %s, %s, %s, %s)
        """, (student_id, pref.max_credits_per_semester, pref.allow_summer, pref.willing_to_extend,
              pref.career_interest_tags))

    # Replace any existing TARGET declaration with the new one (a student can only be
    # actively targeting one extra programme at a time in this prototype's UI).
    cur.execute("delete from student_declared_programme where student_id = %s and status = 'TARGET'",
                (student_id,))
    if pref.target_programme_id is not None:
        cur.execute("""
            insert into student_declared_programme (student_id, programme_id, status)
            values (%s, %s, 'TARGET')
            on conflict (student_id, programme_id) do update set status = 'TARGET'
        """, (student_id, pref.target_programme_id))

    conn.commit()
    conn.close()
    return {"status": "ok"}


class CompletedCourseIn(BaseModel):
    code: str
    grade_status: str  # PASSED | FAILED | IN_PROGRESS
    semester_taken: Optional[int] = None


class StudentCreate(BaseModel):
    name: str
    curriculum_version_id: int
    current_semester: int
    cpi: float
    completed_courses: list[CompletedCourseIn] = []
    target_programme_id: Optional[int] = None
    preference: PreferenceUpdate = PreferenceUpdate()


@app.post("/students")
def create_student(body: StudentCreate):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("select id from curriculum_version where id = %s", (body.curriculum_version_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Unknown curriculum_version_id")

    cur.execute("""
        insert into student (name, curriculum_version_id, current_semester, cpi)
        values (%s, %s, %s, %s) returning id
    """, (body.name, body.curriculum_version_id, body.current_semester, body.cpi))
    student_id = cur.fetchone()["id"]

    for cc in body.completed_courses:
        cur.execute("select id from course where code = %s", (cc.code,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            conn.close()
            raise HTTPException(status_code=400, detail=f"Unknown course code: {cc.code}")
        cur.execute("""
            insert into student_completed_course (student_id, course_id, semester_taken, grade_status)
            values (%s, %s, %s, %s)
        """, (student_id, row["id"], cc.semester_taken, cc.grade_status))

    if body.target_programme_id is not None:
        cur.execute("""
            insert into student_declared_programme (student_id, programme_id, status)
            values (%s, %s, 'TARGET')
        """, (student_id, body.target_programme_id))

    cur.execute("""
        insert into student_preference
            (student_id, max_credits_per_semester, allow_summer, willing_to_extend, career_interest_tags)
        values (%s, %s, %s, %s, %s)
    """, (student_id, body.preference.max_credits_per_semester, body.preference.allow_summer,
          body.preference.willing_to_extend, body.preference.career_interest_tags))

    conn.commit()
    conn.close()
    return {"id": student_id}


class RoadmapRequest(BaseModel):
    student_id: int
    forced_elective_codes: Optional[list[str]] = None
    requested_semester_hints: Optional[dict[str, int]] = None


@app.post("/roadmap/generate")
def roadmap_generate(req: RoadmapRequest):
    try:
        result = generate_roadmap(
            student_id=req.student_id,
            forced_elective_codes=req.forced_elective_codes,
            requested_semester_hints=req.requested_semester_hints,
        )
    except CycleError as e:
        raise HTTPException(status_code=422, detail=f"Corrupted curriculum data: {e}")
    except Exception as e:  # pragma: no cover - defensive; surfaces engine errors legibly
        raise HTTPException(status_code=500, detail=f"Engine error: {e}")
    return result
