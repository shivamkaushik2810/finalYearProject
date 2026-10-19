"""Pure calculation engine for the Student Analytics dashboard.
No Streamlit and no database access: functions take plain rows / DataFrames."""
import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd


@dataclass
class AnalyticsConfig:
    attendance_target: float = 75.0
    marks_target: float = 50.0
    min_corr_points: int = 5          # subjects needed for a correlation
    min_subject_classes: int = 5      # classes a subject needs to enter the correlation
    min_hist_points: int = 6
    min_box_points: int = 4           # weeks a subject needs for a box plot
    min_forecast_weeks: int = 10
    min_prob_classes: int = 5
    ma_window: int = 3
    section_min_students: int = 10
    section_min_subject_students: int = 5
    excused_policy: str = "exclude"   # "exclude" (default) or "present"
    external_types: tuple = ("End Term",)
    practical_types: tuple = ("Practical",)
    date_columns: tuple = ("exam_date", "assessment_date", "date", "created_at", "updated_at")


DEFINITIONS = {
    "Overall attendance %": "Classes marked present / classes held x 100. A class held is one attendance record per "
                            "(subject, timestamp); duplicates count once. Classes with no record (cancelled, or before "
                            "enrolment) are not counted. Classes marked cancelled are never counted; classes marked "
                            "excused leave the denominator (policy 'exclude') unless the policy counts them present. "
                            "The 95% interval is the Wilson score interval.",
    "Overall marks %": "Sum of marks obtained / sum of maximum marks over scored assessments (weighted by maximum "
                       "marks, so a 20-mark quiz counts less than a 50-mark exam). Missing marks are excluded, never zero. "
                       "Zero scores flagged unverified are excluded until a teacher confirms them.",
    "Latest assessment": "The most recent dated assessment, as a percentage of its maximum marks. Needs an assessment date.",
    "Change vs previous": "Latest minus the previous assessment of the same subject, in percentage points. Needs dates.",
    "Subjects below target": "Subjects whose attendance % is below the attendance target, or whose marks % is below the marks target.",
    "Data completeness": "Share of the selected enrolled subjects that have both attendance and marks records.",
    "Risk band": "Rule-based, not a probability: critical < target-10, high < target, watch < target+5, else low.",
    "Probability of meeting target": "Beta-binomial posterior predictive probability that final attendance reaches the target "
                                     "after N more classes, with a uniform prior. Assumes future classes behave like past "
                                     "ones. It is a model estimate and has not been validated or calibrated.",
    "Correlation": "Pearson r and Spearman rho across subjects (attendance % vs marks %). Needs at least 5 subjects with "
                   "enough classes. Association only, not causation.",
}


# ───────────────────────── helpers ─────────────────────────

def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return f if math.isfinite(f) else float("nan")


def _to_dt(series):
    return pd.to_datetime(series, utc=True, errors="coerce").dt.tz_localize(None)


def _p(x, d=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x:.{d}f}"


def wilson(k, n, z=1.96):
    """95% Wilson score interval for a proportion, in percent."""
    if n <= 0:
        return None, None
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    a = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return max(0.0, (c - a) / d * 100), min(100.0, (c + a) / d * 100)


def classes_needed(present, total, target):
    """Consecutive further classes that must be attended to reach the target %."""
    if total <= 0:
        return None
    t = target / 100.0
    if present / total >= t:
        return 0
    if t >= 1.0:
        return None
    return int(math.ceil((t * total - present) / (1 - t) - 1e-9))


def risk_band(pct, target):
    if pct is None:
        return "unknown"
    if pct < target - 10:
        return "critical"
    if pct < target:
        return "high"
    if pct < target + 5:
        return "watch"
    return "low"


def _strength(r):
    a = abs(r)
    return ("negligible" if a < 0.2 else "weak" if a < 0.4 else "moderate" if a < 0.6
            else "strong" if a < 0.8 else "very strong")


# ───────────────────────── attendance ─────────────────────────

ATT_COLS = ["subject_id", "subject", "code", "faculty_id", "faculty", "when", "date", "present"]


def normalize_attendance(rows, policy="exclude"):
    """Returns (DataFrame, dropped_rows). One row per (subject, class time); duplicates merged.
    Cancelled classes are never counted. Excused absences are left out (policy 'exclude') or counted present."""
    recs = []
    for r in rows or []:
        status = str(r.get("status") or "").lower()
        if status == "cancelled" or (status == "excused" and policy != "present"):
            continue
        sub = r.get("subjects") or {}
        teacher = sub.get("teachers") or {}
        recs.append({
            "subject_id": r.get("subject_id"), "subject": sub.get("name") or "Unknown",
            "code": sub.get("subject_code") or "", "faculty_id": sub.get("teacher_id"),
            "faculty": teacher.get("name") or "Unknown", "ts": r.get("timestamp"),
            "present": 1 if (r.get("is_present") or status in ("present", "excused")) else 0,
        })
    if not recs:
        return pd.DataFrame(columns=ATT_COLS), 0
    df = pd.DataFrame(recs)
    df["when"] = _to_dt(df["ts"])
    mask = df["when"].isna() | df["subject_id"].isna()
    dropped = int(mask.sum())
    df = df[~mask]
    if df.empty:
        return pd.DataFrame(columns=ATT_COLS), dropped
    df["when"] = df["when"].dt.floor("s")
    df = (df.groupby(["subject_id", "when"], as_index=False)
            .agg(subject=("subject", "first"), code=("code", "first"), faculty_id=("faculty_id", "first"),
                 faculty=("faculty", "first"), present=("present", "max")))
    df["date"] = df["when"].dt.normalize()
    return df.sort_values("when").reset_index(drop=True)[ATT_COLS], dropped


