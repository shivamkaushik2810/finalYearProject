from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ["rate_all", "rate_last3", "absent_streak", "history_len", "class_rate"]
FLAG_THRESHOLD = 0.40      # >= this chance of absence -> "high"
MEDIUM_THRESHOLD = 0.20
MIN_ROWS = 40
MIN_PER_CLASS = 6
TRAIN_FRACTION = 0.7


def _session_key(ts):
    return str(ts or "")[:19]


def _features(hist, class_rate):
    """hist: list of 0/1 presence values BEFORE the class being predicted."""
    n = len(hist)
    last3 = hist[-3:]
    streak = 0
    for v in reversed(hist):
        if v == 0:
            streak += 1
        else:
            break
    return [sum(hist) / n, sum(last3) / len(last3), float(streak), min(n, 20) / 20.0, class_rate]


def _collect(logs):
    data = defaultdict(lambda: defaultdict(dict))   # subject -> student -> {session: present}
    sessions = defaultdict(set)
    for l in logs:
        ts = _session_key(l.get("timestamp"))
        sid, sub = l.get("student_id"), l.get("subject_id")
        if not ts or sid is None or sub is None:
            continue
        present = 1 if l.get("is_present") else 0
        data[sub][sid][ts] = max(present, data[sub][sid].get(ts, 0))
        sessions[sub].add(ts)
    return data, {s: sorted(v) for s, v in sessions.items()}


def _build_rows(logs):
    """One row per (student, class) that has at least one earlier class; features use only the past."""
    data, order = _collect(logs)
    rows = []
    for sub, students in data.items():
        sess = order[sub]
        rate_by_ts = {}
        for ts in sess:
            vals = [m[ts] for m in students.values() if ts in m]
            rate_by_ts[ts] = sum(vals) / len(vals) if vals else 1.0

        prior, run = {}, 0.0                       # class attendance rate over earlier sessions only
        for i, ts in enumerate(sess):
            prior[ts] = run / i if i else None
            run += rate_by_ts[ts]

        for sid, m in students.items():
            hist = []
            for ts in sess:
                if ts not in m:
                    continue
                if hist and prior[ts] is not None:
                    rows.append({"x": _features(hist, prior[ts]), "y": 1 - m[ts], "ts": ts})
                hist.append(m[ts])
    return rows


def _pipe():
    return Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))])


def _scores(y, pred):
    return {
        "accuracy":  float(accuracy_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall":    float(recall_score(y, pred, zero_division=0)),
        "f1":        float(f1_score(y, pred, zero_division=0)),
    }


def fit_model(logs):
    rows = _build_rows(logs)
    n = len(rows)
    absent = sum(r["y"] for r in rows)
    present = n - absent
    if n < MIN_ROWS or absent < MIN_PER_CLASS or present < MIN_PER_CLASS:
        return {"status": "insufficient", "n_rows": n,
                "reason": (f"{n} usable class records ({absent} absences, {present} presences); "
                           f"need at least {MIN_ROWS} records with {MIN_PER_CLASS}+ of each outcome")}

    rows.sort(key=lambda r: r["ts"])                 # time-ordered split: train on the past, test on the future
    cut = int(n * TRAIN_FRACTION)
    tr, te = rows[:cut], rows[cut:]
    Xtr, ytr = np.array([r["x"] for r in tr]), np.array([r["y"] for r in tr])
    Xte, yte = np.array([r["x"] for r in te]), np.array([r["y"] for r in te])
    if len(set(ytr.tolist())) < 2:
        return {"status": "insufficient", "n_rows": n,
                "reason": "the earlier classes contain only one outcome (all present or all absent)"}

    pipe = _pipe().fit(Xtr, ytr)
    proba = pipe.predict_proba(Xte)[:, 1]
    model_m = _scores(yte, (proba >= FLAG_THRESHOLD).astype(int))
    last_m = _scores(yte, (Xte[:, 2] >= 1).astype(int))     # rule: absent last class -> absent again
    auc = float(roc_auc_score(yte, proba)) if len(set(yte.tolist())) == 2 else None

    final = _pipe().fit(np.array([r["x"] for r in rows]), np.array([r["y"] for r in rows]))
    return {
        "status": "ok",
        "model": final,
        "n_rows": n, "n_train": len(tr), "n_test": len(te),
        "absent_rate": absent / n,
        "metrics": model_m, "auc": auc,
        "baseline_last": last_m,
        "baseline_majority_accuracy": float(1 - yte.mean()),
        "beats_baseline": model_m["f1"] >= last_m["f1"],
        "coef": dict(zip(FEATURES, final.named_steps["clf"].coef_[0].tolist())),
    }


def predict_students(model, logs, enrolled):
    """Chance of absence at the NEXT class of the subject whose logs are given."""
    data, order = _collect(logs)
    sub_ids = list(data.keys())
    out = []
    if not sub_ids:
        return [{"student_id": s["student_id"], "name": s.get("name", "?"), "sessions": 0,
                 "attendance_pct": None, "p": None, "level": "unknown", "reasons": "No attendance data yet"}
                for s in enrolled]

    sub = sub_ids[0]
    sess = order[sub]
    students = data[sub]
    rates = []
    for ts in sess:
        vals = [m[ts] for m in students.values() if ts in m]
        if vals:
            rates.append(sum(vals) / len(vals))
    class_rate = sum(rates) / len(rates) if rates else 1.0

    scaler, clf = model.named_steps["scale"], model.named_steps["clf"]
    for s in enrolled:
        m = students.get(s["student_id"], {})
        seq = [m[t] for t in sess if t in m]
        if not seq:
            out.append({"student_id": s["student_id"], "name": s.get("name", "?"), "sessions": 0,
                        "attendance_pct": None, "p": None, "level": "unknown", "reasons": "No attendance data yet"})
            continue

        f = _features(seq, class_rate)
        x = np.array([f])
        p = float(model.predict_proba(x)[0, 1])
        contrib = scaler.transform(x)[0] * clf.coef_[0]
        texts = {
            0: f"overall attendance {f[0] * 100:.0f}%",
            1: f"only {f[1] * 100:.0f}% attendance in the last {min(3, len(seq))} class(es)",
            2: f"absent {int(f[2])} class(es) in a row",
            4: f"class-wide attendance is low ({f[4] * 100:.0f}%)",
        }
        picks = [i for i in sorted(texts, key=lambda i: contrib[i], reverse=True) if contrib[i] > 0.15][:2]
        if f[2] == 0 and 2 in picks:
            picks.remove(2)
        level = "high" if p >= FLAG_THRESHOLD else "medium" if p >= MEDIUM_THRESHOLD else "low"
        out.append({
            "student_id": s["student_id"], "name": s.get("name", "?"), "sessions": len(seq),
            "attendance_pct": round(sum(seq) / len(seq) * 100, 1), "p": p, "level": level,
            "reasons": "; ".join(texts[i] for i in picks) if picks else "no strong risk factors",
        })
    return out
