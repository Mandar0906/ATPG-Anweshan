"use client";

import { useEffect, useState } from "react";
import {
  listCurriculumVersions,
  listCourses,
  listProgrammes,
  listCareerInterestAreas,
  createStudent,
  CurriculumVersion,
  CurriculumCourseOption,
  Programme,
  CareerInterestArea,
} from "@/lib/api";

type CourseState = "NONE" | "PASSED" | "FAILED";

export default function NewStudentForm({ onCreated }: { onCreated: (id: number) => void }) {
  const [versions, setVersions] = useState<CurriculumVersion[]>([]);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [courses, setCourses] = useState<CurriculumCourseOption[]>([]);
  const [courseState, setCourseState] = useState<Record<string, CourseState>>({});
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [areas, setAreas] = useState<CareerInterestArea[]>([]);

  const [name, setName] = useState("");
  const [currentSemester, setCurrentSemester] = useState("5");
  const [cpi, setCpi] = useState("8.0");
  const [maxCredits, setMaxCredits] = useState("");
  const [allowSummer, setAllowSummer] = useState(false);
  const [willingToExtend, setWillingToExtend] = useState(false);
  const [targetProgrammeId, setTargetProgrammeId] = useState("");
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCurriculumVersions().then((v) => {
      setVersions(v);
      if (v.length) setVersionId(v[0].id);
    });
    listCareerInterestAreas().then(setAreas);
  }, []);

  useEffect(() => {
    if (versionId == null) return;
    listCourses(versionId).then((c) => {
      setCourses(c);
      setCourseState({});
    });
    listProgrammes(versionId).then(setProgrammes);
    setTargetProgrammeId("");
  }, [versionId]);

  function cycleState(code: string) {
    setCourseState((prev) => {
      const cur = prev[code] ?? "NONE";
      const next: CourseState = cur === "NONE" ? "PASSED" : cur === "PASSED" ? "FAILED" : "NONE";
      return { ...prev, [code]: next };
    });
  }

  function toggleTag(tag: string) {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }

  async function submit() {
    if (versionId == null || !name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const completed_courses = Object.entries(courseState)
        .filter(([, state]) => state !== "NONE")
        .map(([code, state]) => {
          const course = courses.find((c) => c.code === code);
          return {
            code,
            grade_status: state as "PASSED" | "FAILED",
            semester_taken: course?.nominal_semester ?? Number(currentSemester) - 1,
          };
        });
      const { id } = await createStudent({
        name: name.trim(),
        curriculum_version_id: versionId,
        current_semester: Number(currentSemester),
        cpi: Number(cpi),
        completed_courses,
        target_programme_id: targetProgrammeId ? Number(targetProgrammeId) : null,
        preference: {
          max_credits_per_semester: maxCredits ? Number(maxCredits) : null,
          allow_summer: allowSummer,
          willing_to_extend: willingToExtend,
          career_interest_tags: Array.from(selectedTags),
          target_programme_id: targetProgrammeId ? Number(targetProgrammeId) : null,
        },
      });
      onCreated(id);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  const bySemester = new Map<string, CurriculumCourseOption[]>();
  for (const c of courses) {
    const key = c.nominal_semester != null ? String(c.nominal_semester) : "Elective / no fixed semester";
    if (!bySemester.has(key)) bySemester.set(key, []);
    bySemester.get(key)!.push(c);
  }

  return (
    <div className="space-y-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="font-semibold">Create a custom student profile</h2>

      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Name</span>
          <input
            className="w-48 rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. My Test Case"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Department / batch</span>
          <select
            className="w-48 rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
            value={versionId ?? ""}
            onChange={(e) => setVersionId(Number(e.target.value))}
          >
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.department} Y{String(v.batch_year).slice(-2)}
              </option>
            ))}
          </select>
          <span className="text-xs text-zinc-400">
            Only departments/batches with loaded curriculum data are offered.
          </span>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Current semester</span>
          <input
            type="number"
            min={1}
            max={12}
            className="w-24 rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
            value={currentSemester}
            onChange={(e) => setCurrentSemester(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">CPI</span>
          <input
            type="number"
            step="0.01"
            min={0}
            max={10}
            className="w-24 rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
            value={cpi}
            onChange={(e) => setCpi(e.target.value)}
          />
        </label>
      </div>

      <div>
        <span className="text-sm text-zinc-500">
          Completed courses — click to cycle Not taken → Passed → Failed
        </span>
        <div className="mt-2 max-h-64 space-y-3 overflow-y-auto rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
          {Array.from(bySemester.entries()).map(([sem, list]) => (
            <div key={sem}>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">
                {sem === "Elective / no fixed semester" ? sem : `Semester ${sem}`}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {list.map((c) => {
                  const state = courseState[c.code] ?? "NONE";
                  const style =
                    state === "PASSED"
                      ? "bg-green-100 border-green-400 text-green-800 dark:bg-green-950 dark:text-green-300"
                      : state === "FAILED"
                      ? "bg-red-100 border-red-400 text-red-800 dark:bg-red-950 dark:text-red-300"
                      : "border-zinc-300 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400";
                  return (
                    <button
                      key={c.code}
                      type="button"
                      onClick={() => cycleState(c.code)}
                      className={`rounded border px-2 py-1 font-mono text-xs ${style}`}
                      title={`${c.title} (${c.category}, ${c.credits}cr)`}
                    >
                      {c.code}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Max credits / semester</span>
          <input
            type="number"
            className="w-36 rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
            value={maxCredits}
            onChange={(e) => setMaxCredits(e.target.value)}
            placeholder="curriculum default"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-zinc-500">Target minor / programme</span>
          <select
            className="w-56 rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
            value={targetProgrammeId}
            onChange={(e) => setTargetProgrammeId(e.target.value)}
          >
            <option value="">None</option>
            {programmes.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.type})
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 self-end pb-1.5 text-sm">
          <input type="checkbox" checked={allowSummer} onChange={(e) => setAllowSummer(e.target.checked)} />
          Allow summer semesters
        </label>
        <label className="flex items-center gap-2 self-end pb-1.5 text-sm">
          <input
            type="checkbox"
            checked={willingToExtend}
            onChange={(e) => setWillingToExtend(e.target.checked)}
          />
          Willing to extend beyond 8 semesters
        </label>
      </div>

      {areas.length > 0 && (
        <div>
          <span className="text-sm text-zinc-500">Career interests</span>
          <div className="mt-1 flex flex-wrap gap-3">
            {areas.map((a) => (
              <label key={a.id} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={selectedTags.has(a.name)}
                  onChange={() => toggleTag(a.name)}
                />
                {a.name}
              </label>
            ))}
          </div>
        </div>
      )}

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <button
        onClick={submit}
        disabled={submitting || !name.trim() || versionId == null}
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-zinc-900"
      >
        {submitting ? "Creating…" : "Create student"}
      </button>
    </div>
  );
}