def count_status(rows):
    """Distinct excused / cancelled classes in the raw rows."""
    seen = {"excused": set(), "cancelled": set()}
    for r in rows or []:
        s = str(r.get("status") or "").lower()
        if s in seen:
            seen[s].add((r.get("subject_id"), str(r.get("timestamp"))[:19]))
    return {k: len(v) for k, v in seen.items()}


def count_unverified(rows):
    return sum(1 for r in rows or [] if str(r.get("entry_status") or "").lower() == "unverified")


def count_status(rows):
    """Distinct excused / cancelled classes in the raw rows."""
    seen = {"excused": set(), "cancelled": set()}
    for r in rows or []:
        s = str(r.get("status") or "").lower()
        if s in seen:
            seen[s].add((r.get("subject_id"), str(r.get("timestamp"))[:19]))
    return {k: len(v) for k, v in seen.items()}


def count_unverified(rows):
    return sum(1 for r in rows or [] if str(r.get("entry_status") or "").lower() == "unverified")


def attendance_summary(df, cfg):
    n = int(len(df))
    p = int(df["present"].sum()) if n else 0
    lo, hi = wilson(p, n)
    pct = round(p / n * 100, 1) if n else None
    return {"classes": n, "present": p, "absent": n - p, "pct": pct, "ci_low": lo, "ci_high": hi,
            "classes_needed": classes_needed(p, n, cfg.attendance_target) if n else None,
            "risk": risk_band(pct, cfg.attendance_target)}


SUBJ_ATT_COLS = ["subject_id", "subject", "code", "faculty", "classes", "present", "absent", "pct",
                 "classes_needed", "below_target"]


def by_subject_attendance(df, cfg):
    if df.empty:
        return pd.DataFrame(columns=SUBJ_ATT_COLS)
    out = (df.groupby("subject_id", as_index=False)
             .agg(subject=("subject", "first"), code=("code", "first"), faculty=("faculty", "first"),
                  classes=("present", "size"), present=("present", "sum")))
    out["absent"] = out["classes"] - out["present"]
    out["pct"] = (out["present"] / out["classes"] * 100).round(1)
    out["classes_needed"] = [classes_needed(int(p), int(c), cfg.attendance_target)
                             for p, c in zip(out["present"], out["classes"])]
    out["below_target"] = out["pct"] < cfg.attendance_target
    return out[SUBJ_ATT_COLS]


