-- APTG core schema
-- Design principle: a curriculum is versioned by (department, batch_year).
-- Every rule table (courses-in-curriculum, prerequisites, offerings, requirements,
-- credit rules) hangs off curriculum_version_id, never off department_id alone.
-- This is what makes cross-batch generalization a data fact, not a code branch.

CREATE TABLE department (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(10) NOT NULL UNIQUE,   -- 'ME', 'AE', 'MSE'
    name            VARCHAR(120) NOT NULL
);

CREATE TABLE curriculum_version (
    id              SERIAL PRIMARY KEY,
    department_id   INTEGER NOT NULL REFERENCES department(id),
    batch_year      INTEGER NOT NULL,               -- 2024 for 'Y24', etc.
    source_note     TEXT,                            -- provenance: which doc, fetched when
    UNIQUE (department_id, batch_year)
);
CREATE INDEX idx_curriculum_version_dept ON curriculum_version(department_id);

CREATE TABLE course (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(20) NOT NULL UNIQUE,     -- 'ME301'
    title           VARCHAR(200) NOT NULL,
    default_credits INTEGER NOT NULL CHECK (default_credits > 0)
);

CREATE TABLE curriculum_course (
    id                   SERIAL PRIMARY KEY,
    curriculum_version_id INTEGER NOT NULL REFERENCES curriculum_version(id),
    course_id            INTEGER NOT NULL REFERENCES course(id),
    category             VARCHAR(20) NOT NULL CHECK (category IN ('CORE','DE','OE','HSS','MINOR_BASKET','UGP')),
    credits              INTEGER NOT NULL CHECK (credits > 0),
    nominal_semester     INTEGER,                    -- template's suggested semester, NULL if elective/flexible
    UNIQUE (curriculum_version_id, course_id)
);
CREATE INDEX idx_curriculum_course_version ON curriculum_course(curriculum_version_id);
CREATE INDEX idx_curriculum_course_course ON curriculum_course(course_id);

CREATE TABLE prerequisite_group (
    id                   SERIAL PRIMARY KEY,
    curriculum_course_id INTEGER NOT NULL REFERENCES curriculum_course(id),
    logic                VARCHAR(3) NOT NULL CHECK (logic IN ('AND','OR')),
    is_illustrative       BOOLEAN NOT NULL DEFAULT FALSE  -- TRUE = inferred/demo data, not an official prereq registry
);
CREATE INDEX idx_prereq_group_course ON prerequisite_group(curriculum_course_id);

CREATE TABLE prerequisite_edge (
    id                    SERIAL PRIMARY KEY,
    group_id              INTEGER NOT NULL REFERENCES prerequisite_group(id) ON DELETE CASCADE,
    prerequisite_course_id INTEGER NOT NULL REFERENCES course(id)
);
CREATE INDEX idx_prereq_edge_group ON prerequisite_edge(group_id);
CREATE INDEX idx_prereq_edge_course ON prerequisite_edge(prerequisite_course_id);

CREATE TABLE course_offering (
    id                     SERIAL PRIMARY KEY,
    curriculum_version_id  INTEGER NOT NULL REFERENCES curriculum_version(id),
    course_id              INTEGER NOT NULL REFERENCES course(id),
    semester_parity        VARCHAR(4) NOT NULL CHECK (semester_parity IN ('ODD','EVEN','BOTH','SUMMER')),
    seat_cap               INTEGER,                  -- NULL = unknown/unlimited, see is_seat_cap_uncertain
    is_offering_uncertain  BOOLEAN NOT NULL DEFAULT FALSE,
    is_seat_cap_uncertain  BOOLEAN NOT NULL DEFAULT FALSE,
    notes                  TEXT,
    UNIQUE (curriculum_version_id, course_id, semester_parity)
);
CREATE INDEX idx_offering_version_course ON course_offering(curriculum_version_id, course_id);

CREATE TABLE programme (
    id     SERIAL PRIMARY KEY,
    name   VARCHAR(120) NOT NULL,
    type   VARCHAR(15) NOT NULL CHECK (type IN ('MAJOR','MINOR','DOUBLE_MAJOR'))
);

CREATE TABLE programme_requirement (
    id                       SERIAL PRIMARY KEY,
    programme_id             INTEGER NOT NULL REFERENCES programme(id),
    curriculum_version_id    INTEGER NOT NULL REFERENCES curriculum_version(id),  -- requesting student's own curriculum context
    curriculum_course_id     INTEGER REFERENCES curriculum_course(id),  -- set => "this specific course is required"
    required_category        VARCHAR(20),                                -- set => "N credits from this category/basket"
    min_credits              INTEGER,
    min_courses              INTEGER,
    CHECK (curriculum_course_id IS NOT NULL OR required_category IS NOT NULL)
);
CREATE INDEX idx_prog_req_programme ON programme_requirement(programme_id, curriculum_version_id);

CREATE TABLE credit_rule (
    id                          SERIAL PRIMARY KEY,
    curriculum_version_id       INTEGER NOT NULL UNIQUE REFERENCES curriculum_version(id),
    min_credits_per_semester    INTEGER NOT NULL,
    max_credits_per_semester    INTEGER NOT NULL,
    min_core_credits_total      INTEGER,
    min_de_credits_total        INTEGER,
    min_oe_credits_total        INTEGER,
    max_semesters_standard      INTEGER NOT NULL DEFAULT 8,
    max_semesters_with_extension INTEGER            -- NULL = extension ceiling unknown/unconfirmed
);

