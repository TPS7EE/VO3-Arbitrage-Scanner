"""SQLite: ανθεκτική μόνιμη αποθήκευση πριν παραχθούν TXT / XLSX."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from .core import Opportunity, extract_quotes, profit_details, parse_utc, quote_age_seconds


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ============================================================
# STEP 4 — ΔΗΜΙΟΥΡΓΟΥΜΕ ΤΗ ΒΑΣΗ SQLite
# ============================================================
# Η βάση είναι το ΠΡΩΤΕΥΟΝ αρχείο δεδομένων. Αν το Excel είναι
# ανοιχτό ή αποτύχει η εξαγωγή, ΔΕΝ χάνουμε τις ευκαιρίες.

class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_key TEXT NOT NULL,
            sport TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_name TEXT NOT NULL,
            discovered_at TEXT NOT NULL,
            checked_at TEXT,
            state TEXT NOT NULL,
            t0_json TEXT NOT NULL,
            t1_json TEXT,
            t0_profit REAL NOT NULL,
            t0_roi_pct REAL NOT NULL,
            t1_profit REAL,
            t1_roi_pct REAL,
            check_note TEXT
          );
          CREATE TABLE IF NOT EXISTS active_keys (
            opportunity_key TEXT PRIMARY KEY,
            opportunity_id INTEGER NOT NULL
          );
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def list_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute('SELECT * FROM opportunities ORDER BY id')]

    def active(self) -> dict[str, int]:
        return {r['opportunity_key']:r['opportunity_id'] for r in self.db.execute('SELECT * FROM active_keys')}

    # ============================================================
    # STEP 5 — ΣΩΖΟΥΜΕ T0, ΕΛΕΓΧΟΥΜΕ ΔΙΠΛΟΕΓΓΡΑΦΕΣ
    # ============================================================
    # Όσο η ίδια ευκαιρία παραμένει διαθέσιμη, η ίδια
    # opportunity_key ΔΕΝ αποκτά δεύτερη γραμμή.
    # Αν εξαφανιστεί και εμφανιστεί αργότερα, νέο επεισόδιο.

    def apply(self, events: list[dict], min_roi: float, bankroll: float,
              observed_at: str | None = None, max_quote_age_seconds: int | None = None,
              scanned_sports: list[str] | None = None):
        from .core import detect
        stamp = observed_at or utc_now()
        observed_dt = parse_utc(stamp)
        found: dict[str, Opportunity] = {}
        event_by_id = {str(e.get('id')):e for e in events}
        # STEP 29 — ΠΟΙΕΣ ΔΙΟΡΓΑΝΩΣΕΙΣ ΕΛΕΓΧΘΗΚΑΝ ΠΡΑΓΜΑΤΙΚΑ;
        # Αν το επόμενο run παρακολουθεί άλλες διοργανώσεις, δεν
        # βαφτίζουμε UNAVAILABLE ένα pending από μη ελεγχόμενο sport.
        scanned = set(scanned_sports) if scanned_sports is not None else {
            str(e.get('sport_key')) for e in events
        }
        for event in events:
            for opportunity in detect(event, min_roi=min_roi,
                                      observed_at=observed_dt,
                                      max_quote_age_seconds=max_quote_age_seconds):
                found[opportunity.key] = opportunity

        previously = self.active()
        inserted, checked, pending, closed = 0, 0, 0, 0
        unavailable = 0
        for key, op_id in previously.items():
            old = self.db.execute('SELECT * FROM opportunities WHERE id=?', (op_id,)).fetchone()
            # STEP 30 — ΔΙΑΤΗΡΟΥΜΕ PENDING ΜΕΤΑΞΥ ΔΙΑΦΟΡΕΤΙΚΩΝ RUNS.
            if old['sport'] not in scanned:
                if old['state'] == 'PENDING':
                    pending += 1
                continue
            event = event_by_id.get(old['event_id'])
            # Στο refresh ολόκληρου sport μπορεί να λείπει ο αγώνας.
            # Δεν το βαφτίζουμε εκτελεσμένο ή ζημιογόνο.
            if event is None:
                self.db.execute('UPDATE opportunities SET state=?,check_note=? WHERE id=? AND state=?',
                                ('UNAVAILABLE', 'Ο αγώνας απουσιάζει από τη νεότερη λήψη της διοργάνωσης', op_id, 'PENDING'))
                self.db.execute('DELETE FROM active_keys WHERE opportunity_key=?',(key,))
                closed += 1
                if old['state'] == 'PENDING':
                    unavailable += 1
                continue
            if old['state'] != 'PENDING':
                # Παραμένει active μέχρι να χαθεί το αρχικό arbitrage,
                # για να μη γράψουμε duplicate μετά το T1.
                if key not in found:
                    self.db.execute('DELETE FROM active_keys WHERE opportunity_key=?',(key,))
                    closed += 1
                continue
            original = json.loads(old['t0_json'])
            quotes = extract_quotes(event)
            revised = []
            all_fresh = True
            too_old = False
            for original_selection in original['selections']:
                matches = [q for q in quotes.get(original_selection['outcome'], [])
                           if q.bookmaker_key == original_selection['bookmaker_key']]
                if not matches:
                    self.db.execute('UPDATE opportunities SET state=?,check_note=? WHERE id=?',
                                    ('UNAVAILABLE', 'Λείπει η αρχική επιλογή ή ο bookmaker στο νέο snapshot', op_id))
                    self.db.execute('DELETE FROM active_keys WHERE opportunity_key=?',(key,))
                    closed += 1
                    unavailable += 1
                    all_fresh = False
                    break
                quote = max(matches, key=lambda q:q.updated_at)
                # Για T1 απαιτούμε νεότερη χρονική σήμανση ΣΕ ΚΑΘΕ
                # επιλογή σε σχέση με τη δική της T0 σήμανση.
                if quote.updated_at <= parse_utc(original_selection['updated_at']):
                    all_fresh = False
                # STEP 19 — Μια νεότερη αλλά ήδη ΠΟΛΥ ΠΑΛΙΑ τιμή
                # δεν πρέπει να θεωρηθεί ασφαλές T1.
                if (max_quote_age_seconds is not None and observed_dt is not None
                        and not (-5 <= quote_age_seconds(quote, observed_dt) <= max_quote_age_seconds)):
                    too_old = True
                revised.append(quote)
            if len(revised) != len(original['selections']):
                continue
            if not all_fresh or too_old:
                # Δεν γεμίζουμε το T1 με μη επιβεβαιωμένες τιμές.
                pending += 1
                self.db.execute('UPDATE opportunities SET check_note=? WHERE id=?',
                    ('Αναμονή νέων timestamps' if not all_fresh else
                     'Νεότερα timestamps αλλά υπερβολικά παλιές τιμές', op_id))
                continue
            details = profit_details([q.odds for q in revised],bankroll)
            raw_t1 = {'selections':[{'bookmaker_key':q.bookmaker_key, 'bookmaker_name':q.bookmaker_name,
                        'outcome':q.outcome,'odds':q.odds,'updated_at':q.updated_at.isoformat()}
                        for q in revised], **details}
            state = 'SURVIVED' if details['profit'] > 0 else 'LOST'
            self.db.execute('''UPDATE opportunities SET checked_at=?,state=?,t1_json=?,
                t1_profit=?,t1_roi_pct=?,check_note=? WHERE id=?''',
                (stamp,state,json.dumps(raw_t1,ensure_ascii=False),details['profit'],
                 details['roi_pct'], 'Νεότερα timestamps σε όλες τις επιλογές (παρατηρούμενο ROI)',op_id))
            checked += 1
            if key not in found:
                self.db.execute('DELETE FROM active_keys WHERE opportunity_key=?',(key,))
                closed += 1

        # Καταγράφουμε νέες ευκαιρίες ΜΕΤΑ τον έλεγχο T1.
        active_now = self.active()
        for key, op in found.items():
            if key in active_now:
                continue
            details = profit_details([q.odds for q in op.selections],bankroll)
            raw_t0 = {'selections':[{'bookmaker_key':q.bookmaker_key, 'bookmaker_name':q.bookmaker_name,
                       'outcome':q.outcome, 'odds':q.odds, 'updated_at':q.updated_at.isoformat()}
                       for q in op.selections], **details}
            cursor = self.db.execute('''INSERT INTO opportunities
              (opportunity_key,sport,event_id,event_name,discovered_at,state,t0_json,t0_profit,t0_roi_pct)
              VALUES (?,?,?,?,?,?,?,?,?)''',
              (key,op.sport,op.event_id,op.event_name,stamp,'PENDING',
               json.dumps(raw_t0,ensure_ascii=False),details['profit'],details['roi_pct']))
            self.db.execute('INSERT INTO active_keys VALUES (?,?)',(key,cursor.lastrowid))
            inserted += 1
        self.db.commit()
        return dict(new=inserted, rechecked=checked, awaiting_fresh=pending, unavailable=unavailable, closed=closed, total=len(self.list_rows()))
