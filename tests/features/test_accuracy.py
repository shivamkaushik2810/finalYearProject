import unittest

from src.features.accuracy import logic as L


def people(**kw):
    return {k: {"refs": v[0], "probes": v[1]} for k, v in kw.items()}


class Accuracy(unittest.TestCase):
    SEPARATED = people(a=([[0, 0]], [[0.1, 0], [0, 0.2]]), b=([[5, 5]], [[5.1, 5]]))

    def test_insufficient_data_says_so(self):
        self.assertEqual(L.evaluate({}, 0.55)["status"], "insufficient")
        self.assertEqual(L.evaluate(people(a=([[0, 0]], [[0, 0]])), 0.55)["status"], "insufficient")
        self.assertEqual(L.evaluate(people(a=([[0, 0]], []), b=([[1, 1]], [])), 0.55)["status"], "insufficient")

    def test_well_separated_faces_give_zero_errors(self):
        r = L.evaluate(self.SEPARATED, 0.55)
        self.assertEqual(r["status"], "ok")
        self.assertEqual((r["genuine"], r["impostor"]), (3, 3))
        self.assertEqual((r["at_threshold"]["far"], r["at_threshold"]["frr"]), (0.0, 0.0))
        self.assertEqual(r["rank1"], {"probes": 3, "correct": 3, "rate": 1.0})
        self.assertEqual(r["eer"]["eer"], 0.0)

    def test_far_and_frr_count_the_right_trials(self):
        g, i = [0.3, 0.6, 0.7, 0.4], [0.5, 0.9, 0.52, 1.2]
        t = L.rates_at(0.55, g, i)
        self.assertEqual(t["frr"], 0.5)                  # 0.6 and 0.7 rejected
        self.assertEqual(t["far"], 0.5)                  # 0.5 and 0.52 accepted
        self.assertEqual(L.rates_at(0.55, [], [])["far"], None)

    def test_equal_error_rate_and_sweep(self):
        rows = L.sweep([0.3, 0.4, 0.5], [0.6, 0.7, 0.8])
        self.assertEqual(len(rows), 81)
        e = L.equal_error_rate(rows)
        self.assertEqual(e["eer"], 0.0)
        self.assertGreaterEqual(e["threshold"], 0.5)
        self.assertLessEqual(e["threshold"], 0.6)
        self.assertIsNone(L.equal_error_rate([]))

    def test_look_alike_students_raise_far_and_lower_rank1(self):
        twins = people(a=([[0, 0]], [[0.3, 0]]), b=([[0.2, 0]], [[0.1, 0]]))
        r = L.evaluate(twins, 0.55)
        self.assertGreater(r["at_threshold"]["far"], 0)
        self.assertLess(r["rank1"]["rate"], 1.0)

    def test_extra_angles_use_the_nearest_reference(self):
        p = people(a=([[0, 0], [3, 0]], [[3.1, 0]]), b=([[9, 9]], [[9, 9.1]]))
        r = L.evaluate(p, 0.55)
        self.assertEqual(r["at_threshold"]["frr"], 0.0)

    def test_impostor_thinning_is_bounded(self):
        many = {str(i): {"refs": [[i, 0]], "probes": [[i + 0.01, 0]]} for i in range(60)}
        g, imp = L.build_trials(many, max_impostors=500)
        self.assertEqual(len(g), 60)
        self.assertEqual(len(imp), 500)


if __name__ == "__main__":
    unittest.main()