def faculty_attendance(df):
    cols = ["faculty", "classes", "present", "pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    d = df[df["faculty"] != "Unknown"]
    if d.empty:
        return pd.DataFrame(columns=cols)
    out = d.groupby("faculty", as_index=False).agg(classes=("present", "size"), present=("present", "sum"))
    out["pct"] = (out["present"] / out["classes"] * 100).round(1)
    return out[cols]


WEEK_COLS = ["week", "classes", "present", "pct", "ma"]


def weekly_attendance(df, window=3):
    if df.empty:
        return pd.DataFrame(columns=WEEK_COLS)
    d = df.copy()
    d["week"] = d["when"].dt.to_period("W-SUN").dt.start_time
    w = d.groupby("week", as_index=False).agg(classes=("present", "size"), present=("present", "sum"))
    w["pct"] = w["present"] / w["classes"] * 100
    rp = w["present"].rolling(window, min_periods=window).sum()
    rc = w["classes"].rolling(window, min_periods=window).sum()
    w["ma"] = rp / rc * 100
    return w[WEEK_COLS]


def monthly_attendance(df):
    cols = ["month", "classes", "present", "pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    d = df.copy()
    d["month"] = d["when"].dt.to_period("M").dt.start_time
    m = d.groupby("month", as_index=False).agg(classes=("present", "size"), present=("present", "sum"))
    m["pct"] = m["present"] / m["classes"] * 100
    return m[cols]


def absence_streaks(df):
    cols = ["subject_id", "subject", "longest", "current"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for sid, g in df.sort_values("when").groupby("subject_id"):
        longest = cur = 0
        for v in g["present"]:
            if v == 0:
                cur += 1
                longest = max(longest, cur)
            else:
                cur = 0
        rows.append({"subject_id": sid, "subject": g["subject"].iloc[0], "longest": longest, "current": cur})
    return pd.DataFrame(rows, columns=cols)


# ───────────────────────── marks ─────────────────────────

MARK_COLS = ["student_id", "subject_id", "subject", "code", "faculty", "exam_type", "obtained", "max_marks",
             "pct", "remarks", "when", "zero_flag"]


def find_date_column(rows, candidates):
    for c in candidates:
        if any(r.get(c) for r in rows):
            return c
    return None


def normalize_marks(rows, cfg):
    """Returns (DataFrame of valid scored rows, excluded_row_count, date_column_or_None).
    Missing / invalid marks are excluded, never treated as zero."""
    rows = list(rows or [])
    date_col = find_date_column(rows, cfg.date_columns)
    recs = []
    for r in rows:
        sub = r.get("subjects") or {}
        teacher = sub.get("teachers") or {}
        got, mx = _num(r.get("marks_obtained")), _num(r.get("max_marks"))
        valid = (not math.isnan(got)) and (not math.isnan(mx)) and mx > 0 and 0 <= got <= mx
        if str(r.get("entry_status") or "").lower() == "unverified":
            valid = False
        if str(r.get("entry_status") or "").lower() == "unverified":
            valid = False
        remarks = str(r.get("remarks") or "").strip()

        # Pick the first available date for THIS row.
        date_candidates = list(dict.fromkeys([*cfg.date_columns, "created_at"]))
        raw_date = next(
            (
                r.get(c)
                for c in date_candidates
                if r.get(c) is not None and str(r.get(c)).strip()
            ),
            None,
        )

        recs.append({
            "student_id": r.get("student_id"), "subject_id": r.get("subject_id"),
            "subject": sub.get("name") or "Unknown", "code": sub.get("subject_code") or "",
            "faculty": teacher.get("name") or "Unknown", "exam_type": r.get("exam_type") or "Other",
            "obtained": got if valid else float("nan"), "max_marks": mx if valid else float("nan"),
            "pct": got / mx * 100 if valid else float("nan"), "remarks": remarks,
            "when": next(
                (
                    r.get(c)
                    for c in dict.fromkeys([*cfg.date_columns, "created_at"])
                    if r.get(c) is not None and str(r.get(c)).strip()
                ),
                None,
            ),
            "zero_flag": bool(valid and got == 0 and not remarks and r.get("entry_status") is None), "valid": valid,
        })
    if not recs:
        return pd.DataFrame(columns=MARK_COLS), 0, date_col
    df = pd.DataFrame(recs)
    invalid = int((~df["valid"]).sum())
    df = df[df["valid"]].drop(columns="valid").reset_index(drop=True)
    df["when"] = pd.to_datetime(
        df["when"].map(
            lambda value: pd.to_datetime(
                value, utc=True, errors="coerce"
            )
        ),
        utc=True,
        errors="coerce",
    ).dt.tz_localize(None)
    return df[MARK_COLS], invalid, date_col


def filter_marks(df, start=None, end=None, subject_ids=None, exam_types=None):
    d = df
    if subject_ids is not None:
        d = d[d["subject_id"].isin(list(subject_ids))]
    if exam_types:
        d = d[d["exam_type"].isin(list(exam_types))]
    if (start or end) and not d.empty and d["when"].notna().any():
        if start:
            d = d[d["when"] >= pd.Timestamp(start)]
        if end:
            d = d[d["when"] < pd.Timestamp(end) + pd.Timedelta(days=1)]
    return d.reset_index(drop=True)


def marks_summary(df, cfg):
    n = int(len(df))
    if n == 0:
        return {"n": 0}
    pct = df["pct"].astype(float)
    s = {"n": n, "weighted_pct": round(float(df["obtained"].sum() / df["max_marks"].sum() * 100), 1),
         "mean": round(float(pct.mean()), 1), "median": round(float(pct.median()), 1),
         "min": round(float(pct.min()), 1), "max": round(float(pct.max()), 1)}
    s["range"] = round(s["max"] - s["min"], 1)
    if n >= 2:
        s["std"] = round(float(pct.std(ddof=1)), 2)
        s["variance"] = round(float(pct.var(ddof=1)), 2)
    vc = pct.round().value_counts()
    if len(vc) and vc.iloc[0] >= 2 and (len(vc) == 1 or vc.iloc[0] > vc.iloc[1]):
        s["mode"] = float(vc.index[0])
    s["outliers"] = []
    if n >= 4:
        q1, q3 = float(pct.quantile(0.25)), float(pct.quantile(0.75))
        s.update(q1=round(q1, 1), q3=round(q3, 1), iqr=round(q3 - q1, 1))
        if n >= 5 and q3 > q1:
            lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
            for _, r in df[(pct < lo) | (pct > hi)].iterrows():
                s["outliers"].append({"subject": r["subject"], "exam_type": r["exam_type"], "pct": round(float(r["pct"]), 1)})
    if n >= 4 and "std" in s:
        s["consistency"] = "consistent" if s["std"] <= 8 else "moderately variable" if s["std"] <= 15 else "highly variable"
    return s


def by_subject_marks(df):
    cols = ["subject_id", "subject", "assessments", "obtained", "max_marks", "marks_pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    out = (df.groupby("subject_id", as_index=False)
             .agg(subject=("subject", "first"), assessments=("pct", "size"),
                  obtained=("obtained", "sum"), max_marks=("max_marks", "sum")))
    out["marks_pct"] = (out["obtained"] / out["max_marks"] * 100).round(1)
    return out[cols]


def by_exam_type(df):
    cols = ["exam_type", "assessments", "pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    out = (df.groupby("exam_type", as_index=False)
             .agg(assessments=("pct", "size"), obtained=("obtained", "sum"), max_marks=("max_marks", "sum")))
    out["pct"] = (out["obtained"] / out["max_marks"] * 100).round(1)
    return out[cols]


def marks_by_category(df, cfg):
    empty = pd.DataFrame(columns=["group", "assessments", "pct"])
    if df.empty:
        return {"internal_external": empty, "theory_practical": empty}
    d = df.copy()
    d["ie"] = np.where(d["exam_type"].isin(cfg.external_types), "External", "Internal")
    d["tp"] = np.where(d["exam_type"].isin(cfg.practical_types), "Practical", "Theory / other")
    out = {}
    for key, col in (("internal_external", "ie"), ("theory_practical", "tp")):
        g = (d.groupby(col, as_index=False)
               .agg(assessments=("pct", "size"), obtained=("obtained", "sum"), max_marks=("max_marks", "sum"))
               .rename(columns={col: "group"}))
        g["pct"] = (g["obtained"] / g["max_marks"] * 100).round(1)
        out[key] = g[["group", "assessments", "pct"]]
    return out


def latest_result(df):
    d = df.dropna(subset=["when"])
    if d.empty:
        return None
    last = d.sort_values("when").iloc[-1]
    earlier = d[(d["subject_id"] == last["subject_id"]) & (d["when"] < last["when"])]
    change, prev_exam = None, None
    if not earlier.empty:
        prev = earlier.sort_values("when").iloc[-1]
        change, prev_exam = round(float(last["pct"] - prev["pct"]), 1), prev["exam_type"]
    return {"subject": last["subject"], "exam_type": last["exam_type"], "pct": round(float(last["pct"]), 1),
            "when": last["when"], "change": change, "previous_exam": prev_exam}


def marks_trend(df, cfg):
    d = df.dropna(subset=["when"]).sort_values("when")
    if len(d) < 4:
        return {"status": "insufficient", "reason": f"{len(d)} dated assessment(s); at least 4 are needed."}
    x = (d["when"] - d["when"].iloc[0]).dt.total_seconds().to_numpy() / 86400.0
    if x.max() < 14:
        return {"status": "insufficient", "reason": "The assessments span less than 14 days."}
    slope = float(np.polyfit(x, d["pct"].astype(float).to_numpy(), 1)[0])
    return {"status": "ok", "slope_per_30_days": round(slope * 30, 2), "n": int(len(d)),
            "note": "Slope mixes subjects of different difficulty; read it as a rough direction only."}


def declining_subjects(df, min_drop=5.0):
    out = []
    d = df.dropna(subset=["when"])
    for _, g in d.sort_values("when").groupby("subject_id"):
        v = g["pct"].astype(float).tolist()
        if len(v) >= 3 and v[-3] > v[-2] > v[-1] and (v[-3] - v[-1]) >= min_drop:
            out.append({"subject": g["subject"].iloc[0], "values": [round(x, 1) for x in v[-3:]]})
    return out


# ───────────────────────── marks vs attendance ─────────────────────────

def attendance_marks_pairs(att_sub, mk_sub, cfg):
    cols = ["subject_id", "subject", "pct", "marks_pct", "classes", "assessments"]
    if att_sub.empty or mk_sub.empty:
        return pd.DataFrame(columns=cols)
    p = (att_sub[["subject_id", "subject", "pct", "classes"]]
         .merge(mk_sub[["subject_id", "marks_pct", "assessments"]], on="subject_id"))
    p = p[p["classes"] >= cfg.min_subject_classes].reset_index(drop=True)
    return p[cols]


def correlation(pairs, cfg):
    n = int(len(pairs))
    if n < cfg.min_corr_points:
        return {"status": "insufficient", "n": n,
                "reason": f"{n} subject(s) have both attendance (>= {cfg.min_subject_classes} classes) and marks; "
                          f"at least {cfg.min_corr_points} are needed."}
    x, y = pairs["pct"].astype(float), pairs["marks_pct"].astype(float)
    if x.std(ddof=0) == 0 or y.std(ddof=0) == 0:
        return {"status": "insufficient", "n": n, "reason": "One of the series has no variation."}
    r = float(np.corrcoef(x, y)[0, 1])
    rho = float(x.rank().corr(y.rank()))
    z = math.atanh(max(min(r, 0.999999), -0.999999))
    se = 1 / math.sqrt(n - 3)
    return {"status": "ok", "n": n, "pearson": round(r, 2), "spearman": round(rho, 2),
            "ci_low": round(math.tanh(z - 1.96 * se), 2), "ci_high": round(math.tanh(z + 1.96 * se), 2),
            "strength": _strength(r)}


def section_comparison(sec_df, student_id, cfg):
    if sec_df.empty:
        return {"status": "insufficient", "reason": "No marks recorded for the section."}
    g = sec_df.groupby("student_id").agg(o=("obtained", "sum"), mx=("max_marks", "sum"))
    g["pct"] = g["o"] / g["mx"] * 100
    n = int(len(g))
    if n < cfg.section_min_students:
        return {"status": "insufficient", "n": n,
                "reason": f"Only {n} section student(s) have marks; at least {cfg.section_min_students} are needed."}
    if student_id not in g.index:
        return {"status": "insufficient", "n": n, "reason": "The selected student has no marks in this selection."}
    mine, mean, sd = float(g.loc[student_id, "pct"]), float(g["pct"].mean()), float(g["pct"].std(ddof=1))
    z = (mine - mean) / sd if sd > 0 else None
    below, equal = int((g["pct"] < mine).sum()), int((g["pct"] == mine).sum())
    sub = (sec_df.groupby("subject_id")
                 .agg(o=("obtained", "sum"), mx=("max_marks", "sum"), students=("student_id", "nunique"))
                 .reset_index())
    sub = sub[sub["students"] >= cfg.section_min_subject_students].copy()
    sub["section_mean_pct"] = (sub["o"] / sub["mx"] * 100).round(1)
    return {"status": "ok", "n": n, "student_pct": round(mine, 1), "section_mean": round(mean, 1),
            "section_sd": round(sd, 2), "z": None if z is None else round(z, 2),
            "percentile": round((below + 0.5 * equal) / n * 100, 1),
            "per_subject": sub[["subject_id", "students", "section_mean_pct"]]}


# ───────────────────────── forecasting & risk ─────────────────────────

def _tcrit(dof):
    table = [(8, 2.306), (9, 2.262), (10, 2.228), (12, 2.179), (15, 2.131), (20, 2.086), (30, 2.042)]
    for d, t in table:
        if dof <= d:
            return t
    return 1.96


def forecast_attendance(weekly, cfg, horizon=4):
    n = int(len(weekly))
    if n < cfg.min_forecast_weeks:
        return {"status": "insufficient", "n": n,
                "reason": f"{n} week(s) of data; at least {cfg.min_forecast_weeks} are needed for a forecast."}
    y = weekly["pct"].to_numpy(float)
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (intercept + slope * x)
    dof = n - 2
    s = math.sqrt(float((resid ** 2).sum()) / dof)
    xbar, sxx, t = x.mean(), float(((x - xbar) ** 2).sum()) if False else float(((x - x.mean()) ** 2).sum()), _tcrit(dof)
    last_week = weekly["week"].iloc[-1]
    clip = lambda v: float(min(100.0, max(0.0, v)))
    future = []
    for h in range(1, horizon + 1):
        xi = n - 1 + h
        pred = intercept + slope * xi
        half = t * s * math.sqrt(1 + 1 / n + (xi - x.mean()) ** 2 / sxx)
        future.append({"week": last_week + pd.Timedelta(weeks=h), "pred": clip(pred),
                       "low": clip(pred - half), "high": clip(pred + half)})
    err_m, err_n = [], []
    for k in (3, 2, 1):                       # rolling-origin backtest on the last 3 weeks
        tr = y[: n - k]
        sl, ic = np.polyfit(np.arange(len(tr), dtype=float), tr, 1)
        err_m.append(abs(y[n - k] - (ic + sl * (n - k))))
        err_n.append(abs(y[n - k] - tr[-1]))
    mae_m, mae_n = float(np.mean(err_m)), float(np.mean(err_n))
    return {"status": "ok", "n": n, "slope_per_week": round(float(slope), 2), "forecast": future,
            "mae": round(mae_m, 1), "naive_mae": round(mae_n, 1), "beats_naive": mae_m < mae_n,
            "note": "Linear trend on weekly attendance; interval is an approximate 95% prediction interval."}


def prob_meet_target(present, total, remaining, target, min_classes=5):
    """P(final attendance >= target) after `remaining` more classes (beta-binomial, uniform prior)."""
    if total < min_classes or remaining <= 0:
        return None
    a, b = present + 1, total - present + 1
    kmin = math.ceil(target / 100 * (total + remaining) - 1e-9) - present
    if kmin <= 0:
        return 1.0
    if kmin > remaining:
        return 0.0

    def lbeta(x, y):
        return math.lgamma(x) + math.lgamma(y) - math.lgamma(x + y)

    pr = 0.0
    for k in range(kmin, remaining + 1):
        lp = (math.lgamma(remaining + 1) - math.lgamma(k + 1) - math.lgamma(remaining - k + 1)
              + lbeta(k + a, remaining - k + b) - lbeta(a, b))
        pr += math.exp(lp)
    return min(1.0, pr)


def attendance_scenarios(present, total, target, remaining_options):
    rows = []
    for r in remaining_options:
        need = max(0, math.ceil(target / 100 * (total + r) - 1e-9) - present)
        rows.append({"remaining_classes": r, "must_attend": need if need <= r else None, "feasible": need <= r,
                     "pct_if_all_attended": round((present + r) / (total + r) * 100, 1),
                     "pct_if_half_attended": round((present + r * 0.5) / (total + r) * 100, 1),
                     "pct_if_none_attended": round(present / (total + r) * 100, 1)})
    return pd.DataFrame(rows)


# ───────────────────────── completeness, assembly ─────────────────────────

def subject_summary(att_sub, mk_sub):
    if att_sub.empty and mk_sub.empty:
        return pd.DataFrame()
    a = att_sub.rename(columns={"pct": "attendance_pct"})
    k = mk_sub.rename(columns={"subject": "subject_m"})[["subject_id", "subject_m", "assessments", "marks_pct"]]
    s = a.merge(k, on="subject_id", how="outer")
    s["subject"] = s["subject"].fillna(s["subject_m"])
    return s.drop(columns=["subject_m"])


def build_completeness(enrolled, att, marks, att_dropped, marks_invalid, date_col, zero_scores,
                       excused=0, cancelled=0, unverified=0):
    ids = {s["subject_id"] for s in enrolled}
    att_ids = set(att["subject_id"]) if not att.empty else set()
    mk_ids = set(marks["subject_id"]) if not marks.empty else set()
    both = ids & att_ids & mk_ids
    last_att = att["when"].max() if not att.empty else None
    last_mk = marks["when"].max() if (not marks.empty and marks["when"].notna().any()) else None
    return {"selected_subjects": len(ids), "with_attendance": len(ids & att_ids), "with_marks": len(ids & mk_ids),
            "with_both": len(both), "score": round(len(both) / len(ids) * 100) if ids else None,
            "attendance_rows_dropped": att_dropped, "marks_rows_excluded": marks_invalid,
            "marks_date_column": date_col, "zero_scores_without_remarks": zero_scores,
            "last_attendance": last_att, "last_marks": last_mk,
            "excused_excluded": excused, "cancelled_excluded": cancelled, "unverified_marks": unverified}


def compute_all(att_rows, marks_rows, section_rows, enrolled_subjects, student_id, cfg=None,
                start=None, end=None, subject_ids=None, exam_types=None, generated_at=None, section_agg=None):
    cfg = cfg or AnalyticsConfig()
    att, att_dropped = normalize_attendance(att_rows, cfg.excused_policy)
    status_counts = count_status(att_rows)
    unverified = count_unverified(marks_rows)
    marks_all, marks_invalid, date_col = normalize_marks(marks_rows, cfg)
    marks = filter_marks(marks_all, start, end, subject_ids, exam_types)
    if section_agg is not None:
        sec = section_agg.copy()
        if not sec.empty:
            sec["student_id"] = sec["student_id"].astype(str)
        sid_key = str(student_id)
    else:
        sec_all, _, _ = normalize_marks(section_rows, cfg)
        sec = filter_marks(sec_all, start, end, subject_ids, exam_types)
        sid_key = student_id

    att_sub, mk_sub = by_subject_attendance(att, cfg), by_subject_marks(marks)
    pairs = attendance_marks_pairs(att_sub, mk_sub, cfg)
    weekly = weekly_attendance(att, cfg.ma_window)
    zero_scores = int(marks["zero_flag"].sum()) if not marks.empty else 0

    m = {
        "cfg": cfg,
        "meta": {"generated_at": generated_at or datetime.now(),
                 "period_start": att["when"].min().strftime("%d %b %Y") if not att.empty else None,
                 "period_end": att["when"].max().strftime("%d %b %Y") if not att.empty else None,
                 "start_filter": start, "end_filter": end, "exam_types": list(exam_types or []),
                 "marks_date_column": date_col},
        "att": attendance_summary(att, cfg), "att_df": att, "att_by_subject": att_sub,
        "faculty": faculty_attendance(att), "streaks": absence_streaks(att),
        "weekly": weekly, "monthly": monthly_attendance(att),
        "marks": marks_summary(marks, cfg), "marks_df": marks, "marks_by_subject": mk_sub,
        "marks_by_exam": by_exam_type(marks), "marks_categories": marks_by_category(marks, cfg),
        "latest": latest_result(marks), "trend": marks_trend(marks, cfg), "declines": declining_subjects(marks),
        "pairs": pairs, "corr": correlation(pairs, cfg),
        "forecast": forecast_attendance(weekly, cfg),
        "section": section_comparison(sec, sid_key, cfg),
        "completeness": build_completeness(enrolled_subjects, att, marks, att_dropped, marks_invalid, date_col, zero_scores,
                                           excused=status_counts["excused"], cancelled=status_counts["cancelled"],
                                           unverified=unverified),
    }
    m["subjects_below"] = {
        "attendance": att_sub[att_sub["below_target"]].sort_values("pct").to_dict("records") if not att_sub.empty else [],
        "marks": mk_sub[mk_sub["marks_pct"] < cfg.marks_target].sort_values("marks_pct").to_dict("records") if not mk_sub.empty else [],
    }
    m["insights"] = generate_insights(m, cfg)
    return m


# ───────────────────────── insights (deterministic, grounded in verified metrics) ─────────────────────────

def generate_insights(m, cfg):
    out = []

    def add(level, title, text, evidence, next_step=""):
        out.append({"level": level, "title": title, "text": text, "evidence": evidence, "next_step": next_step})

    att, T = m["att"], cfg.attendance_target
    period = (f"{m['meta']['period_start']} to {m['meta']['period_end']}" if m["meta"]["period_start"] else "the selected period")

    if att["classes"] == 0:
        add("info", "No attendance data", "No attendance records match the selected filters.",
            ["Classes held = 0"], "Check the filters, or whether attendance has been recorded.")
    else:
        ev = [f"Attendance = {att['present']}/{att['classes']} classes = {_p(att['pct'])}% "
              f"(95% interval {_p(att['ci_low'])}-{_p(att['ci_high'])}%)", f"Period: {period}"]
        if att["pct"] < T:
            need = att["classes_needed"]
            tail = (f" Attending the next {need} classes in a row would reach the {T:.0f}% target." if need else "")
            add("alert" if att["risk"] in ("critical", "high") else "warn",
                f"Attendance is below the {T:.0f}% target",
                f"Overall attendance is {_p(att['pct'])}% ({att['present']} of {att['classes']} classes).{tail}",
                ev, "Discuss the shortfall with the student. The classes-needed figure assumes no further absences.")
        else:
            add("good", "Attendance meets the target",
                f"Overall attendance is {_p(att['pct'])}%, at or above the {T:.0f}% target.", ev)

    low = m["subjects_below"]["attendance"]
    if low:
        add("warn", f"{len(low)} subject(s) below the attendance target",
            "Lowest: " + "; ".join(f"{s['subject']} {_p(s['pct'])}%" for s in low[:3]),
            [f"{s['subject']}: {s['present']}/{s['classes']} = {_p(s['pct'])}% (needs {s['classes_needed']} more)" for s in low],
            "Prioritise these subjects when planning support.")

    st_df = m["streaks"]
    if not st_df.empty:
        cur = st_df[st_df["current"] >= 3]
        if not cur.empty:
            add("warn", "Ongoing consecutive absences",
                "Currently absent for 3 or more classes in a row in: " + ", ".join(cur["subject"]),
                [f"{r['subject']}: current streak {r['current']}, longest {r['longest']}" for _, r in cur.iterrows()],
                "Contact the student about the recent absences.")
        elif int(st_df["longest"].max()) >= 3:
            worst = st_df.sort_values("longest").iloc[-1]
            add("info", "Earlier absence streak",
                f"Longest streak: {int(worst['longest'])} classes in {worst['subject']}; not ongoing.",
                [f"{worst['subject']}: longest streak {int(worst['longest'])}, current {int(worst['current'])}"])

    mk = m["marks"]
    if mk["n"] == 0:
        add("info", "No marks data", "No scored assessments match the selected filters. Missing marks are not treated as zero.",
            ["Scored assessments = 0"])
    else:
        ev = [f"Marks = {_p(mk['weighted_pct'])}% across {mk['n']} assessment(s) (weighted by maximum marks)",
              f"Mean {_p(mk['mean'])}%, median {_p(mk['median'])}%, range {_p(mk['min'])}-{_p(mk['max'])}%"]
        if mk["weighted_pct"] < cfg.marks_target:
            add("warn", f"Marks are below the {cfg.marks_target:.0f}% target",
                f"Overall marks are {_p(mk['weighted_pct'])}%.", ev, "Review which subjects need academic support.")
        else:
            add("good", "Marks meet the target", f"Overall marks are {_p(mk['weighted_pct'])}%.", ev)
        lowm = m["subjects_below"]["marks"]
        if lowm:
            add("warn", f"{len(lowm)} subject(s) below the marks target",
                "Lowest: " + "; ".join(f"{s['subject']} {_p(s['marks_pct'])}%" for s in lowm[:3]),
                [f"{s['subject']}: {_p(s['obtained'], 0)}/{_p(s['max_marks'], 0)} = {_p(s['marks_pct'])}%" for s in lowm])
        if mk.get("consistency") == "highly variable":
            add("info", "Scores vary widely",
                f"Assessment scores have a standard deviation of {_p(mk['std'])} points, so results are uneven.",
                [f"Standard deviation = {_p(mk['std'])} points over {mk['n']} assessments"])
        if mk["outliers"]:
            add("info", "Unusual scores", "Scores outside 1.5 x IQR: " +
                "; ".join(f"{o['subject']} ({o['exam_type']}) {o['pct']}%" for o in mk["outliers"]),
                [f"{o['subject']} - {o['exam_type']}: {o['pct']}%" for o in mk["outliers"]],
                "Check these entries for data errors before drawing conclusions.")

    for d in m["declines"]:
        add("warn", f"Declining scores in {d['subject']}",
            f"The last three assessments fell: {' -> '.join(str(v) + '%' for v in d['values'])}.",
            [f"{d['subject']} last three scores: {d['values']}"], "Discuss recent difficulties in this subject.")
    lat = m["latest"]
    if lat and lat["change"] is not None and lat["change"] <= -10:
        add("warn", "Sharp drop in the latest result",
            f"{lat['subject']} ({lat['exam_type']}) scored {lat['pct']}%, {abs(lat['change'])} points below the previous "
            f"{lat['previous_exam']} result.", [f"Latest {lat['pct']}%, change {lat['change']:+.1f} points"])

    c = m["corr"]
    if c["status"] == "ok":
        direction = "positive" if c["pearson"] > 0 else "negative"
        add("info", "Attendance and marks",
            f"Across {c['n']} subjects, attendance and marks show a {c['strength']} {direction} association "
            f"(r = {c['pearson']}). This is an association only; it does not show that attendance causes the marks.",
            [f"Pearson r = {c['pearson']} (95% interval {c['ci_low']} to {c['ci_high']}), Spearman rho = {c['spearman']}, n = {c['n']} subjects"])
    else:
        add("info", "Attendance vs marks not analysed", c["reason"], [f"Subjects available: {c.get('n', 0)}"])

    s = m["section"]
    if s["status"] == "ok" and s["z"] is not None:
        ev = [f"Student {s['student_pct']}% vs section mean {s['section_mean']}% (SD {s['section_sd']}, n = {s['n']})",
              f"z-score = {s['z']}, percentile rank = {s['percentile']}"]
        if s["z"] <= -1:
            add("warn", "Below the section average", f"Marks are {abs(s['z']):.1f} standard deviations below the section mean.", ev)
        elif s["z"] >= 1:
            add("good", "Above the section average", f"Marks are {s['z']:.1f} standard deviations above the section mean.", ev)
        else:
            add("info", "Close to the section average", "Marks are within one standard deviation of the section mean.", ev)

    comp = m["completeness"]
    if comp.get("unverified_marks"):
        add("info", "Unverified zero scores excluded",
            f"{comp['unverified_marks']} score(s) of exactly 0 with no remarks are marked unverified and left out "
            "of every calculation until a teacher re-enters or confirms them.",
            [f"Unverified marks = {comp['unverified_marks']}"], "Ask the teacher to confirm these entries.")
    if comp.get("excused_excluded") or comp.get("cancelled_excluded"):
        add("info", "Excused and cancelled classes",
            f"{comp.get('excused_excluded', 0)} excused class(es) and {comp.get('cancelled_excluded', 0)} cancelled "
            "class(es) were left out of the attendance percentage.",
            [f"Excused = {comp.get('excused_excluded', 0)}", f"Cancelled = {comp.get('cancelled_excluded', 0)}"])
    if comp["zero_scores_without_remarks"]:
        add("info", "Possible placeholder zeros",
            f"{comp['zero_scores_without_remarks']} assessment(s) are scored exactly 0 with no remarks. "
            "The marks screen saves 0 for every student, so these may be unentered marks rather than real zeros.",
            [f"Zero scores without remarks = {comp['zero_scores_without_remarks']}"], "Verify these entries.")
    if comp["marks_rows_excluded"] or comp["attendance_rows_dropped"]:
        add("info", "Some records were excluded",
            f"{comp['marks_rows_excluded']} marks row(s) and {comp['attendance_rows_dropped']} attendance row(s) "
            "were excluded because they were incomplete or invalid.",
            [f"Marks rows excluded = {comp['marks_rows_excluded']}", f"Attendance rows excluded = {comp['attendance_rows_dropped']}"])
    return out


def build_llm_payload(m):
    """Minimal, anonymised payload for a future model call: no name, roll number, faculty or IDs."""
    a, mk, c = m["att"], m["marks"], m["corr"]
    return {
        "period": {"start": m["meta"]["period_start"], "end": m["meta"]["period_end"]},
        "targets": {"attendance": m["cfg"].attendance_target, "marks": m["cfg"].marks_target},
        "attendance": {k: a[k] for k in ("classes", "present", "pct", "classes_needed", "risk")},
        "marks": {k: mk.get(k) for k in ("n", "weighted_pct", "mean", "median", "std", "min", "max")},
        "subjects": [{"subject": r["subject"], "attendance_pct": r.get("attendance_pct"), "marks_pct": r.get("marks_pct")}
                     for r in subject_summary(m["att_by_subject"], m["marks_by_subject"]).to_dict("records")],
        "correlation": {k: c.get(k) for k in ("status", "n", "pearson", "spearman", "strength")},
        "verified_insights": [{"title": i["title"], "evidence": i["evidence"]} for i in m["insights"]],
    }


def export_tables(m):
    att = m["att_df"]
    return {
        "Subject summary": subject_summary(m["att_by_subject"], m["marks_by_subject"]).drop(columns=["subject_id"], errors="ignore"),
        "Weekly attendance": m["weekly"],
        "Monthly attendance": m["monthly"],
        "Assessments": m["marks_df"][["subject", "exam_type", "obtained", "max_marks", "pct", "when", "remarks"]] if not m["marks_df"].empty else m["marks_df"],
        "Absence streaks": m["streaks"].drop(columns=["subject_id"], errors="ignore"),
        "Attendance records": att[["when", "subject", "present"]] if not att.empty else att,
    }
