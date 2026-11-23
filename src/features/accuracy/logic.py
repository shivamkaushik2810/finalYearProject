"""Face-recognition accuracy numbers (pure Python, no database, no Streamlit).

Terms:  genuine trial  = a sample compared with the SAME student's enrolled faces
        impostor trial = a sample compared with a DIFFERENT student's enrolled faces
Distance is Euclidean (what face_recognition uses); a trial is accepted when distance < threshold.
FRR = genuine trials rejected / genuine trials.  FAR = impostor trials accepted / impostor trials."""
import math

MIN_PEOPLE = 2


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _best(probe, refs):
    return min(dist(probe, r) for r in refs)


def build_trials(people, max_impostors=20000):
    """people: {id: {"refs": [vec, ...], "probes": [vec, ...]}}.
    Returns (genuine_distances, impostor_distances). Impostors are thinned evenly if there are too many."""
    usable = {k: v for k, v in people.items() if v.get("refs")}
    genuine, impostor = [], []
    for k, v in usable.items():
        for p in v.get("probes") or []:
            genuine.append(_best(p, v["refs"]))
            for k2, v2 in usable.items():
                if k2 != k:
                    impostor.append(_best(p, v2["refs"]))
    if len(impostor) > max_impostors:
        step = len(impostor) / max_impostors
        impostor = [impostor[int(i * step)] for i in range(max_impostors)]
    return genuine, impostor


def rates_at(threshold, genuine, impostor):
    frr = sum(1 for d in genuine if d >= threshold) / len(genuine) if genuine else None
    far = sum(1 for d in impostor if d < threshold) / len(impostor) if impostor else None
    return {"threshold": round(threshold, 4), "far": far, "frr": frr}


def sweep(genuine, impostor, lo=0.2, hi=1.0, step=0.01):
    n = int(round((hi - lo) / step)) + 1
    return [rates_at(lo + i * step, genuine, impostor) for i in range(n)]


def equal_error_rate(rows):
    """Point where FAR and FRR are closest. Returns {"threshold", "eer"} or None."""
    ok = [r for r in rows if r["far"] is not None and r["frr"] is not None]
    if not ok:
        return None
    best = min(ok, key=lambda r: (abs(r["far"] - r["frr"]), r["threshold"]))
    return {"threshold": best["threshold"], "eer": round((best["far"] + best["frr"]) / 2, 4)}


def rank1(people):
    """Share of probes whose nearest enrolled student (over all students) is the right one."""
    usable = {k: v for k, v in people.items() if v.get("refs")}
    hits = total = 0
    for k, v in usable.items():
        for p in v.get("probes") or []:
            nearest = min(usable, key=lambda j: _best(p, usable[j]["refs"]))
            total += 1
            hits += 1 if nearest == k else 0
    return {"probes": total, "correct": hits, "rate": (hits / total) if total else None}


def evaluate(people, threshold):
    """Everything the page shows. status 'insufficient' explains what is missing instead of inventing numbers."""
    usable = {k: v for k, v in people.items() if v.get("refs")}
    with_probes = [k for k, v in usable.items() if v.get("probes")]
    if len(usable) < MIN_PEOPLE or not with_probes:
        return {"status": "insufficient", "students": len(usable), "students_with_samples": len(with_probes),
                "reason": ("Need at least 2 enrolled students and some confirmed attendance samples "
                           f"(have {len(usable)} students, {len(with_probes)} with samples).")}
    genuine, impostor = build_trials(people)
    rows = sweep(genuine, impostor)
    return {"status": "ok", "students": len(usable), "students_with_samples": len(with_probes),
            "genuine": len(genuine), "impostor": len(impostor),
            "at_threshold": rates_at(threshold, genuine, impostor),
            "eer": equal_error_rate(rows), "rank1": rank1(people), "curve": rows}
