# VO.3 — Sports Arbitrage Detection & Temporal Validation Engine

A Python research project that analyzes sports odds for **theoretical arbitrage** and checks whether detected opportunities persist between two observations (T0 and T1).

> **Research / read-only software.** It does not place bets, access bookmaker accounts, or guarantee that quoted odds can be executed. API access may require a separate subscription.

## Features

- Detects theoretical arbitrage across two- and three-outcome markets.
- Uses odds from distinct bookmakers and calculates theoretical return.
- Tracks T0/T1 opportunity status with persistent SQLite storage.
- Applies quote freshness rules for live analysis.
- Exports TXT and XLSX reports.
- Includes an offline demo and unit tests.

## Tech stack

Python 3.13 (original development environment), `requests`, `XlsxWriter`, SQLite (standard library), and `unittest`.

## Quick start

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py --demo
```

The demo uses **synthetic odds**, makes no API calls, and writes reports under `outputs/`.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Live data (optional)

1. Obtain an API key from [The Odds API](https://the-odds-api.com/).
2. Set the `ODDS_API_KEY` environment variable in your terminal (do not commit it).
3. Review `config.json` for sports, region, request frequency, and quota settings.
4. Run `python main.py --sports` to inspect available sports or `python main.py --live` to collect odds.

Live runs consume API credits. Market availability and quote freshness vary; T1 persistence is **not** proof of executable profit.

## Repository layout

```text
main.py              Command-line entry point
config.json          Scanner configuration (no API key)
scanner/             Detection, API client, storage, reporting, diagnostics
tests/               Offline unit tests
sample_reports/      Sample demonstration reports
outputs/             Local generated reports (ignored by Git)
```

## Portfolio highlights

- Modular data ingestion, analysis, persistence, and reporting.
- Stateful opportunity tracking across independent runs.
- Automated offline tests and a reproducible demo workflow.

## Limitations

- Real-world execution is not verified: bookmaker limits, changing odds, settlement rules, and latency can invalidate apparent opportunities.
- Results depend on external API coverage and freshness.
- This project is intended for analysis and education, not betting automation.

## Privacy and publishing

The original ZIP contained a local virtual environment and generated live reports/databases. They are intentionally excluded from this public portfolio package. Use your own API key via environment variable. Review the contents and licensing rights before publishing.
