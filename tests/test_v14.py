"""STEP 33 — TESTS v1.4: cross-run pending, unavailable και quota, χωρίς API."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from scanner.storage import Store
from scanner.sources import demo_events
from scanner.reports import export_reports


class CrossRunPendingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'live.sqlite3'
        self.base = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def init_pending(self):
        store = Store(self.path)
        first = store.apply(demo_events(0,self.base), .01, 100, self.base.isoformat(), 180)
        self.assertEqual(first['new'], 1)
        store.close()

    def test_recheck_pending_in_later_run(self):
        self.init_pending()
        store=Store(self.path)
        t=self.base+timedelta(seconds=40)
        result=store.apply(demo_events(1,self.base), .01, 100, t.isoformat(),180,
                           scanned_sports=['tennis_atp'])
        self.assertEqual(result['rechecked'],1)
        self.assertEqual(result['new'],0)
        self.assertEqual(store.list_rows()[0]['state'],'SURVIVED')
        store.close()

    def test_no_update_does_not_duplicate_between_runs(self):
        self.init_pending()
        store=Store(self.path)
        result=store.apply(demo_events(0,self.base), .01, 100,
                           (self.base+timedelta(seconds=50)).isoformat(),180,
                           scanned_sports=['tennis_atp'])
        self.assertEqual(result['new'],0)
        self.assertEqual(result['awaiting_fresh'],1)
        self.assertEqual(store.list_rows()[0]['state'],'PENDING')
        store.close()

    def test_unavailable_when_bookmaker_missing(self):
        self.init_pending()
        store=Store(self.path)
        event=demo_events(1,self.base)[0]
        event['bookmakers']=[event['bookmakers'][0]]
        result=store.apply([event],.01,100,(self.base+timedelta(seconds=40)).isoformat(),180,
                           scanned_sports=['tennis_atp'])
        self.assertEqual(result['unavailable'],1)
        self.assertEqual(store.list_rows()[0]['state'],'UNAVAILABLE')
        self.assertIsNone(store.list_rows()[0]['t1_profit'])
        store.close()

    def test_other_sport_does_not_mark_unavailable(self):
        self.init_pending()
        store=Store(self.path)
        result=store.apply([], .01,100,(self.base+timedelta(seconds=40)).isoformat(),180,
                           scanned_sports=['soccer_epl'])
        self.assertEqual(result['unavailable'],0)
        self.assertEqual(store.list_rows()[0]['state'],'PENDING')
        store.close()


if __name__ == '__main__':
    unittest.main()
