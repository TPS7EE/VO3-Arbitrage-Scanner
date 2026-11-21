"""Διαγνωστικά για τις πραγματικές αποδόσεις, χωρίς επιπλέον API requests."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from typing import Any
from .core import Quote, extract_quotes, market_outcomes


# ============================================================
# STEP 11 — ΜΕΤΡΑΜΕ BOOKMAKERS ΑΠΟ ΤΑ ΔΕΔΟΜΕΝΑ ΠΟΥ ΗΔΗ ΠΗΡΑΜΕ
# ============================================================
# Εδώ ΔΕΝ κάνουμε καινούργιο HTTP request. Χρησιμοποιούμε το
# JSON των αγώνων που μόλις επέστρεψε ο OddsClient.fetch().
# Μετράμε μόνο bookmakers που έχουν έγκυρη αγορά 'h2h'.
# Έτσι δεν συγχέουμε την παρουσία bookmaker σε έναν αγώνα
# με την πραγματική ύπαρξη έγκυρων αποδόσεων νικητή αγώνα.

@dataclass(frozen=True)
class MatchDiagnostic:
    match: str
    bookmaker_count: int
    best_roi_pct: float | None
    best_quotes: tuple[Quote, ...]
    note: str


def _best_two_or_more_bookmakers(needed: tuple[str, ...], quotes: dict[str, list[Quote]]) -> tuple[Quote, ...]:
    """Βρίσκουμε το κορυφαίο πλήρες σετ από τουλάχιστον 2 εταιρείες.

    Επιλέγουμε τις υψηλότερες αποδόσεις ανά αποτέλεσμα. Αν όλες
    είναι από τον ΙΔΙΟ bookmaker, δοκιμάζουμε κάθε δυνατό τρόπο
    αντικατάστασης ΜΙΑΣ επιλογής με τη καλύτερη άλλη εταιρεία.
    Αυτό αρκεί για το βέλτιστο σετ με περιορισμό >= 2 εταιρειών:
    κάθε άλλη αντικατάσταση θα είχε εξίσου ή περισσότερο κακή τιμή.
    """
    if not needed or any(not quotes.get(outcome) for outcome in needed):
        return ()
    top = tuple(max(quotes[n], key=lambda q: q.odds) for n in needed)
    if len({q.bookmaker_key for q in top}) >= 2:
        return top
    candidates: list[tuple[Quote, ...]] = []
    for index, outcome in enumerate(needed):
        other = [q for q in quotes[outcome] if q.bookmaker_key != top[index].bookmaker_key]
        if not other:
            continue
        alternate = max(other, key=lambda q: q.odds)
        changed = list(top)
        changed[index] = alternate
        candidates.append(tuple(changed))
    if not candidates:
        return ()
    return min(candidates, key=lambda combo: sum(1 / q.odds for q in combo))


def analyze_snapshot(events: list[dict[str, Any]]) -> tuple[list[MatchDiagnostic], list[tuple[str, str]], Counter]:
    # STEP 12 — ΣΥΓΚΕΝΤΡΩΝΟΥΜΕ ΤΑ ΑΠΟΤΕΛΕΣΜΑΤΑ ΓΙΑ ΟΛΟΥΣ ΤΟΥΣ ΑΓΩΝΕΣ
    # Τα bookmaker keys είναι η ταυτότητα της εταιρείας.
    # Τα ονόματα προέρχονται από το API, όχι από υποθέσεις μας.
    all_books: dict[str, str] = {}
    matches: list[MatchDiagnostic] = []
    counts: Counter = Counter()
    for event in events:
        needed = market_outcomes(event)
        quotes = extract_quotes(event)
        event_books: dict[str, str] = {}
        for outcome_quotes in quotes.values():
            for q in outcome_quotes:
                event_books[q.bookmaker_key] = q.bookmaker_name
                all_books[q.bookmaker_key] = q.bookmaker_name
        for key in event_books:
            counts[key] += 1
        match = f"{event.get('home_team', '?')} vs {event.get('away_team', '?')}"
        best = _best_two_or_more_bookmakers(needed, quotes)
        if best:
            # ROI μπορεί να είναι ΑΡΝΗΤΙΚΟ. Το εμφανίζουμε για
            # να δούμε πόσο απέχουν οι αποδόσεις από arbitrage.
            implied = sum(1 / q.odds for q in best)
            roi = (1 / implied - 1) * 100
            note = 'Πλήρες σετ από >=2 bookmakers'
        else:
            roi = None
            note = 'Δεν υπάρχουν πλήρεις επιλογές σε >=2 bookmakers'
        matches.append(MatchDiagnostic(match, len(event_books), roi, best, note))
    names = sorted(all_books.items(), key=lambda pair: pair[1].casefold())
    return matches, names, counts


def print_snapshot_diagnostics(events: list[dict[str, Any]], min_roi_pct: float) -> None:
    # STEP 13 — ΕΜΦΑΝΙΖΟΥΜΕ ΤΗ ΔΙΑΓΝΩΣΗ ΣΤΟ TERMINAL
    # Η εκτύπωση είναι μόνο για έλεγχο ποιότητας δεδομένων.
    # Δεν επηρεάζει την SQLite, τα Excel ή τον detector T0/T1.
    matches, books, counts = analyze_snapshot(events)
    print('\n--- ΔΙΑΓΝΩΣΤΙΚΑ ODDS API (χωρίς πρόσθετο request) ---')
    print(f'Bookmakers με έγκυρες h2h τιμές: {len(books)}')
    if books:
        print('Ονόματα bookmakers (πόσους αγώνες καλύπτει ο καθένας):')
        for key, name in books:
            print(f'  - {name} [{key}]: {counts[key]} αγώνες')
    else:
        print('Δεν επιστράφηκαν χρησιμοποιήσιμες τιμές h2h.')
    print('\nΑνά αγώνα — πλήθος bookmakers και καλύτερο θεωρητικό ROI:')
    for i, m in enumerate(matches, start=1):
        if m.best_roi_pct is None:
            print(f'  {i:02d}. {m.match} | bookmakers: {m.bookmaker_count} | ROI: N/A ({m.note})')
        else:
            legs = ' / '.join(f'{q.outcome}: {q.odds:.2f} @ {q.bookmaker_name}' for q in m.best_quotes)
            print(f'  {i:02d}. {m.match} | bookmakers: {m.bookmaker_count} | καλύτερο ROI: {m.best_roi_pct:+.2f}%')
            print(f'      {legs}')
    viable = [m for m in matches if m.best_roi_pct is not None]
    if viable:
        top = max(viable, key=lambda m: m.best_roi_pct)
        above = sum(1 for m in viable if m.best_roi_pct >= min_roi_pct)
        print(f'\nΚαλύτερο ROI στο snapshot: {top.best_roi_pct:+.2f}% ({top.match})')
        print(f'Αγώνες με καλύτερο ROI >= {min_roi_pct:g}%: {above} / {len(matches)}')
    else:
        print('\nΚαλύτερο ROI: N/A — ανεπαρκή ή μη συγκρίσιμα δεδομένα.')
    print('Σημείωση: τα ROI είναι παρατηρούμενα/θεωρητικά, όχι εκτελεσμένα bets.')
    print('--- ΤΕΛΟΣ ΔΙΑΓΝΩΣΤΙΚΩΝ ---\n')
