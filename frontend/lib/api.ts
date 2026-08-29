const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface StudentSummary {
  id: number;
  name: string;
  department: string;
  batch_year: number;
  current_semester: number;
  cpi: number;
}

export interface CourseCard {
  code: string;
  title: string;
  category: string;
  credits: number;
}

export interface SemesterInfo {
  courses: CourseCard[];
  total_credits: number;
}

export interface TraceEntry {
  decision_type: "PLACED" | "REJECTED";
  cc_id: number | null;
  semester?: number;
  reason_code: string;
  detail: string;
}

export interface SemesterShift {
  code: string;
  requested_semester: number;
  actual_semester: number;
}

export interface RenderedRoadmap {
  semesters: Record<string, SemesterInfo>;
  score: {
    score: number;
    career_alignment: number;
    workload_imbalance_stdev: number;
    extension_penalty: number;
    total_semesters_used: number;
  };
  trace: TraceEntry[];
  semester_shifts: SemesterShift[];
}

export interface RiskFlag {
  risk_type: string;
  course_code: string | null;
  semester: number | null;
  severity: "LOW" | "MEDIUM" | "HIGH";
  detail: string;
}

export interface RoadmapResult {
  status: "FEASIBLE" | "FEASIBLE_WITH_ADJUSTMENT" | "CURRENTLY_INFEASIBLE";
  adjustment: string | null;
  requested_end_sem?: number;
  primary: RenderedRoadmap | null;
  alternative: RenderedRoadmap | null;
  n_valid_candidates_found: number;
  risk_flags?: RiskFlag[];
  why_standard_failed?: string[];
  reason?: string;
  engine_log?: unknown;
}

export interface CurriculumVersion {
  id: number;
  department: string;
  batch_year: number;
}

export interface CareerInterestArea {
  id: number;
  name: string;
}

export interface Programme {
  id: number;
  name: string;
  type: string;
}

export interface CurriculumCourseOption {
  id: number;
  code: string;
  title: string;
  category: string;
  credits: number;
  nominal_semester: number | null;
}

export interface Preference {
  max_credits_per_semester: number | null;
  allow_summer: boolean;
  willing_to_extend: boolean;
  career_interest_tags: string[];
  target_programme_id: number | null;
}

export interface StudentDetail extends StudentSummary {
  curriculum_version_id: number;
  completed_courses: { code: string; title: string; grade_status: string; semester_taken: number | null }[];
  programmes: { programme_id: number; name: string; type: string; status: string }[];
  preference: (Preference & { id: number; student_id: number }) | null;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}

export function listStudents(): Promise<StudentSummary[]> {
  return fetch(`${API_URL}/students`, { cache: "no-store" }).then((r) => json<StudentSummary[]>(r));
}

export function getStudent(id: number): Promise<StudentDetail> {
  return fetch(`${API_URL}/students/${id}`, { cache: "no-store" }).then((r) => json<StudentDetail>(r));
}

export function listCurriculumVersions(): Promise<CurriculumVersion[]> {
  return fetch(`${API_URL}/curriculum-versions`, { cache: "no-store" }).then((r) => json<CurriculumVersion[]>(r));
}

export function listCareerInterestAreas(): Promise<CareerInterestArea[]> {
  return fetch(`${API_URL}/career-interest-areas`, { cache: "no-store" }).then((r) => json<CareerInterestArea[]>(r));
}

export function listProgrammes(curriculumVersionId?: number): Promise<Programme[]> {
  const qs = curriculumVersionId ? `?curriculum_version_id=${curriculumVersionId}` : "";
  return fetch(`${API_URL}/programmes${qs}`, { cache: "no-store" }).then((r) => json<Programme[]>(r));
}

export function listCourses(curriculumVersionId: number): Promise<CurriculumCourseOption[]> {
  return fetch(`${API_URL}/courses?curriculum_version_id=${curriculumVersionId}`, { cache: "no-store" }).then(
    (r) => json<CurriculumCourseOption[]>(r)
  );
}

export function updatePreferences(studentId: number, pref: Preference): Promise<{ status: string }> {
  return fetch(`${API_URL}/students/${studentId}/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(pref),
  }).then((r) => json<{ status: string }>(r));
}

export interface CompletedCourseIn {
  code: string;
  grade_status: "PASSED" | "FAILED" | "IN_PROGRESS";
  semester_taken?: number | null;
}

export interface StudentCreate {
  name: string;
  curriculum_version_id: number;
  current_semester: number;
  cpi: number;
  completed_courses: CompletedCourseIn[];
  target_programme_id: number | null;
  preference: Preference;
}

export function createStudent(body: StudentCreate): Promise<{ id: number }> {
  return fetch(`${API_URL}/students`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => json<{ id: number }>(r));
}

export function generateRoadmap(
  studentId: number,
  forcedElectiveCodes?: string[],
  requestedSemesterHints?: Record<string, number>
): Promise<RoadmapResult> {
  return fetch(`${API_URL}/roadmap/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      student_id: studentId,
      forced_elective_codes: forcedElectiveCodes?.length ? forcedElectiveCodes : undefined,
      requested_semester_hints:
        requestedSemesterHints && Object.keys(requestedSemesterHints).length
          ? requestedSemesterHints
          : undefined,
    }),
  }).then((r) => json<RoadmapResult>(r));
}
