"""STEP 36 — Tests για το BEST SET, χωρίς API requests/credits."""
import unittest
import tempfile
from pathlib import Path
from scanner.reports import best_ids_by_event, export_run_txt, export_reports


def make_row(i, event='e1', state='PENDING', t0=1.1, t1=None):
    import json
    q={'selections':[{'bookmaker_key':'a','bookmaker_name':'Test',
          'outcome':'Home','odds':2.2,'updated_at':'2026-11-18T10:00:00+00:00'}],
       'stakes':[100]}
    return {'id':i,'event_id':event,'sport':'soccer_epl','event_name':event,
        'state':state,'discovered_at':'2026-11-18T10:00:00+00:00',
        'checked_at':'2026-11-18T10:01:00+00:00' if t1 is not None else None,
        't0_json':json.dumps(q),'t1_json':json.dumps(q) if t1 is not None else None,
        't0_roi_pct':t0,'t1_roi_pct':t1,'t0_profit':t0,'t1_profit':t1,
        'check_note':''}

class BestSetTests(unittest.TestCase):
    def test_pending_uses_t0(self):
        self.assertEqual(best_ids_by_event([make_row(1,t0=1.1), make_row(2,t0=1.8)]),{2})
    def test_survived_preferred_over_pending(self):
        rows=[make_row(1,t0=4),make_row(2,state='SURVIVED',t0=1.2,t1=1.05)]
        self.assertEqual(best_ids_by_event(rows),{2})
    def test_lost_and_unavailable_excluded(self):
        rows=[make_row(1,state='LOST',t0=7,t1=-2),make_row(2,state='UNAVAILABLE',t0=4)]
        self.assertEqual(best_ids_by_event(rows),set())
    def test_txt_best_and_excel_created(self):
        rows=[make_row(1,t0=1.1),make_row(2,t0=1.8)]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            export_run_txt(rows,path/'run1.txt',0,'LIVE')
            txt=(path/'run1.txt').read_text(encoding='utf8')
            self.assertEqual(txt.count('★ BEST SET'),1)
            self.assertIn('ARB-00002',txt)
            _,excel,ok=export_reports(rows,path)
            self.assertTrue(ok)
            self.assertTrue(excel.exists())

if __name__ == '__main__': unittest.main()
