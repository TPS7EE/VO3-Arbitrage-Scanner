"""Δύο πηγές: DEMO χωρίς κλειδί, και LIVE μόνο ανάγνωση αποδόσεων."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import requests


# ============================================================
# STEP 6 — DEMO ΔΕΔΟΜΕΝΑ (ΧΩΡΙΣ INTERNET / API KEY)
# ============================================================
# Τα δεδομένα είναι ΣΥΝΘΕΤΙΚΑ και δεν αντιπροσωπεύουν
# bookmakers. Το timestamp αλλάζει, ώστε να δοκιμάσουμε T1.
# Ο πρώτος αγώνας ξεκινά με 2.04/2.04 και γίνεται 2.00/2.04.

def demo_events(step: int, base: datetime | None = None) -> list[dict]:
    base = base or datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    timestamp = (base + timedelta(seconds=40*step)).isoformat().replace('+00:00','Z')
    a = 2.04 if step == 0 else 2.00
    b = 2.04
    # STEP 18 — Κάθε DEMO bookmaker περιέχει ΟΛΗ την αγορά.
    # Η μη συμφέρουσα πλευρά έχει 1.50, ώστε να επιλέγεται ο
    # σωστός bookmaker για κάθε αποτέλεσμα και να δοκιμάζεται
    # ο νέος αυστηρός έλεγχος πλήρους αγοράς.
    def book(key, name, choice, odds):
        other = 'Παίκτης Β' if choice == 'Παίκτης Α' else 'Παίκτης Α'
        return {'key':key,'title':name,'last_update':timestamp,
                'markets':[{'key':'h2h','last_update':timestamp,
                'outcomes':[{'name':choice,'price':odds},
                            {'name':other,'price':1.50}]}]}
    return [{'id':'demo-match-001','sport_key':'tennis_atp',
             'home_team':'Παίκτης Α','away_team':'Παίκτης Β',
             'bookmakers':[book('demo_a','DEMO Bookmaker A','Παίκτης Α',a),
                           book('demo_b','DEMO Bookmaker B','Παίκτης Β',b)]}]



# ============================================================
# STEP 7 — ΠΑΙΡΝΟΥΜΕ ODDS ΑΠΟ ΤΟ THE ODDS API (GET ΜΟΝΟ)
# ============================================================
# Το API KEY ΔΙΑΒΑΖΕΤΑΙ ΑΠΟ ΠΕΡΙΒΑΛΛΟΝ, ΟΧΙ ΣΤΟΝ ΚΩΔΙΚΑ.
# ΔΕΝ υπάρχει endpoint placing bets σε αυτό το project.
# Παρακολουθούμε το υπόλοιπο quota για να αποφύγουμε κόστος.

class OddsClient:
    def __init__(self, api_key: str, region: str='eu'):
        if not api_key:
            raise ValueError('Δεν βρέθηκε ODDS_API_KEY. Δες το README.')
        self.key = api_key
        self.region = region
        self.session = requests.Session()

    def available_sports(self) -> list[dict]:
        response = self.session.get('https://api.the-odds-api.com/v4/sports',
                                    params={'apiKey':self.key},timeout=20)
        response.raise_for_status()
        return response.json()

    def fetch(self, sport_keys: list[str]) -> tuple[list[dict], dict]:
        events: list[dict] = []
        quota = {}
        for sport in sport_keys:
            response = self.session.get(
                f'https://api.the-odds-api.com/v4/sports/{sport}/odds',
                params={'apiKey':self.key,'regions':self.region,
                        'markets':'h2h','oddsFormat':'decimal','dateFormat':'iso'},
                timeout=25)
            if response.status_code == 429:
                raise RuntimeError('API rate limit (429). Αύξησε το διάστημα refresh.')
            if response.status_code in (401,403):
                raise RuntimeError('API key μη έγκυρο ή χωρίς πρόσβαση (401/403).')
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload,list):
                raise RuntimeError('Απροσδόκητη απάντηση API: αναμενόταν λίστα αγώνων.')
            events += payload
            quota = {'remaining':response.headers.get('x-requests-remaining'),
                     'used':response.headers.get('x-requests-used'),
                     'last':response.headers.get('x-requests-last')}
        return events,quota
