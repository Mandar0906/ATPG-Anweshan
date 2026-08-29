"use client";

import { useEffect, useState } from "react";
import {
  getStudent,
  listProgrammes,
  listCareerInterestAreas,
  updatePreferences,
  CareerInterestArea,
  Programme,
  StudentDetail,
} from "@/lib/api";

export default function PreferencesPanel({
  studentId,
  onSaved,
}: {
  studentId: number;
  onSaved?: () => void;
}) {
  const [student, setStudent] = useState<StudentDetail | null>(null);
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [areas, setAreas] = useState<CareerInterestArea[]>([]);

  const [maxCredits, setMaxCredits] = useState<string>("");
  const [allowSummer, setAllowSummer] = useState(false);
  const [willingToExtend, setWillingToExtend] = useState(false);
  const [targetProgrammeId, setTargetProgrammeId] = useState<string>("");
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSaved(false);
    getStudent(studentId).then((s) => {
      if (cancelled) return;
      setStudent(s);
      const p = s.preference;
      setMaxCredits(p?.max_credits_per_semester != null ? String(p.max_credits_per_semester) : "");
      setAllowSummer(p?.allow_summer ?? false);
      setWillingToExtend(p?.willing_to_extend ?? false);
      setTargetProgrammeId(p?.target_programme_id != null ? String(p.target_programme_id) : "");
      setSelectedTags(new Set(p?.career_interest_tags ?? []));
      listProgrammes(s.curriculum_version_id).then((rows) => !cancelled && setProgrammes(rows));
    });
    listCareerInterestAreas().then((rows) => !cancelled && setAreas(rows));
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  function toggleTag(name: string) {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      await updatePreferences(studentId, {
        max_credits_per_semester: maxCredits ? Number(maxCredits) : null,
        allow_summer: allowSummer,
        willing_to_extend: willingToExtend,
        career_interest_tags: Array.from(selectedTags),
        target_programme_id: targetProgrammeId ? Number(targetProgrammeId) : null,
      });
      setSaved(true);
      onSaved?.();
    } finally {
      setSaving(false);
    }
  }

  if (!student) return <p className="text-sm text-zinc-500">Loading preferences…</p>;

  return (
    <div className="space-y-3">
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
          {programmes.length === 0 && (
            <span className="text-xs text-zinc-400">
              No minors/majors have defined requirements for this department/batch yet.
            </span>
          )}
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

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-zinc-700"
        >
          {saving ? "Saving…" : "Save preferences"}
        </button>
        {saved && <span className="text-xs text-green-600 dark:text-green-400">Saved.</span>}
      </div>
    </div>
  );
}
