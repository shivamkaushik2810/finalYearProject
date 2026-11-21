import unittest
from datetime import date
from unittest.mock import patch

from src.features.alerts import low_attendance as la


def row(sid, sub, total, present):
    return {"pair_key": f"{sid}:{sub}", "student_id": sid, "subject_id": sub,
            "total_classes": total, "present_classes": present}


def person(sid, **kw):
    d = {"student_id": sid, "name": f"S{sid}", "email": f"s{sid}@college.edu", "parent_name": "Par",
         "parent_email": f"p{sid}@gmail.com", "phone": None, "parent_phone": None, "alert_opt_in": False}
    d.update(kw)
    return d


class Env:
    """Replaces every outside dependency of run(): database reads, claim table, mail and SMS."""
    def __init__(self, rows, people, mode="off", fail_to=()):
        self.claimed, self.sent, self.released, self.msgs = set(), [], [], []
        self.rows, self.people, self.mode, self.fail_to = rows, {p["student_id"]: p for p in people}, mode, set(fail_to)

    def claim(self, *k):
        if k in self.claimed:
            return False
        self.claimed.add(k)
        return True

    def send(self, to, subj, html, plain):
        if to in self.fail_to:
            raise RuntimeError("smtp down")
        self.sent.append((to, subj, html, plain))

    def __enter__(self):
        self.ps = [
            patch.object(la, "_view_rows", lambda: self.rows),
            patch.object(la, "_people", lambda ids: {str(k): v for k, v in self.people.items() if str(k) in {str(i) for i in ids}}),
            patch.object(la, "_subject_names", lambda ids: {i: "Maths" for i in ids}),
            patch.object(la.alerts, "claim", self.claim),
            patch.object(la.alerts, "mark_sent", lambda *k: None),
            patch.object(la.alerts, "release", lambda *k: (self.released.append(k), self.claimed.discard(k))),
            patch.object(la.alerts, "channel_mode", lambda: self.mode),
            patch.object(la.alerts, "send_message", lambda ph, t: (self.msgs.append((ph, t)), (True, ""))[1]),
            patch.object(la.mail, "_send", self.send),
        ]
        for p in self.ps:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self.ps:
            p.stop()


WEEK = date(2026, 11, 18)


class GroupLow(unittest.TestCase):
    def test_threshold_boundary_min_classes_and_order(self):
        rows = [row("a", "m", 20, 15), row("a", "p", 20, 14), row("b", "m", 4, 0), row("c", "m", 10, 5),
                row("a", "c", 10, 2), row("d", "m", None, None)]
        out = la.group_low(rows)
        self.assertNotIn("b", out)                       # only 4 classes: too early to judge
        self.assertNotIn("d", out)                       # missing numbers are not zero-percent
        self.assertEqual([i["subject_id"] for i in out["a"]], ["c", "p"])   # 75.0% is NOT low; worst first
        self.assertEqual(out["c"][0]["pct"], 50.0)


class RunJob(unittest.TestCase):
    def test_sends_to_student_and_parent_once_and_retry_is_idempotent(self):
        with Env([row("1", "m", 10, 4)], [person("1")]) as e:
            r1 = la.run(today=WEEK)
            r2 = la.run(today=WEEK)
        self.assertEqual((r1["emails_sent"], r1["flagged"]), (2, 1))
        self.assertEqual((r2["emails_sent"], r2["already_sent"]), (0, 2))
        self.assertEqual(sorted(t[0] for t in e.sent), ["p1@gmail.com", "s1@college.edu"])

    def test_dry_run_sends_and_claims_nothing(self):
        with Env([row("1", "m", 10, 4)], [person("1")]) as e:
            r = la.run(dry_run=True, today=WEEK)
        self.assertEqual((r["emails_sent"], len(e.sent), len(e.claimed)), (2, 0, 0))

    def test_failure_releases_claim_and_does_not_stop_others(self):
        with Env([row("1", "m", 10, 4), row("2", "m", 10, 4)], [person("1"), person("2")], fail_to={"s1@college.edu"}) as e:
            r = la.run(today=WEEK)
        self.assertEqual((r["failed"], r["emails_sent"]), (1, 3))
        self.assertEqual(len(e.released), 1)             # slot freed so the next run retries it

    def test_email_cap_defers_the_rest(self):
        with Env([row(str(i), "m", 10, 4) for i in range(5)], [person(str(i)) for i in range(5)]) as e:
            r = la.run(max_emails=3, today=WEEK)
        self.assertEqual((r["emails_sent"], r["deferred"]), (3, 7))

    def test_parent_same_mailbox_and_invalid_addresses_are_skipped(self):
        people = [person("1", parent_email="s.1@college.edu".replace("s.1", "s1")),     # same as student
                  person("2", email="x@snapclass-test.invalid", parent_email=None)]
        with Env([row("1", "m", 10, 4), row("2", "m", 10, 4)], people) as e:
            r = la.run(today=WEEK)
        self.assertEqual([t[0] for t in e.sent], ["s1@college.edu"])

    def test_messages_only_when_channel_on_and_opted_in(self):
        p = person("1", phone="9876543210", parent_phone="+919812345678", alert_opt_in=True)
        with Env([row("1", "m", 10, 4)], [p], mode="off") as e:
            la.run(today=WEEK)
        self.assertEqual(e.msgs, [])
        with Env([row("1", "m", 10, 4)], [p], mode="whatsapp") as e:
            r = la.run(today=WEEK)
        self.assertEqual((len(e.msgs), r["messages_sent"]), (2, 2))
        self.assertTrue(e.msgs[0][0].startswith("+91"))
        q = person("1", phone="9876543210", alert_opt_in=False)
        with Env([row("1", "m", 10, 4)], [q], mode="sms") as e:
            la.run(today=WEEK)
        self.assertEqual(e.msgs, [])                      # no consent, no message

    def test_names_are_html_escaped(self):
        with Env([row("1", "m", 10, 4)], [person("1", name="<script>x</script>", parent_name="<b>P</b>")]) as e:
            la.run(today=WEEK)
        for _, _, html, _ in e.sent:
            self.assertNotIn("<script>", html)
            self.assertNotIn("<b>P</b>", html)

    def test_nobody_low_means_no_database_lookups(self):
        with Env([row("1", "m", 10, 10)], [person("1")]) as e, \
             patch.object(la, "_people", side_effect=AssertionError("should not be called")):
            self.assertEqual(la.run(today=WEEK)["flagged"], 0)


if __name__ == "__main__":
    unittest.main()
