"""
DAG operations: cycle detection, topological ordering, prerequisite satisfaction,
and constraint propagation (earliest-possible-semester per node).

Node = curriculum_course.id. Edge = prerequisite_edge, direction prereq -> dependent
(a dependent cannot be scheduled before its prerequisite completes).
"""
from .model import Curriculum, CurriculumCourse, StudentState


class CycleError(Exception):
    def __init__(self, cycle_cc_ids):
        self.cycle_cc_ids = cycle_cc_ids
        super().__init__(f"Prerequisite cycle detected among curriculum_course ids: {cycle_cc_ids}")


def _dependency_edges(curriculum: Curriculum):
    """dependent_cc_id -> set of prerequisite cc_ids that appear in ANY of its groups
    (used for cycle detection / topo sort; group AND/OR logic doesn't matter for ordering,
    only for eligibility -- a node still structurally depends on all courses named in any
    of its groups)."""
    edges = {}
    for cc_id, node in curriculum.nodes.items():
        deps = set()
        for group in node.prereq_groups:
            for course_id in group.prereq_course_ids:
                dep_cc_id = curriculum.course_id_to_cc_id.get(course_id)
                if dep_cc_id is not None:
                    deps.add(dep_cc_id)
        edges[cc_id] = deps
    return edges


def check_cycles(curriculum: Curriculum):
    """DFS with recursion-stack set. Raises CycleError on any back-edge."""
    edges = _dependency_edges(curriculum)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {cc_id: WHITE for cc_id in curriculum.nodes}
    stack_path = []

    def dfs(u):
        color[u] = GRAY
        stack_path.append(u)
        for v in edges[u]:
            if color[v] == GRAY:
                idx = stack_path.index(v)
                raise CycleError(stack_path[idx:] + [v])
            if color[v] == WHITE:
                dfs(v)
        stack_path.pop()
        color[u] = BLACK

    for cc_id in curriculum.nodes:
        if color[cc_id] == WHITE:
            dfs(cc_id)


def topological_order(curriculum: Curriculum) -> list:
    """Kahn's algorithm. prerequisite before dependent. Assumes check_cycles() already passed."""
    edges = _dependency_edges(curriculum)  # dependent -> {prereqs}
    in_degree = {cc_id: 0 for cc_id in curriculum.nodes}
    dependents_of = {cc_id: [] for cc_id in curriculum.nodes}
    for dependent, prereqs in edges.items():
        in_degree[dependent] = len(prereqs)
        for p in prereqs:
            dependents_of[p].append(dependent)

    queue = sorted([cc_id for cc_id, deg in in_degree.items() if deg == 0],
                    key=lambda cid: curriculum.nodes[cid].code)
    order = []
    while queue:
        u = queue.pop(0)
        order.append(u)
        for v in sorted(dependents_of[u], key=lambda cid: curriculum.nodes[cid].code):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)
    if len(order) != len(curriculum.nodes):
        remaining = set(curriculum.nodes) - set(order)
        raise CycleError(list(remaining))
    return order


def group_satisfied(group, satisfied_course_ids: set) -> bool:
    if group.logic == "AND":
        return all(cid in satisfied_course_ids for cid in group.prereq_course_ids)
    return any(cid in satisfied_course_ids for cid in group.prereq_course_ids)  # OR


def node_prereqs_satisfied(node: CurriculumCourse, satisfied_course_ids: set) -> bool:
    return all(group_satisfied(g, satisfied_course_ids) for g in node.prereq_groups)


def compute_earliest_possible(curriculum: Curriculum, student: StudentState, search_start_sem: int) -> dict:
    """
    Constraint propagation: for every node, compute the earliest semester >= search_start_sem
    at which it could possibly be scheduled, given prerequisite chain depth + offering parity
    ONLY (ignores credit limits / competing slots -- those are checked during search). A node
    already PASSED gets earliest_complete = -1 (never blocks a dependent). This is a LOWER BOUND:
    the real backtracking search may still fail to hit it due to credit/slot contention, but
    nothing can ever be scheduled *before* this bound, so it is what search.py uses to prune.

    Returns {cc_id: (earliest_eligible_sem, earliest_complete_sem)}.
    'earliest_eligible' = earliest semester the course COULD be taken (prereqs satisfiable by then).
    'earliest_complete' = earliest semester it could be marked complete (== earliest matching-parity
    offering at or after earliest_eligible).
    None for either value means "impossible within any bounded horizon we can compute" (e.g. no
    matching offering exists at all, or a prerequisite is itself impossible).
    """
    order = topological_order(curriculum)
    earliest_eligible = {}
    earliest_complete = {}

    for cc_id in order:
        node = curriculum.nodes[cc_id]
        if node.course_id in student.passed_course_ids:
            earliest_eligible[cc_id] = -1
            earliest_complete[cc_id] = -1
            continue

        if not node.prereq_groups:
            ee = search_start_sem
        else:
            group_bounds = []
            for g in node.prereq_groups:
                member_completes = []
                for course_id in g.prereq_course_ids:
                    dep_cc = curriculum.course_id_to_cc_id.get(course_id)
                    if dep_cc is None:
                        member_completes.append(None)  # prereq outside this curriculum -- can't verify
                        continue
                    member_completes.append(earliest_complete.get(dep_cc))
                if g.logic == "AND":
                    if any(v is None for v in member_completes):
                        group_bounds.append(None)
                    else:
                        group_bounds.append(max(member_completes) if member_completes else search_start_sem - 1)
                else:  # OR: only need the earliest of the alternatives
                    finite = [v for v in member_completes if v is not None]
                    group_bounds.append(min(finite) if finite else None)
            if any(b is None for b in group_bounds):
                ee = None
            else:
                ee = max([search_start_sem] + [b + 1 for b in group_bounds])

        earliest_eligible[cc_id] = ee
        if ee is None or node.offering is None:
            earliest_complete[cc_id] = None
            continue
        ec = None
        floor = max(ee, node.nominal_semester) if node.nominal_semester is not None else ee
        for s in range(floor, floor + 40):  # bounded look-ahead; far beyond any realistic horizon
            if node.offering.matches(s, allow_summer=True):
                ec = s
                break
        earliest_complete[cc_id] = ec

    return {cc_id: (earliest_eligible[cc_id], earliest_complete[cc_id]) for cc_id in curriculum.nodes}