CREATE TABLE student (
    id                      SERIAL PRIMARY KEY,
    name                    VARCHAR(120) NOT NULL,
    curriculum_version_id   INTEGER NOT NULL REFERENCES curriculum_version(id),
    current_semester        INTEGER NOT NULL CHECK (current_semester >= 1),
    cpi                     NUMERIC(3,2)
);
CREATE INDEX idx_student_curriculum ON student(curriculum_version_id);

CREATE TABLE student_completed_course (
    id            SERIAL PRIMARY KEY,
    student_id    INTEGER NOT NULL REFERENCES student(id),
    course_id     INTEGER NOT NULL REFERENCES course(id),
    semester_taken INTEGER,
    grade_status  VARCHAR(12) NOT NULL CHECK (grade_status IN ('PASSED','FAILED','IN_PROGRESS')),
    UNIQUE (student_id, course_id)
);
CREATE INDEX idx_completed_student ON student_completed_course(student_id);

CREATE TABLE student_declared_programme (
    student_id    INTEGER NOT NULL REFERENCES student(id),
    programme_id  INTEGER NOT NULL REFERENCES programme(id),
    status        VARCHAR(10) NOT NULL CHECK (status IN ('DECLARED','TARGET')),
    PRIMARY KEY (student_id, programme_id)
);

CREATE TABLE career_interest_area (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(80) NOT NULL UNIQUE       -- e.g. 'Robotics & Autonomy', 'Data Science & ML'
);

CREATE TABLE course_career_relevance (
    career_interest_area_id INTEGER NOT NULL REFERENCES career_interest_area(id),
    curriculum_course_id    INTEGER NOT NULL REFERENCES curriculum_course(id),
    relevance_weight        NUMERIC(3,2) NOT NULL CHECK (relevance_weight BETWEEN 0 AND 1),
    PRIMARY KEY (career_interest_area_id, curriculum_course_id)
);

CREATE TABLE student_preference (
    id                        SERIAL PRIMARY KEY,
    student_id                INTEGER NOT NULL UNIQUE REFERENCES student(id),
    max_credits_per_semester  INTEGER,
    allow_summer              BOOLEAN NOT NULL DEFAULT FALSE,
    willing_to_extend         BOOLEAN NOT NULL DEFAULT FALSE,
    career_interest_tags      TEXT[]                 -- raw student-entered tags, mapped to career_interest_area separately
);

CREATE TABLE roadmap (
    id                  SERIAL PRIMARY KEY,
    student_id          INTEGER NOT NULL REFERENCES student(id),
    generated_at        TIMESTAMP NOT NULL DEFAULT now(),
    status              VARCHAR(28) NOT NULL CHECK (status IN ('FEASIBLE','FEASIBLE_WITH_ADJUSTMENT','CURRENTLY_INFEASIBLE')),
    total_semesters     INTEGER,
    is_alternative       BOOLEAN NOT NULL DEFAULT FALSE,
    primary_roadmap_id  INTEGER REFERENCES roadmap(id),
    objective_score     NUMERIC(6,3)
);
CREATE INDEX idx_roadmap_student ON roadmap(student_id);

CREATE TABLE roadmap_assignment (
    id                    SERIAL PRIMARY KEY,
    roadmap_id            INTEGER NOT NULL REFERENCES roadmap(id) ON DELETE CASCADE,
    semester_number        INTEGER NOT NULL,
    curriculum_course_id   INTEGER NOT NULL REFERENCES curriculum_course(id),
    slot_type              VARCHAR(20) NOT NULL,
    credits_snapshot        INTEGER NOT NULL
);
CREATE INDEX idx_roadmap_assignment_roadmap ON roadmap_assignment(roadmap_id);

CREATE TABLE explanation_log (
    id                      SERIAL PRIMARY KEY,
    roadmap_id              INTEGER NOT NULL REFERENCES roadmap(id) ON DELETE CASCADE,
    roadmap_assignment_id   INTEGER REFERENCES roadmap_assignment(id),
    decision_type           VARCHAR(10) NOT NULL CHECK (decision_type IN ('PLACED','REJECTED')),
    reason_code             VARCHAR(60) NOT NULL,
    reason_detail           JSONB NOT NULL
);
CREATE INDEX idx_explanation_roadmap ON explanation_log(roadmap_id);

CREATE TABLE risk_flag (
    id                  SERIAL PRIMARY KEY,
    roadmap_id           INTEGER NOT NULL REFERENCES roadmap(id) ON DELETE CASCADE,
    risk_type            VARCHAR(30) NOT NULL CHECK (risk_type IN
                          ('SEAT_LIMITED','UNCERTAIN_OFFERING','UNRESOLVED_PREREQ','DEGREE_EXTENSION',
                           'TIGHT_CHAIN','NEAR_CREDIT_LIMIT')),
    related_course_id    INTEGER REFERENCES course(id),
    severity              VARCHAR(6) NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH')),
    detail                 TEXT NOT NULL
);
CREATE INDEX idx_risk_roadmap ON risk_flag(roadmap_id);
