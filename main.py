"""
ARBITRAGE SCANNER v1.2 — ΜΟΝΟ ΕΡΕΥΝΑ / ΧΩΡΙΣ ΠΡΑΓΜΑΤΙΚΑ BETS
Εκτέλεση: python main.py --demo
           python main.py --sports
           python main.py --live
"""
import argparse
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from scanner.storage import Store
from scanner.sources import demo_events, OddsClient
from scanner.reports import export_reports, reserve_next_run_txt, export_run_txt, best_ids_by_event
from scanner.diagnostics import print_snapshot_diagnostics

BASE=Path(__file__).resolve().parent


# ============================================================
# STEP 9 — ΔΙΑΒΑΖΟΥΜΕ ΤΙΣ ΡΥΘΜΙΣΕΙΣ ΤΟΥ PROJECT
# ============================================================
# Τροποποιούμε το config.json και ΟΧΙ τον κώδικα.
# Το API KEY μπαίνει σε μεταβλητή περιβάλλοντος ODDS_API_KEY.

def load_config():
    cfg=json.loads((BASE/'config.json').read_text(encoding='utf-8'))
    if not 0 < float(cfg['min_roi_pct']) < 100:
        raise ValueError('Το min_roi_pct πρέπει να είναι ανάμεσα σε 0 και 100.')
    if float(cfg['virtual_bankroll_eur']) <= 0:
        raise ValueError('Το εικονικό κεφάλαιο πρέπει να είναι >0.')
    if int(cfg.get('max_quote_age_seconds',180)) < 1:
        raise ValueError('Το max_quote_age_seconds πρέπει να είναι θετικό.')
    if int(cfg['refresh_seconds']) < 10:
        raise ValueError('Το refresh_seconds πρέπει να είναι >=10 για αποφυγή κατάχρησης API.')
    return cfg


# ============================================================
# STEP 10 — ΤΡΕΧΟΥΜΕ ΕΝΑΝ ΚΥΚΛΟ ΣΥΛΛΟΓΗΣ ΚΑΙ ΑΝΑΛΥΣΗΣ
# ============================================================
# ΚΑΘΕ κύκλος: GET δεδομένα -> υπολογισμός -> SQLite -> TXT/XLSX.
# Δεν υπάρχουν κλήσεις για deposits ή placing bets.

def process(store,events,cfg,observed_at=None, live=False, run_path=None, first_id=0):
    result=store.apply(events,float(cfg['min_roi_pct'])/100,
                       float(cfg['virtual_bankroll_eur']),observed_at,
                       int(cfg.get('max_quote_age_seconds',180)) if live else None,
                       scanned_sports=cfg['sport_keys'] if live else None)
    rows = store.list_rows()
    txt,xlsx,export_ok=export_reports(rows,BASE/'outputs')
    # ============================================================
    # STEP 26 — ΑΝΑΝΕΩΝΟΥΜΕ ΜΟΝΟ ΤΟ TXT ΤΗΣ ΤΡΕΧΟΥΣΑΣ ΕΚΤΕΛΕΣΗΣ
    # ============================================================
    # Περιλαμβάνει μόνον τις νέες εγγραφές από την εκκίνηση
    # του προγράμματος. Στον δεύτερο κύκλο μπορεί να συμπληρωθεί
    # το T1 στο ΙΔΙΟ runN.txt χωρίς να δημιουργηθεί νέο αρχείο.
    if run_path is not None:
        run_count = export_run_txt(rows, run_path, first_id, 'LIVE' if live else 'DEMO')
        print(f'{run_path.name}: {run_count} νέα sets αυτής της εκτέλεσης')
        # STEP 35 — ΕΜΦΑΝΙΖΟΥΜΕ ΤΑ BEST SETS ΜΕ ΠΡΑΣΙΝΟ ΣΤΟ TERMINAL.
        # Τα ANSI escape codes δουλεύουν στο Windows Terminal / VS Code.
        # Αν η κονσόλα δεν υποστηρίζει χρώμα, παραμένει το ★ BEST.
        relevant=[r for r in rows if r['id'] > first_id]
        chosen=best_ids_by_event(relevant)
        for item in relevant:
            if item['id'] in chosen:
                basis='T1' if item['state']=='SURVIVED' else 'T0'
                value=item['t1_roi_pct'] if basis=='T1' else item['t0_roi_pct']
                print(f"\033[32m★ BEST SET ARB-{item['id']:05d} | {item['event_name']} "
                      f"| ROI {value:.3f}% ({basis})\033[0m")
    print(f"Νέες: {result['new']} | T1: {result['rechecked']} | "
          f"Αναμονή fresh data: {result['awaiting_fresh']} | "
          f"Μη διαθέσιμα: {result['unavailable']} | Σύνολο: {result['total']}")
    print(f'TXT: {txt.name} | Excel: '+('ενημερώθηκε' if export_ok else 'ΚΛΕΙΣΕ ΤΟ EXCEL ΚΑΙ ΞΑΝΑΤΡΕΞΕ'))


