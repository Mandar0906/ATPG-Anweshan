"use client";

import { useEffect, useState } from "react";
import {
  listStudents,
  generateRoadmap,
  StudentSummary,
  RoadmapResult,
  RenderedRoadmap,
} from "@/lib/api";
import PreferencesPanel from "@/components/PreferencesPanel";
import NewStudentForm from "@/components/NewStudentForm";

const STATUS_STYLE: Record<string, { emoji: string; label: string; classes: string }> = {
  FEASIBLE: {
    emoji: "🟢",
    label: "Feasible",
    classes: "bg-green-50 text-green-800 border-green-300 dark:bg-green-950 dark:text-green-300",
  },
  FEASIBLE_WITH_ADJUSTMENT: {
    emoji: "🟡",
    label: "Feasible with Adjustment",
    classes:
      "bg-amber-50 text-amber-800 border-amber-300 dark:bg-amber-950 dark:text-amber-300",
  },
  CURRENTLY_INFEASIBLE: {
    emoji: "🔴",
    label: "Currently Infeasible",
    classes: "bg-red-50 text-red-800 border-red-300 dark:bg-red-950 dark:text-red-300",
  },
};

const SEVERITY_STYLE: Record<string, string> = {
  LOW: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  MEDIUM: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  HIGH: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const CATEGORY_STYLE: Record<string, string> = {
  CORE: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  DE: "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300",
  OE: "bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-300",
  HSS: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  MINOR_BASKET: "bg-pink-100 text-pink-800 dark:bg-pink-950 dark:text-pink-300",
};

function StatusBadge({ status, adjustment }: { status: string; adjustment: string | null }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.CURRENTLY_INFEASIBLE;
  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-medium ${s.classes}`}>
      <span>{s.emoji}</span>
      <span>{s.label}</span>
      {adjustment && <span className="opacity-70">· {adjustment.replaceAll("_", " ")}</span>}
    </div>
  );
}

function RoadmapView({ roadmap, title }: { roadmap: RenderedRoadmap; title: string }) {
  const semesters = Object.entries(roadmap.semesters).sort(
    (a, b) => Number(a[0]) - Number(b[0])
  );
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">{title}</h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {semesters.map(([sem, info]) => (
          <div key={sem} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
            <div className="mb-2 flex items-baseline justify-between">
              <span className="font-semibold">Semester {sem}</span>
              <span className="text-xs text-zinc-500">{info.total_credits} credits</span>
            </div>
            <ul className="space-y-1">
              {info.courses.map((c) => (
                <li key={c.code} className="flex items-center justify-between gap-2 text-sm">
                  <span>
                    <span className="font-mono">{c.code}</span>{" "}
                    <span className="text-zinc-500">— {c.title}</span>
                  </span>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      CATEGORY_STYLE[c.category] ?? "bg-zinc-100 text-zinc-700"
                    }`}
                  >
                    {c.category}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {roadmap.semester_shifts.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950">
          {roadmap.semester_shifts.map((s) => (
            <div key={s.code}>
              <span className="font-mono">{s.code}</span> was requested for semester{" "}
              {s.requested_semester} but placed in semester {s.actual_semester} instead —
              see the explainability log below for why.
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ExplainabilityLog({ trace }: { trace: RenderedRoadmap["trace"] }) {
  const rejected = trace.filter((t) => t.decision_type === "REJECTED");
  const placed = trace.filter((t) => t.decision_type === "PLACED");
  return (
    <div className="space-y-3">
      {rejected.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-600">
            Rejected / structurally infeasible
          </h4>
          <ul className="space-y-1 text-sm">
            {rejected.map((t, i) => (
              <li key={i} className="rounded border border-red-200 bg-red-50 p-2 dark:border-red-900 dark:bg-red-950">
                <span className="font-mono text-xs text-red-700 dark:text-red-300">{t.reason_code}</span>
                <div>{t.detail}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Placement decisions ({placed.length})
        </summary>
        <ul className="mt-2 space-y-1">
          {placed
            .sort((a, b) => (a.semester ?? 0) - (b.semester ?? 0))
            .map((t, i) => (
              <li key={i} className="rounded border border-zinc-200 p-2 dark:border-zinc-800">
                {t.detail}
              </li>
            ))}
        </ul>
      </details>
    </div>
  );
}

function RiskFlags({ flags }: { flags: RoadmapResult["risk_flags"] }) {
  if (!flags || flags.length === 0) {
    return <p className="text-sm text-zinc-500">No risk flags on this roadmap.</p>;
  }
  return (
    <ul className="space-y-2">
      {flags.map((f, i) => (
        <li key={i} className="flex items-start gap-2 rounded-md border border-zinc-200 p-2 text-sm dark:border-zinc-800">
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${SEVERITY_STYLE[f.severity]}`}>
            {f.severity}
          </span>
          <div>
            <span className="font-medium">{f.risk_type.replaceAll("_", " ")}</span>
            {f.course_code && <span className="font-mono text-zinc-500"> · {f.course_code}</span>}
            {f.semester != null && <span className="text-zinc-500"> · Sem {f.semester}</span>}
            <div className="text-zinc-600 dark:text-zinc-400">{f.detail}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function Home() {
  const [students, setStudents] = useState<StudentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [forcedCode, setForcedCode] = useState("");
  const [requestedSem, setRequestedSem] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RoadmapResult | null>(null);
  const [showAlternative, setShowAlternative] = useState(false);
  const [showNewForm, setShowNewForm] = useState(false);

  function refreshStudents(selectId?: number) {
    return listStudents()
      .then((s) => {
        setStudents(s);
        if (selectId != null) setSelectedId(selectId);
        else if (s.length && selectedId == null) setSelectedId(s[0].id);
      })
      .catch((e) => setError(String(e)));
  }

  useEffect(() => {
    refreshStudents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onGenerate() {
    if (selectedId == null) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setShowAlternative(false);
    try {
      const hints =
        forcedCode && requestedSem ? { [forcedCode.trim()]: Number(requestedSem) } : undefined;
      const r = await generateRoadmap(
        selectedId,
        forcedCode ? [forcedCode.trim()] : undefined,
        hints
      );
      setResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const selectedStudent = students.find((s) => s.id === selectedId);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold">APTG</h1>
        <p className="text-sm text-zinc-500">
          Algorithmic Academic Pathway &amp; Template Generator — deterministic CSED + DPGR engine
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          {error}
          <div className="mt-1 text-xs opacity-75">
            Is the API reachable? Check NEXT_PUBLIC_API_URL and that the backend is running.
          </div>
        </div>
      )}

      <section className="mb-6 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Student profile</h2>
          <button
            className="text-sm font-medium text-blue-600 underline dark:text-blue-400"
            onClick={() => setShowNewForm((v) => !v)}
          >
            {showNewForm ? "Cancel" : "+ New student profile"}
          </button>
        </div>

        {showNewForm ? (
          <NewStudentForm
            onCreated={(id) => {
              setShowNewForm(false);
              refreshStudents(id);
            }}
          />
        ) : (
          <>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-zinc-500">Student</span>
              <select
                className="w-full max-w-md rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
                value={selectedId ?? ""}
                onChange={(e) => setSelectedId(Number(e.target.value))}
              >
                {students.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.department} Y{String(s.batch_year).slice(-2)}, Sem {s.current_semester}, CPI {s.cpi})
                  </option>
                ))}
              </select>
            </label>

            {selectedId != null && (
              <div className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-500">
                  Preferences (saved to this student — no summer, workload cap, target minor,
                  career interests, willingness to extend all live here)
                </h3>
                <PreferencesPanel studentId={selectedId} />
              </div>
            )}

            <div className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-500">
                One-off request (optional) — ask for a specific course in a specific semester
              </h3>
              <div className="flex flex-wrap items-end gap-4">
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-zinc-500">Course code</span>
                  <input
                    className="w-48 rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 font-mono dark:border-zinc-700"
                    placeholder="e.g. MSEADVELEC"
                    value={forcedCode}
                    onChange={(e) => setForcedCode(e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-zinc-500">Requested semester</span>
                  <input
                    type="number"
                    className="w-32 rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 dark:border-zinc-700"
                    placeholder="e.g. 5"
                    value={requestedSem}
                    onChange={(e) => setRequestedSem(e.target.value)}
                  />
                </label>
                <button
                  onClick={onGenerate}
                  disabled={loading || selectedId == null}
                  className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-zinc-900"
                >
                  {loading ? "Generating…" : "Generate Roadmap"}
                </button>
              </div>
              {selectedStudent && (
                <p className="mt-2 text-xs text-zinc-500">
                  Try MSEADVELEC / semester 5 on Example3_PrereqBottleneck to see the
                  semester-shift explanation. Leave both blank for a normal run.
                </p>
              )}
            </div>
          </>
        )}
      </section>

      {result && (
        <section className="space-y-6">
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={result.status} adjustment={result.adjustment} />
            {result.primary && (
              <span className="text-sm text-zinc-500">
                score {result.primary.score.score} · {result.primary.score.total_semesters_used} semesters
              </span>
            )}
          </div>

          {result.reason && (
            <p className="rounded-md border border-red-300 bg-red-50 p-3 text-sm dark:border-red-800 dark:bg-red-950">
              {result.reason}
            </p>
          )}

          {result.why_standard_failed && result.why_standard_failed.length > 0 && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950">
              <span className="font-semibold">Why the standard 8-semester plan failed: </span>
              {result.why_standard_failed.join(" ")}
            </div>
          )}

          {result.primary && <RoadmapView roadmap={result.primary} title="Generated roadmap" />}

          {result.alternative && (
            <div>
              <button
                className="text-sm font-medium text-blue-600 underline dark:text-blue-400"
                onClick={() => setShowAlternative((v) => !v)}
              >
                {showAlternative ? "Hide alternative pathway" : "Show alternative pathway"}
              </button>
              {showAlternative && (
                <div className="mt-3">
                  <RoadmapView roadmap={result.alternative} title="Alternative roadmap" />
                </div>
              )}
            </div>
          )}

          {result.primary && (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <div>
                <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
                  Explainability log
                </h3>
                <ExplainabilityLog trace={result.primary.trace} />
              </div>
              <div>
                <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
                  Risk flags
                </h3>
                <RiskFlags flags={result.risk_flags} />
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
