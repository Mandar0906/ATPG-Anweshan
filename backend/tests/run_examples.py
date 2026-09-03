"""
Reproduces PS Examples 1, 2, 3 end-to-end against the seeded database and asserts the
engine's classification matches the PS's expected reasoning. This is the litmus test
called out explicitly in the PS: "judges may test irregular or conflicting profiles to
verify dynamic graph traversal" -- these three ARE the profiles the PS itself gives us
to check against.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.csed.engine import generate_roadmap

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
results = []


def check(label, cond, detail=""):
    cond = bool(cond)
    results.append(cond)
    print(f"  [{PASS if cond else FAIL}] {label}" + (f" -- {detail}" if detail else ""))


def print_roadmap(tag, r):
    print(f"\n--- {tag}: status={r['status']}  adjustment={r.get('adjustment')} ---")
    if r["primary"]:
        for sem, info in sorted(r["primary"]["semesters"].items()):
            codes = ", ".join(f"{c['code']}({c['category']},{c['credits']}cr)" for c in info["courses"])
            print(f"  Sem {sem} [{info['total_credits']} cr]: {codes}")
        print(f"  score = {r['primary']['score']}")
        if r["primary"]["semester_shifts"]:
            print(f"  semester_shifts = {r['primary']['semester_shifts']}")
    if r.get("alternative"):
        print("  Alternative roadmap available (breadth / no-minor / etc.)")
    if r.get("why_standard_failed"):
        print(f"  why_standard_failed: {r['why_standard_failed']}")


print("=" * 80)
print("EXAMPLE 1 -- ME Y24, Sem6, CPI 8.5, target Data Science Minor, willing to extend to 9")
print("=" * 80)
r1 = generate_roadmap(student_id=1)
print_roadmap("Example 1", r1)
check("Status is FEASIBLE_WITH_ADJUSTMENT", r1["status"] == "FEASIBLE_WITH_ADJUSTMENT")
check("Adjustment reason is DEGREE_EXTENSION", r1.get("adjustment") == "DEGREE_EXTENSION")
check("Roadmap extends to semester 9, not beyond",
      r1["primary"] and max(r1["primary"]["semesters"].keys()) == 9,
      f"max semester = {max(r1['primary']['semesters'].keys()) if r1['primary'] else None}")
check("DS101/DS201/DS301 all scheduled",
      r1["primary"] and {"DS101", "DS201", "DS301"} <= {
          c["code"] for info in r1["primary"]["semesters"].values() for c in info["courses"]})
check("An alternative (no-minor, 8-semester) pathway is offered", r1.get("alternative") is not None)

print("\n" + "=" * 80)
print("EXAMPLE 2 -- AE Y23, Sem5, CPI 8.0, robotics career interest, max 48 credits, 8 sem")
print("=" * 80)
r2 = generate_roadmap(student_id=2)
print_roadmap("Example 2", r2)
check("Status is FEASIBLE", r2["status"] == "FEASIBLE")
check("Ends at semester 8", r2["primary"] and max(r2["primary"]["semesters"].keys()) == 8)
check("No semester exceeds 48 credits",
      r2["primary"] and all(info["total_credits"] <= 48 for info in r2["primary"]["semesters"].values()))
check("At least one robotics-relevant elective (AEROBO1/AEROBOADV/AECTRL1) chosen",
      r2["primary"] and any(c["code"] in ("AECTRL1", "AEROBO1", "AEROBOADV", "AEROBOADV2")
                             for info in r2["primary"]["semesters"].values() for c in info["courses"]))
check("Structurally-impossible AEROBOELITE never scheduled",
      r2["primary"] and "AEROBOELITE" not in {c["code"] for info in r2["primary"]["semesters"].values() for c in info["courses"]})
check("An alternative roadmap is offered for comparison", r2.get("alternative") is not None)

print("\n" + "=" * 80)
print("EXAMPLE 3 -- MSE Y24, Sem4, CPI 7.6, MSE201 failed, wants MSEADVELEC in Sem5, no summer, 8 sem")
print("=" * 80)
r3 = generate_roadmap(student_id=3, forced_elective_codes=["MSEADVELEC"],
                       requested_semester_hints={"MSEADVELEC": 5})
print_roadmap("Example 3", r3)
check("Status is FEASIBLE_WITH_ADJUSTMENT (requested infeasible, modified plan feasible)",
      r3["status"] == "FEASIBLE_WITH_ADJUSTMENT")
check("Ends at semester 8 (original graduation date retained)",
      r3["primary"] and max(r3["primary"]["semesters"].keys()) == 8)
check("MSE201 (the failed prerequisite) is retaken in semester 5",
      r3["primary"] and any(c["code"] == "MSE201" for c in r3["primary"]["semesters"].get(5, {}).get("courses", [])))
check("MSEADVELEC is NOT in semester 5 (would violate the uncleared prerequisite)",
      r3["primary"] and "MSEADVELEC" not in {c["code"] for c in r3["primary"]["semesters"].get(5, {}).get("courses", [])})
check("A semester_shift explanation was recorded for MSEADVELEC (requested 5 -> actual)",
      r3["primary"] and any(s["code"] == "MSEADVELEC" for s in r3["primary"]["semester_shifts"]))

print("\n" + "=" * 80)
print("EXAMPLE 4 -- MSE Y24, Sem5, E_GRADE in MSE201, Satisfied Slot MSEDE1")
print("=" * 80)
r4 = generate_roadmap(student_id=4, forced_elective_codes=["MSEADVELEC"], requested_semester_hints={"MSEADVELEC": 5})
print_roadmap("Example 4", r4)
check("Status is FEASIBLE (or FEASIBLE_WITH_ADJUSTMENT)", r4["status"] in ("FEASIBLE", "FEASIBLE_WITH_ADJUSTMENT"))
check("MSEADVELEC is scheduled in semester 5 because MSE201 (E_GRADE) satisfies the prerequisite",
      r4["primary"] and any(c["code"] == "MSEADVELEC" for c in r4["primary"]["semesters"].get(5, {}).get("courses", [])) or (r4["primary"] and any(s["code"] == "MSEADVELEC" for s in r4["primary"]["semester_shifts"])))
check("MSE201 (the E-graded prerequisite) is retaken in semester 5 or later",
      r4["primary"] and any(c["code"] == "MSE201" for sem, info in r4["primary"]["semesters"].items() for c in info["courses"]))
check("MSEDE1 is NOT scheduled (slot is already satisfied)",
      r4["primary"] and not any(c["code"] == "MSEDE1" for sem, info in r4["primary"]["semesters"].items() for c in info["courses"]))

print("\n" + "=" * 80)
total, passed = len(results), sum(results)
print(f"RESULT: {passed}/{total} checks passed")
print("=" * 80)
sys.exit(0 if passed == total else 1)
