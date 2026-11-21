"""Εξαγωγή προς τον χρήστη. Η SQLite διατηρεί πάντα τα πρωτογενή δεδομένα."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json

HEADERS = ['ID','Αγώνας','Άθλημα','T0 ώρα','T1 ώρα','Κατάσταση','Bookmaker A',
           'Επιλογή A','T0 odds A','T1 odds A','T0 stake A (€)','T1 stake A (€)',
           'Bookmaker B','Επιλογή B','T0 odds B','T1 odds B','T0 stake B (€)',
           'T1 stake B (€)','Bookmaker C','Επιλογή C','T0 odds C','T1 odds C',
           'T0 stake C (€)','T1 stake C (€)','T0 ROI (%)','T1 ROI (%)',
           'T0 κέρδος (€)','T1 κέρδος (€)','Μεταβολή ROI (μονάδες)',
           'Διάστημα T0-T1 (s)','Σχόλιο',
           'T0 παλαιότερη αγορά (s)', 'T1 παλαιότερη αγορά (s)',
           'Μεταβολή κέρδους (€)', 'T1 ποιοτικός έλεγχος']


def elapsed_seconds(a, b):
    if not a or not b:
        return None
    return round((datetime.fromisoformat(b)-datetime.fromisoformat(a)).total_seconds(), 2)


def _max_age_at(selections, observed):
    """STEP 20 — Η ηλικία της πιο παλιάς αγοράς του set, σε δευτερόλεπτα."""
    if not observed or not selections:
        return None
    try:
        observation=datetime.fromisoformat(observed.replace('Z','+00:00'))
        return round(max((observation - datetime.fromisoformat(
            q['updated_at'].replace('Z','+00:00'))).total_seconds()
            for q in selections),2)
    except (ValueError,KeyError,TypeError):
        return None


def flatten(row):
    t0=json.loads(row['t0_json'])
    t1=json.loads(row['t1_json']) if row['t1_json'] else None
    result=[row['id'],row['event_name'],row['sport'],row['discovered_at'],
            row['checked_at'] or '',row['state']]
    for i in range(3):
        if i < len(t0['selections']):
            q=t0['selections'][i]
            s1=t1['selections'][i] if t1 else None
            result += [q['bookmaker_name'],q['outcome'],q['odds'],s1['odds'] if s1 else '',
                       t0['stakes'][i],t1['stakes'][i] if t1 else '']
        else:
            result += ['']*6
    result += [row['t0_roi_pct'],row['t1_roi_pct'] if row['t1_roi_pct'] is not None else '',
               row['t0_profit'],row['t1_profit'] if row['t1_profit'] is not None else '',
               round(row['t1_roi_pct']-row['t0_roi_pct'],4) if row['t1_roi_pct'] is not None else '',
               elapsed_seconds(row['discovered_at'],row['checked_at']),row['check_note'] or '']
    # STEP 21 — Δείχνουμε T0/T1 ηλικίες και αλλαγή απόδοσης.
    result += [_max_age_at(t0['selections'],row['discovered_at']),
               _max_age_at(t1['selections'],row['checked_at']) if t1 else None,
               round(row['t1_profit']-row['t0_profit'],2) if t1 else None,
               ('FRESH_OBSERVED_NOT_EXECUTED' if t1 else 'UNVERIFIED')]

    return result


# ============================================================
# STEP 8 — ΕΞΑΓΟΥΜΕ TXT ΚΑΙ XLSX
# ============================================================
# Το XLSX αναδημιουργείται από τη SQLite σε ΚΑΘΕ νέο κύκλο.
# Έτσι κάθε ID εμφανίζεται μία φορά, με T0 και T1 δίπλα.
# Αν το Excel είναι ανοιχτό, διατηρούμε την SQLite και
# ζητάμε να κλείσει το αρχείο για την επόμενη εξαγωγή.

# ============================================================
# STEP 24 — ΓΡΑΦΟΥΜΕ ΤΑ SETS ΣΕ TXT ΜΕ ΚΟΙΝΗ ΜΟΡΦΗ
# ============================================================
# Η ίδια μορφοποίηση χρησιμοποιείται στο συγκεντρωτικό TXT
# και στα ξεχωριστά run1.txt, run2.txt, ...
# ΚΑΝΕΝΑ TXT δεν τοποθετεί πραγματικά στοιχήματα.

# ============================================================
# STEP 33 — ΕΠΙΛΟΓΗ ΕΝΟΣ BEST SET ΑΝΑ ΑΓΩΝΑ
# ============================================================
# Κρατάμε ΟΛΑ τα sets. Απλώς ξεχωρίζουμε ένα ανά event/αγορά.
# ΠΡΟΤΕΡΑΙΟΤΗΤΑ: Κερδοφόρο T1 (SURVIVED) > εκκρεμές T0 (PENDING).
# LOST και UNAVAILABLE δεν μπορούν να χαρακτηριστούν BEST.
# Αν υπάρχουν ισοβαθμίες: μικρότερο ID για σταθερό αποτέλεσμα.
# Το dataset που περνάει εδώ είναι αυτό που θα εμφανιστεί
# στο συγκεκριμένο TXT ή στο συνολικό Excel.

def best_ids_by_event(rows: list[dict]) -> set[int]:
    winners = {}
    for row in rows:
        state = row['state']
        if state == 'SURVIVED' and row['t1_roi_pct'] is not None and row['t1_roi_pct'] > 0:
            priority, roi = 2, float(row['t1_roi_pct'])
        elif state == 'PENDING':
            priority, roi = 1, float(row['t0_roi_pct'])
        else:
            continue
        # Το event_id από το API διακρίνει αγώνες με παρόμοια ονόματα.
        # Αν αργότερα υποστηρίξουμε πολλαπλές αγορές στο ίδιο event,
        # θα προσθέσουμε και market_key σε αυτό το κλειδί.
        event_key = (row['sport'], row['event_id'])
        rank = (priority, roi, -int(row['id']))
        if event_key not in winners or rank > winners[event_key][0]:
            winners[event_key] = (rank, row['id'])
    return {entry[1] for entry in winners.values()}


def _write_txt(rows: list[dict], text_path: Path, label: str):
    with text_path.open('w',encoding='utf-8') as f:
        f.write(f'ARBITRAGE SCANNER — {label} | ΟΧΙ ΠΡΑΓΜΑΤΙΚΑ BETS\n')
        f.write('ΠΡΟΣΟΧΗ: Οι μετρήσεις Τ1 είναι παρατηρούμενες τιμές, όχι αποδεκτά bets.\n')
        f.write(f'Εγγραφές: {len(rows)}\n\n')
        if not rows:
            f.write('Δεν βρέθηκαν ΝΕΑ arbitrage sets σε αυτή την εκτέλεση.\n')
        best_ids=best_ids_by_event(rows)
        for row in rows:
            if row['id'] in best_ids:
                basis='T1' if row['state']=='SURVIVED' else 'T0 (PENDING)'
                f.write(f'🟢 ★ BEST SET — βάσει {basis}\n')
            a=json.loads(row['t0_json']); b=json.loads(row['t1_json']) if row['t1_json'] else None
            f.write(f"ARB-{row['id']:05d} | {row['event_name']} | {row['state']}\n")
            f.write(f"  T0 {row['discovered_at']} | ROI {row['t0_roi_pct']:.3f}% | κέρδος {row['t0_profit']:.2f} EUR\n")
            for q,stake in zip(a['selections'],a['stakes']):
                f.write(f"    {q['bookmaker_name']} / {q['outcome']} @ {q['odds']} | stake {stake:.2f} EUR\n")
            if b:
                f.write(f"  T1 {row['checked_at']} | ROI {row['t1_roi_pct']:.3f}% | κέρδος {row['t1_profit']:.2f} EUR\n")
                for q,stake in zip(b['selections'],b['stakes']):
                    f.write(f"    {q['bookmaker_name']} / {q['outcome']} @ {q['odds']} | stake {stake:.2f} EUR\n")
                f.write(f"  Μεταβολή κέρδους: {row['t1_profit']-row['t0_profit']:+.2f} EUR | ")
                f.write('ΕΚΤΙΜΗΣΗ, ΟΧΙ ΕΚΤΕΛΕΣΗ\n')
            else:
                # STEP 31 — Η ΑΙΤΙΑ ΠΟΥ ΔΕΝ ΥΠΑΡΧΕΙ T1 ΕΙΝΑΙ ΣΑΦΗΣ.
                f.write(f"  T1: {row['state']} — {row['check_note'] or 'Δεν υπάρχει επαληθευμένη νέα τιμή'}\n")
            f.write('\n')


# ============================================================
# STEP 25 — ΕΝΑ ΝΕΟ ΑΡΧΕΙΟ TXT ΓΙΑ ΚΑΘΕ ΕΚΤΕΛΕΣΗ
# ============================================================
# Ο αριθμός του run είναι μοναδικός ΜΕΣΑ στον φάκελο outputs.
# Δεν ξαναγράφουμε προηγούμενα runN.txt αρχεία.
# Δημιουργούμε runN.txt και αν ΔΕΝ βρεθούν νέα sets,
# ώστε να γνωρίζουμε ότι πράγματι έγινε η εκτέλεση.

def reserve_next_run_txt(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        path = directory / f'run{index}.txt'
        try:
            with path.open('x', encoding='utf-8'):
                pass
            return path
        except FileExistsError:
            index += 1


def export_run_txt(rows: list[dict], run_path: Path, first_id: int, mode: str):
    # Κρατάμε ΑΠΟΚΛΕΙΣΤΙΚΑ όσα ARB-IDs δημιουργήθηκαν
    # μετά την έναρξη αυτής της εκτέλεσης.
    # Έτσι δεν επαναλαμβάνουμε όλο το ιστορικό στο runN.txt.
    new_rows = [r for r in rows if r['id'] > first_id]
    _write_txt(new_rows, run_path, f'{mode} / {run_path.stem} — ΜΟΝΟ ΝΕΑ SETS')
    return len(new_rows)


def export_reports(rows: list[dict], directory: Path):
    directory.mkdir(parents=True,exist_ok=True)
    text_path=directory/'arbitrage_log.txt'
    _write_txt(rows, text_path, 'ΣΥΓΚΕΝΤΡΩΤΙΚΟ ΙΣΤΟΡΙΚΟ / DEMO + LIVE ΞΕΧΩΡΙΣΤΑ')

    # Η εφαρμογή που θα τρέχει στο PC χρησιμοποιεί την
    # ελαφριά βιβλιοθήκη XlsxWriter μόνο για αναφορές XLSX.
    import xlsxwriter
    target=directory/'arbitrage_opportunities.xlsx'
    temporary=directory/'arbitrage_opportunities.tmp.xlsx'
    workbook=xlsxwriter.Workbook(str(temporary))
    sheet=workbook.add_worksheet('Opportunities')
    summary=workbook.add_worksheet('Statistics')
    header=workbook.add_format({'bold':True,'bg_color':'#12324A','font_color':'#FFFFFF',
                                'text_wrap':True,'valign':'vcenter','border':0})
    good=workbook.add_format({'font_color':'#087345','num_format':'0.00'})
    bad=workbook.add_format({'font_color':'#C1373A','num_format':'0.00'})
    numeric=workbook.add_format({'num_format':'0.00'})
    sheet.freeze_panes(1,3)
    sheet.set_row(0,36)
    sheet.set_column(0,0,10)
    sheet.set_column(1,2,28)
    sheet.set_column(3,5,23)
    sheet.set_column(6,23,18)
    sheet.set_column(24,34,22)
    for col,title in enumerate(HEADERS):sheet.write(0,col,title,header)
    # STEP 34 — ΠΡΑΣΙΝΗ ΕΠΙΣΗΜΑΝΣΗ ΤΟΥ BEST SET ΣΤΟ EXCEL.
    best_ids=best_ids_by_event(rows)
    best_text=workbook.add_format({'bg_color':'#DDF4E7','font_color':'#17613B','bold':True})
    best_number=workbook.add_format({'bg_color':'#DDF4E7','font_color':'#17613B','bold':True,'num_format':'0.00'})
    for idx,row in enumerate(rows,start=1):
        values=flatten(row)
        for col,value in enumerate(values):
            fmt=(good if value>=0 else bad) if col in (24,25,26,27,28) and isinstance(value,(float,int)) else numeric if isinstance(value,(float,int)) else None
            if value is None:value=''
            if row['id'] in best_ids:
                fmt=best_number if isinstance(value,(float,int)) else best_text
            sheet.write(idx,col,value,fmt)
    if rows:
        sheet.autofilter(0,0,len(rows),len(HEADERS)-1)
    # STEP 22 — ΑΝΑΛΥΤΙΚΑ ΣΤΑΤΙΣΤΙΚΑ ΣΤΟ EXCEL
    summary.set_column('A:A',38);summary.set_column('B:B',24)
    stats=[('Στατιστικό','Τιμή'),('Σύνολο μοναδικών εγγραφών',len(rows)),
           ('T1 ολοκληρωμένα',sum(r['state'] in ('SURVIVED','LOST') for r in rows)),
           ('Κερδοφόρα στο T1',sum(r['state']=='SURVIVED' for r in rows)),
           ('Χάθηκαν στο T1',sum(r['state']=='LOST' for r in rows)),
           ('Μη διαθέσιμα στο T1',sum(r['state'] in ('UNAVAILABLE','UNVERIFIED_MISSING') for r in rows)),
           ('Σε αναμονή',sum(r['state']=='PENDING' for r in rows)),
           ('Μέσο T0 ROI (%)',round(sum(r['t0_roi_pct'] for r in rows)/len(rows),4) if rows else 0),
           ('Μέσο T1 ROI (%)',round(sum(r['t1_roi_pct'] for r in rows if r['t1_roi_pct'] is not None)/max(1,sum(r['t1_roi_pct'] is not None for r in rows)),4)),
           ('Μέση μεταβολή κέρδους (€)',round(sum(r['t1_profit']-r['t0_profit'] for r in rows if r['t1_profit'] is not None)/max(1,sum(r['t1_profit'] is not None for r in rows)),2)),
           ('Σύνολο μεταβολής κέρδους (€)',round(sum(r['t1_profit']-r['t0_profit'] for r in rows if r['t1_profit'] is not None),2)),
           ('Σε αναμονή νέων δεδομένων',sum(r['state']=='PENDING' for r in rows)),
           ('ΥΠΕΝΘΥΜΙΣΗ','Εκτίμηση, όχι πραγματοποιημένο κέρδος')]
    for i,(name,value) in enumerate(stats):
        summary.write(i,0,name,header if i==0 else None)
        summary.write(i,1,value,header if i==0 else None)
    workbook.close()
    try:
        temporary.replace(target)
        excel_ok=True
    except PermissionError:
        # Windows: το ανοιχτό Excel μπορεί να κρατά κλειδωμένο το target.
        excel_ok=False
    return text_path,target,excel_ok
