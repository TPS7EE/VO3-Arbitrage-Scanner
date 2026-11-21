"""STEP 23 — Έλεγχοι ποιότητας, freshness, T1 και Excel χωρίς API requests."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from scanner.core import detect, extract_quotes
from scanner.sources import demo_events
from scanner.storage import Store
from scanner.reports import flatten, HEADERS, export_reports


class V12Tests(unittest.TestCase):
    def test_reject_partial_market(self):
        event=demo_events(0)[0]
        event['bookmakers'][0]['markets'][0]['outcomes'].pop()
        self.assertEqual(detect(event,.01),[])

    def test_reject_lay_and_duplicate_outcomes(self):
        event=demo_events(0)[0]
        event['bookmakers'][0]['markets'][0]['key']='h2h_lay'
        self.assertEqual(detect(event,.01),[])
        event=demo_events(0)[0]
        event['bookmakers'][0]['markets'][0]['outcomes'][1]['name']='Παίκτης Α'
        self.assertEqual(detect(event,.01),[])

    def test_reject_stale_initial_quote(self):
        base=datetime(2026,11,18,12,tzinfo=timezone.utc)
        event=demo_events(0,base)[0]
        found=detect(event,.01,observed_at=base+timedelta(seconds=300),max_quote_age_seconds=180)
        self.assertEqual(found,[])
        good=detect(event,.01,observed_at=base+timedelta(seconds=90),max_quote_age_seconds=180)
        self.assertEqual(len(good),1)

    def test_pending_when_no_new_timestamp(self):
        base=datetime(2026,11,18,12,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'db.sqlite')
            a=store.apply(demo_events(0,base),.01,100,base.isoformat(),180)
            b=store.apply(demo_events(0,base),.01,100,(base+timedelta(seconds=40)).isoformat(),180)
            self.assertEqual(a['new'],1)
            self.assertEqual(b['rechecked'],0)
            self.assertEqual(store.list_rows()[0]['state'],'PENDING')
            store.close()

    def test_t1_columns_and_export(self):
        base=datetime(2026,11,18,12,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            store=Store(path/'db.sqlite')
            store.apply(demo_events(0,base),.01,100,base.isoformat(),180)
            store.apply(demo_events(1,base),.01,100,(base+timedelta(seconds=40)).isoformat(),180)
            row=store.list_rows()[0]
            self.assertEqual(row['state'],'SURVIVED')
            vals=flatten(row)
            self.assertEqual(len(vals),len(HEADERS))
            self.assertLess(vals[33],0)
            txt,xlsx,ok=export_reports([row],path)
            self.assertTrue(ok)
            self.assertTrue(txt.exists() and xlsx.exists())
            store.close()

if __name__=='__main__': unittest.main()
