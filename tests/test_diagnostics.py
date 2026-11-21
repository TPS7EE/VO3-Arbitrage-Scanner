"""Tests για το διαγνωστικό report, χωρίς API credits."""
import unittest
from scanner.diagnostics import analyze_snapshot
from scanner.sources import demo_events

class DiagnosticTests(unittest.TestCase):
    def test_demo_positive_roi_and_two_bookmakers(self):
        matches, books, counts = analyze_snapshot(demo_events(0))
        self.assertEqual(len(matches), 1)
        self.assertEqual(len(books), 2)
        self.assertEqual(matches[0].bookmaker_count, 2)
        self.assertAlmostEqual(matches[0].best_roi_pct, 2.0)

    def test_negative_roi_is_not_discarded(self):
        ev = demo_events(0)[0]
        for book in ev['bookmakers']:
            for outcome in book['markets'][0]['outcomes']:
                outcome['price'] = 1.8
        matches, books, _ = analyze_snapshot([ev])
        self.assertLess(matches[0].best_roi_pct, 0)

    def test_not_enough_bookmakers(self):
        ev = demo_events(0)[0]
        ev['bookmakers'] = ev['bookmakers'][:1]
        matches, _, _ = analyze_snapshot([ev])
        self.assertIsNone(matches[0].best_roi_pct)

    def test_best_alternative_when_single_book_has_all_best_odds(self):
        ev = demo_events(0)[0]
        ev['bookmakers'][0]['markets'][0]['outcomes'][1]['price'] = 2.2
        ev['bookmakers'][0]['markets'][0]['outcomes'][0]['price']=2.2
        # Και οι δύο καλύτερες τιμές είναι της εταιρείας A,
        # αλλά αξιολογούμε μόνο σετ με τουλάχιστον δύο εταιρείες.
        matches, _, _ = analyze_snapshot([ev])
        self.assertEqual(len({q.bookmaker_key for q in matches[0].best_quotes}),2)

if __name__ == '__main__':
    unittest.main()
