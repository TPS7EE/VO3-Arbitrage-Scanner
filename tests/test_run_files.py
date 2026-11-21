"""STEP 28 — Ελέγχουμε το TXT κάθε ανεξάρτητης εκτέλεσης χωρίς API credits."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from scanner.sources import demo_events
from scanner.storage import Store
from scanner.reports import reserve_next_run_txt, export_run_txt


class RunFileTests(unittest.TestCase):
    def test_separate_run_files_and_only_new_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            store = Store(folder/'live.sqlite3')
            base = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)

            # RUN 1: φτιάχνει ARB-00001 και αργότερα συμπληρώνει T1.
            run1 = reserve_next_run_txt(folder)
            self.assertEqual(run1.name, 'run1.txt')
            first_id = 0
            store.apply(demo_events(0, base), .01, 100, base.isoformat(), 180)
            self.assertEqual(export_run_txt(store.list_rows(), run1, first_id, 'LIVE'), 1)
            store.apply(demo_events(1, base), .01, 100,
                        (base+timedelta(seconds=40)).isoformat(), 180)
            export_run_txt(store.list_rows(), run1, first_id, 'LIVE')
            self.assertIn('T1 ', run1.read_text(encoding='utf8'))

            # RUN 2: δεν δημιουργεί νέα IDs και δεν αντιγράφει το προηγούμενο.
            first_id = max(r['id'] for r in store.list_rows())
            run2 = reserve_next_run_txt(folder)
            self.assertEqual(run2.name, 'run2.txt')
            self.assertEqual(export_run_txt(store.list_rows(), run2, first_id, 'LIVE'), 0)
            self.assertIn('Δεν βρέθηκαν ΝΕΑ', run2.read_text(encoding='utf8'))
            self.assertNotIn('ARB-00001', run2.read_text(encoding='utf8'))
            self.assertIn('ARB-00001', run1.read_text(encoding='utf8'))
            store.close()

if __name__=='__main__': unittest.main()
