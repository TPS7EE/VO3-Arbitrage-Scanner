"""Τεστ λογικής χωρίς συνδρομή, χωρίς δίκτυο, χωρίς πραγματικά bets."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from scanner.core import detect,profit_details
from scanner.sources import demo_events
from scanner.storage import Store

class ScannerTests(unittest.TestCase):
    def test_initial_arbitrage(self):
        opportunity=detect(demo_events(0)[0],.01)[0]
        self.assertAlmostEqual(opportunity.roi*100,2.0,places=3)

    def test_recheck_loss_of_threshold_but_still_profit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            first=store.apply(demo_events(0),.01,100, '2026-11-18T12:00:00+00:00')
            second=store.apply(demo_events(1),.01,100, '2026-11-18T12:00:40+00:00')
            row=store.list_rows()[0]
            self.assertEqual(first['new'],1)
            self.assertEqual(second['new'],0)
            self.assertEqual(second['rechecked'],1)
            self.assertEqual(row['state'],'SURVIVED')
            self.assertLess(row['t1_roi_pct'],1)
            self.assertGreater(row['t1_roi_pct'],0)
            store.close()

    def test_unchanged_timestamp_not_valid_t1(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db')
            store.apply(demo_events(0),.01,100)
            result=store.apply(demo_events(0),.01,100)
            self.assertEqual(result['new'],0)
            self.assertEqual(store.list_rows()[0]['state'],'PENDING')
            store.close()

    def test_math(self):
        result=profit_details([2.2,2.1],100)
        self.assertEqual(round(sum(result['stakes']),2),100)
        self.assertGreater(result['profit'],7)

    def test_soccer_three_outcomes(self):
        timestamp='2026-11-18T12:00:00Z'
        def b(key,name,price):
            return {'key':key,'title':key,'markets':[{'key':'h2h','last_update':timestamp,
                'outcomes':[{'name':name,'price':price},
                            {'name':next(n for n in ('Home','Away','Draw') if n!=name),'price':1.2},
                            {'name':next(n for n in ('Home','Away','Draw') if n!=name and n!=next(n for n in ('Home','Away','Draw') if n!=name)),'price':1.2}]}]}
        ev={'id':'soc-1','sport_key':'soccer_epl','home_team':'Home','away_team':'Away',
            'bookmakers':[b('a','Home',3.5),b('b','Away',3.5),b('c','Draw',3.5)]}
        self.assertEqual(len(detect(ev,.01)),1)
        self.assertEqual(len(detect(ev,.01)[0].selections),3)

if __name__=='__main__':unittest.main()
