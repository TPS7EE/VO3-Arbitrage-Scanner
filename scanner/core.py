"""Αναλυτικός πυρήνας: λειτουργεί χωρίς API και χωρίς πραγματικά στοιχήματα."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product
from typing import Any


# ============================================================
# STEP 1 — ΚΑΝΟΝΙΚΟΠΟΙΟΥΜΕ ΑΠΟΔΟΣΕΙΣ ΚΑΙ ΧΡΟΝΟΥΣ
# ============================================================
# Το API δίνει μία ενιαία ταυτότητα event, διαφορετικούς
# bookmakers και χρονικά stamps ανά αγορά.
# Δεν συγκρίνουμε άσχετες αγορές ούτε ελλιπή αποτελέσματα.


def parse_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if d.tzinfo is None:
            return None
        return d.astimezone(timezone.utc)
    except ValueError:
        return None


@dataclass(frozen=True)
class Quote:
    bookmaker_key: str
    bookmaker_name: str
    outcome: str
    odds: float
    updated_at: datetime


@dataclass(frozen=True)
class Opportunity:
    key: str
    sport: str
    event_id: str
    event_name: str
    market: str
    selections: tuple[Quote, ...]
    roi: float                 # ROI as fraction: 0.01 = 1%


def market_outcomes(event: dict[str, Any]) -> tuple[str, ...]:
    """h2h: δύο αποτελέσματα, ή τρία όταν υπάρχει ισοπαλία.

    Το event.home_team και away_team είναι οι ΟΝΟΜΑΣΤΙΚΕΣ
    ταυτότητες: αποφεύγουμε να συναγάγουμε market type από
    αριθμό bookmakers ή τυχαίες επιπλέον επιλογές.
    """
    home, away = event.get('home_team'), event.get('away_team')
    if not home or not away or home == away:
        return ()
    sports_key = str(event.get('sport_key', ''))
    # Στο h2h του The Odds API το soccer είναι αγορά 1-X-2.
    if sports_key.startswith('soccer_'):
        return (home, away, 'Draw')
    return (home, away)


def extract_quotes(event: dict[str, Any]) -> dict[str, list[Quote]]:
    """STEP 15 — ΔΕΧΟΜΑΣΤΕ ΜΟΝΟ ΠΛΗΡΕΙΣ, ΣΥΓΚΡΙΣΙΜΕΣ h2h ΑΓΟΡΕΣ.

    Κάθε bookmaker πρέπει να επιστρέφει ΑΚΡΙΒΩΣ τα ίδια αποτελέσματα
    (π.χ. 1, X, 2). Ελλιπή, διπλά ή άσχετα outcomes απορρίπτονται.
    ΟΧΙ h2h_lay: οι lay odds έχουν διαφορετικό νόημα/υποχρέωση.
    Η ώρα προέρχεται από το market.last_update, ποτέ από το
    deprecated bookmaker.last_update ως εναλλακτική.
    """
    needed = market_outcomes(event)
    found: dict[str, list[Quote]] = {n: [] for n in needed}
    if not needed:
        return found
    for bookmaker in event.get('bookmakers', []):
        key = bookmaker.get('key')
        if not key:
            continue
        # Κρατάμε μόνο BACK τιμές από την ακριβή αγορά h2h.
        for market in bookmaker.get('markets', []):
            if market.get('key') != 'h2h':
                continue
            stamp = parse_utc(market.get('last_update'))
            if stamp is None:
                continue
            outcomes = market.get('outcomes', [])
            names = [o.get('name') for o in outcomes]
            # Ακριβής συμφωνία επιλογών· όχι μερική αγορά/διπλό outcome.
            if len(names) != len(needed) or set(names) != set(needed):
                continue
            cleaned = {}
            try:
                for outcome in outcomes:
                    price = float(outcome['price'])
                    if not (1.0 < price < 1000.0):
                        raise ValueError('Άκυρη απόδοση')
                    cleaned[outcome['name']] = price
            except (TypeError, ValueError, KeyError):
                continue
            for name in needed:
                found[name].append(Quote(key, bookmaker.get('title', key),
                                         name, cleaned[name], stamp))
    return found


def quote_age_seconds(quote: Quote, now: datetime) -> float:
    """STEP 16 — Υπολογίζουμε πόσων δευτερολέπτων είναι μια αγορά."""
    return (now - quote.updated_at).total_seconds()


# ============================================================
# STEP 2 — ΑΝΑΖΗΤΑΜΕ ARBITRAGE SETS
# ============================================================
# Κάθε SET καλύπτει ΟΛΑ τα αποτελέσματα της αγοράς και
# χρησιμοποιεί τουλάχιστον δύο διαφορετικούς bookmakers.
# Για να μην χάσουμε ένα δεύτερο έγκυρο set, δοκιμάζουμε
# τους καλύτερους 3 quotes ανά επιλογή (μικρό MVP search).
# Δεν επιτρέπουμε δύο selections από ΙΔΙΟ bookmaker σε
# αγορά δύο αποτελεσμάτων.


def detect(event: dict[str, Any], min_roi: float = .01, top_per_outcome: int = 3,
           observed_at: datetime | None = None, max_quote_age_seconds: int | None = None) -> list[Opportunity]:
    needed = market_outcomes(event)
    if not needed:
        return []
    by_outcome = extract_quotes(event)
    # STEP 17 — Σε LIVE mode δεν ανοίγουμε νέα sets από παλιές τιμές.
    # Σε tests/ιστορικά δεδομένα το όριο μπορεί να παραλειφθεί.
    if observed_at is not None and max_quote_age_seconds is not None:
        by_outcome = {name: [q for q in quotes
                    if -5 <= quote_age_seconds(q, observed_at) <= max_quote_age_seconds]
                    for name, quotes in by_outcome.items()}
    if any(not by_outcome.get(n) for n in needed):
        return []
    choices = [sorted(by_outcome[n], key=lambda q: q.odds, reverse=True)[:top_per_outcome] for n in needed]
    results: list[Opportunity] = []
    for combo in product(*choices):
        if len({q.bookmaker_key for q in combo}) < 2:
            continue
        implied = sum(1 / q.odds for q in combo)
        if implied <= 0:
            continue
        roi = 1/implied - 1
        if roi + 1e-10 < min_roi:
            continue
        event_id = str(event.get('id', ''))
        sport = str(event.get('sport_key', ''))
        if not event_id or not sport:
            continue
        # Κλειδί σταθερό ανεξάρτητα από τις τρέχουσες τιμές.
        identities = '|'.join(f'{q.outcome}::{q.bookmaker_key}' for q in combo)
        key = f'{sport}|{event_id}|h2h|{identities}'
        results.append(Opportunity(key, sport, event_id,
                   f"{event.get('home_team')} vs {event.get('away_team')}", 'h2h', tuple(combo), roi))
    return results


# ============================================================
# STEP 3 — ΥΠΟΛΟΓΙΖΟΥΜΕ ΕΙΚΟΝΙΚΑ STAKES ΚΑΙ ΚΕΡΔΟΣ
# ============================================================
# Το stake μοιράζεται με βάση το 1/odds. Στρογγυλεύουμε
# σε λεπτά, ώστε οι αριθμοί να έχουν πρακτικό νόημα.
# Το «εγγυημένο» θεωρητικό κέρδος είναι το ΕΛΑΧΙΣΤΟ payout
# μείον το συνολικό ποντάρισμα, όχι μέσος όρος των payouts.


def profit_details(odds: list[float], bankroll: float) -> dict[str, Any]:
    if bankroll <= 0 or not odds or any(o <= 1 for o in odds):
        raise ValueError('Επιτρέπονται μόνο θετικό κεφάλαιο και αποδόσεις >1')
    weights = [1/o for o in odds]
    total = sum(weights)
    cents = round(bankroll*100)
    allocations = [int(cents*(w/total)) for w in weights]
    # Διανέμουμε τα εναπομείναντα λεπτά στις μεγαλύτερες
    # κλασματικές υπολειπόμενες ποσότητες.
    residues = [cents*(w/total)-allocated for w,allocated in zip(weights,allocations)]
    for i in sorted(range(len(odds)), key=lambda k: residues[k], reverse=True)[:cents-sum(allocations)]:
        allocations[i] += 1
    stakes = [c/100 for c in allocations]
    payouts = [round(s*o, 4) for s,o in zip(stakes,odds)]
    minimum_profit = min(payouts) - cents/100
    return {'stakes': stakes, 'payouts': payouts,
            'profit': round(minimum_profit, 2),
            'roi_pct': round(100*minimum_profit/(cents/100), 4)}