def main():
    parser=argparse.ArgumentParser(description='Arbitrage Scanner — ΜΟΝΟ ΠΑΡΑΤΗΡΗΣΗ')
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--demo',action='store_true',help='Συνθετικά δεδομένα χωρίς API key')
    group.add_argument('--live',action='store_true',help='Πραγματικές αποδόσεις The Odds API (read-only)')
    group.add_argument('--sports',action='store_true',help='Δείξε έγκυρα sport_keys χωρίς quota cost')
    args=parser.parse_args()
    cfg=load_config()
    if args.sports:
        client=OddsClient(os.getenv('ODDS_API_KEY',''),cfg['region'])
        for sport in client.available_sports():
            if sport.get('active'):
                print(sport['key'], '|',sport.get('title',''))
        return

    # Ξεχωριστή DB για DEMO και LIVE ώστε να μην αναμιχθούν
    # ψεύτικες και πραγματικές παρατηρήσεις.
    db_name='demo.sqlite3' if args.demo else 'live.sqlite3'
    store=Store(BASE/'outputs'/db_name)
    # ============================================================
    # STEP 27 — ΚΛΕΙΔΩΝΟΥΜΕ ΤΗΝ ΑΡΧΗ ΤΟΥ ΣΥΓΚΕΚΡΙΜΕΝΟΥ RUN
    # ============================================================
    # Τα IDs που υπήρχαν ήδη ΔΕΝ θα μπουν στο καινούργιο TXT.
    # Το όνομα run1.txt, run2.txt, ... δεν ξαναχρησιμοποιείται.
    first_id = max((r['id'] for r in store.list_rows()), default=0)
    run_path = reserve_next_run_txt(BASE/'outputs')
    export_run_txt([], run_path, first_id, 'DEMO' if args.demo else 'LIVE')
    print(f'Αρχείο τρέχουσας εκτέλεσης: {run_path.name}')
    last_quota = None
    try:
        if args.demo:
            base=datetime.now(timezone.utc)
            for i in range(2):
                print(f'\nDEMO κύκλος {i+1}/2 (ΣΥΝΘΕΤΙΚΑ ΔΕΔΟΜΕΝΑ)')
                observed_at=(base.replace(microsecond=0) if i==0 else base.replace(microsecond=0) + __import__('datetime').timedelta(seconds=40)).isoformat()
                process(store,demo_events(i,base),cfg,observed_at,run_path=run_path,first_id=first_id)
            print('\nDEMO ολοκληρώθηκε. Άνοιξε τον φάκελο outputs.')
            return

        client=OddsClient(os.getenv('ODDS_API_KEY',''),cfg['region'])
        cycles=int(cfg.get('max_live_cycles',10))
        refresh=int(cfg['refresh_seconds'])
        for i in range(cycles):
            print(f'\nLIVE κύκλος {i+1}/{cycles} | '+datetime.now().isoformat(timespec='seconds'))
            events,quota=client.fetch(cfg['sport_keys'])
            last_quota = quota
            print(f'Λήφθηκαν {len(events)} αγώνες. Quota: {quota}')
            # ============================================================
            # STEP 14 — ΔΙΑΓΝΩΣΗ ΤΗΣ ΠΟΙΟΤΗΤΑΣ ΤΩΝ LIVE ΑΠΟΔΟΣΕΩΝ
            # ============================================================
            # Αναλύουμε τα ίδια events που ήδη λάβαμε από το API.
            # ΜΗΔΕΝ επιπλέον API calls / credits για τη διάγνωση.
            # Ακόμα και όταν δεν υπάρχει arb >= 1%, εμφανίζουμε
            # το καλύτερο μαθηματικό ROI (μπορεί να είναι αρνητικό).
            print_snapshot_diagnostics(events, float(cfg['min_roi_pct']))
            process(store,events,cfg,live=True,run_path=run_path,first_id=first_id)
            remaining=quota.get('remaining')
            if remaining is not None and int(remaining)<int(cfg.get('stop_if_quota_below',20)):
                print('Προστασία quota: σταματάμε πριν εξαντληθούν τα credits.')
                break
            if i<cycles-1:
                time.sleep(refresh)
    except KeyboardInterrupt:
        print('\nΔιακοπή χρήστη. Τα στοιχεία έχουν σωθεί στη βάση.')
    except Exception as err:
        print('\nΣΦΑΛΜΑ:',err)
        raise SystemExit(1) from err
    finally:
        # ============================================================
        # STEP 32 — ΕΜΦΑΝΙΖΟΥΜΕ ΤΑ ΥΠΟΛΟΙΠΑ CREDITS ΣΤΟ ΤΕΛΟΣ ΤΟΥ RUN
        # ============================================================
        # ΔΕΝ κάνουμε νέο API request για το quota. Χρησιμοποιούμε
        # αποκλειστικά τα headers της τελευταίας επιτυχούς λήψης.
        if args.live:
            if last_quota is None:
                print('\nCREDITS: Άγνωστο υπόλοιπο — δεν ολοκληρώθηκε επιτυχές request.')
            else:
                print('\n========== ΥΠΟΛΟΙΠΟ API CREDITS ==========')
                print(f"Απομένουν: {last_quota.get('remaining') or 'άγνωστο'}")
                print(f"Χρησιμοποιήθηκαν συνολικά: {last_quota.get('used') or 'άγνωστο'}")
                print(f"Τελευταίο API request: {last_quota.get('last') or 'άγνωστο'} credit(s)")
                print('=========================================')
        store.close()


if __name__=='__main__':
    main()
