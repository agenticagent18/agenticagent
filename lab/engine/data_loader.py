"""
Data loader for strategy lab.

Responsibilities:
1. Cache team schedules from MLB Stats API in SQLite (one fetch per team per season)
2. Pre-load all game records from the orderbook DB with entry prices
3. Build pre-processed GameContext objects ready for sweep iteration

Design: load everything into memory once. The sweep iterates over pre-built
GameContext objects without touching the DB or network.
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from engine.strategy_base import GameContext

HOME = Path.home()
ORDERBOOK_DB = HOME / ".openclaw/workspace/kalshi/mlb_orderbook.db"

MONTH_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

# Kalshi ticker codes → MLB Stats API abbreviations
KALSHI_TO_MLB = {
    'NYM': 'NYM', 'LAD': 'LAD', 'SEA': 'SEA', 'SD': 'SD', 'TEX': 'TEX',
    'ATH': 'ATH', 'COL': 'COL', 'HOU': 'HOU', 'TOR': 'TOR', 'MIL': 'MIL',
    'CLE': 'CLE', 'CHC': 'CHC', 'SF': 'SF', 'ATL': 'ATL', 'DET': 'DET',
    'PHI': 'PHI', 'STL': 'STL', 'AZ': 'ARI', 'CIN': 'CIN', 'TB': 'TB',
    'MIN': 'MIN', 'BOS': 'BOS', 'BAL': 'BAL', 'PIT': 'PIT', 'KC': 'KC',
    'WSH': 'WSH', 'NYY': 'NYY', 'MIA': 'MIA', 'LAA': 'LAA', 'OAK': 'ATH',
    'ARI': 'ARI',
}


def _mlb_get(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 ** attempt)
            elif attempt < retries - 1:
                time.sleep(1)
            else:
                raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                raise
    return {}


def _fetch_team_map() -> dict:
    """Return {abbrev: team_id}."""
    data = _mlb_get("https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2026")
    return {t["abbreviation"]: t["id"] for t in data.get("teams", []) if t.get("abbreviation") and t.get("id")}


def _fetch_team_schedule(team_id: int, season: int = 2026) -> list:
    """Fetch full season schedule → [{'date': 'YYYY-MM-DD', 'won': bool}]."""
    url = (
        f"https://statsapi.mlb.com/api/v1/schedule?sportId=1"
        f"&teamId={team_id}&season={season}&gameType=R"
        f"&hydrate=linescore,team&startDate={season}-03-01&endDate={season}-12-01"
    )
    data = _mlb_get(url)
    games = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            if game.get("status", {}).get("detailedState", "") != "Final":
                continue
            home = game.get("teams", {}).get("home", {})
            away = game.get("teams", {}).get("away", {})
            home_id = home.get("team", {}).get("id")
            away_id = away.get("team", {}).get("id")
            home_score = home.get("score", 0) or 0
            away_score = away.get("score", 0) or 0
            if home_score == away_score:
                continue
            is_home = (home_id == team_id)
            won = (home_score > away_score) if is_home else (away_score > home_score)
            games.append({
                "date": game.get("officialDate", ""),
                "won": won,
            })
    return games


def _init_cache(cache_db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(cache_db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_schedules (
            team_code TEXT PRIMARY KEY,
            schedule_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entry_prices (
            market_ticker TEXT PRIMARY KEY,
            mid REAL NOT NULL,
            fetched_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _parse_ticker(event_ticker: str):
    """Parse KXMLBGAME-26APR142210NYMLAD → (game_start_utc, teams_str)."""
    m = re.match(r'KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})([A-Z]+)', event_ticker)
    if not m:
        return None, None
    yr, mon, day, hr, mn, teams_str = m.groups()
    try:
        dt = datetime.datetime(
            2000 + int(yr), MONTH_MAP[mon], int(day),
            int(hr), int(mn), tzinfo=datetime.timezone.utc
        )
    except (KeyError, ValueError):
        return None, None
    return dt, teams_str


def _extract_teams(market_tickers_str: str) -> list:
    parts = market_tickers_str.split(',')
    teams = []
    for p in parts:
        m = re.search(r'-([A-Z]{2,4})$', p.strip())
        if m:
            teams.append(m.group(1))
    return teams


def _wins_history_before(schedule: list, game_date: str, max_window: int = 20) -> list | None:
    """Return list of bool (True=win) for last max_window games before game_date.
    Returns None if fewer than 3 games available (insufficient for any signal)."""
    past = [g for g in schedule if g["date"] < game_date]
    past.sort(key=lambda g: g["date"], reverse=True)
    recent = past[:max_window]
    if len(recent) < 3:
        return None
    return [g["won"] for g in recent]


def _get_outcome(schedule: list, game_date: str) -> float | None:
    """Return settlement (1.0=win, 0.0=loss) for game_date, or None if ambiguous."""
    matches = [g for g in schedule if g["date"] == game_date]
    if len(matches) == 1:
        return 1.0 if matches[0]["won"] else 0.0
    return None  # doubleheader or no game


class DataLoader:
    def __init__(self, cache_db: Path, orderbook_db: Path = ORDERBOOK_DB, max_window: int = 20):
        self.cache_db_path = cache_db
        self.orderbook_db = orderbook_db
        self.max_window = max_window
        self._cache_conn = _init_cache(cache_db)
        self._team_schedules: dict = {}  # code -> [{date, won}]
        self._team_map: dict = {}        # mlb_abbrev -> team_id

    def warm_cache(self, verbose: bool = True) -> dict:
        """Fetch all team schedules and store in cache. Returns stats."""
        t0 = time.time()
        if verbose:
            print("[data_loader] Warming cache...")

        # Check what's already cached
        cached = {row[0] for row in self._cache_conn.execute("SELECT team_code FROM team_schedules")}

        # Identify all teams in the orderbook DB
        ob_conn = sqlite3.connect(self.orderbook_db)
        all_games_raw = ob_conn.execute(
            "SELECT market_tickers FROM games"
        ).fetchall()
        ob_conn.close()

        all_team_codes = set()
        for (mkt_str,) in all_games_raw:
            all_team_codes.update(_extract_teams(mkt_str))

        # Fetch team map once
        if not self._team_map:
            if verbose:
                print("[data_loader] Fetching MLB team map...")
            self._team_map = _fetch_team_map()
            time.sleep(0.3)

        fetched_count = 0
        skipped_count = 0
        for code in sorted(all_team_codes):
            mlb_abbrev = KALSHI_TO_MLB.get(code, code)
            team_id = self._team_map.get(mlb_abbrev)
            if not team_id:
                if verbose:
                    print(f"[data_loader]   WARNING: no MLB ID for {code}/{mlb_abbrev}")
                continue

            if code in cached:
                skipped_count += 1
                continue

            if verbose:
                print(f"[data_loader]   Fetching {code} ({mlb_abbrev}, id={team_id})...", end=" ", flush=True)
            try:
                sched = _fetch_team_schedule(team_id)
                self._cache_conn.execute(
                    "INSERT OR REPLACE INTO team_schedules (team_code, schedule_json, fetched_at) VALUES (?,?,?)",
                    (code, json.dumps(sched), datetime.datetime.utcnow().isoformat())
                )
                self._cache_conn.commit()
                if verbose:
                    print(f"{len(sched)} games")
                fetched_count += 1
            except Exception as e:
                if verbose:
                    print(f"ERROR: {e}")
            time.sleep(0.4)

        elapsed = time.time() - t0
        stats = {
            "teams_fetched": fetched_count,
            "teams_from_cache": skipped_count,
            "elapsed_seconds": round(elapsed, 1),
        }
        if verbose:
            print(f"[data_loader] Cache warm complete: {fetched_count} fetched, {skipped_count} from cache ({elapsed:.1f}s)")
        return stats

    def _load_schedules(self):
        """Load all cached schedules into memory."""
        if self._team_schedules:
            return
        rows = self._cache_conn.execute("SELECT team_code, schedule_json FROM team_schedules").fetchall()
        for code, json_str in rows:
            self._team_schedules[code] = json.loads(json_str)

    def load_game_records(self, verbose: bool = True) -> tuple[list, dict]:
        """Pre-build all GameContext objects. Returns (records, exclusion_stats)."""
        self._load_schedules()

        ob_conn = sqlite3.connect(self.orderbook_db)
        all_games = ob_conn.execute(
            "SELECT event_ticker, market_tickers, game_date FROM games ORDER BY event_ticker"
        ).fetchall()

        excl = {"no_parse": 0, "bad_teams": 0, "no_snapshot": 0,
                "no_schedule": 0, "insufficient_history": 0, "no_outcome": 0}
        records = []

        if verbose:
            print(f"[data_loader] Building game records from {len(all_games)} games...")

        for event_ticker, market_tickers, _ in all_games:
            game_start, _ = _parse_ticker(event_ticker)
            if game_start is None:
                excl["no_parse"] += 1
                continue

            game_date = game_start.strftime('%Y-%m-%d')
            teams = _extract_teams(market_tickers)
            if len(teams) != 2:
                excl["bad_teams"] += 1
                continue

            team_a, team_b = teams[0], teams[1]
            mkt_a = f"{event_ticker}-{team_a}"
            mkt_b = f"{event_ticker}-{team_b}"

            # Entry price — query orderbook
            t_target = game_start - datetime.timedelta(minutes=45)
            t_back = game_start - datetime.timedelta(minutes=60)
            row = ob_conn.execute("""
                SELECT yes_bid, yes_ask FROM orderbook_events
                WHERE market_ticker=? AND event_type='ticker'
                  AND yes_bid IS NOT NULL AND yes_ask IS NOT NULL
                  AND received_at <= ? AND received_at >= ?
                ORDER BY received_at DESC LIMIT 1
            """, (mkt_a, t_target.isoformat(), t_back.isoformat())).fetchone()

            if row is None:
                excl["no_snapshot"] += 1
                continue

            mid_a = (row[0] + row[1]) / 2.0

            # Team schedules
            sched_a = self._team_schedules.get(team_a)
            sched_b = self._team_schedules.get(team_b)
            if sched_a is None or sched_b is None:
                excl["no_schedule"] += 1
                continue

            wins_hist_a = _wins_history_before(sched_a, game_date, self.max_window)
            wins_hist_b = _wins_history_before(sched_b, game_date, self.max_window)
            if wins_hist_a is None or wins_hist_b is None:
                excl["insufficient_history"] += 1
                continue

            # Settlement
            outcome_a = _get_outcome(sched_a, game_date)
            if outcome_a is None:
                outcome_b = _get_outcome(sched_b, game_date)
                if outcome_b is None:
                    excl["no_outcome"] += 1
                    continue
                outcome_a = 1.0 - outcome_b

            records.append(GameContext(
                event_ticker=event_ticker,
                game_date=game_date,
                game_start=game_start,
                team_a=team_a,
                team_b=team_b,
                mkt_a=mkt_a,
                mkt_b=mkt_b,
                mid_a=mid_a,
                wins_history_a=wins_hist_a,
                wins_history_b=wins_hist_b,
                settlement_a=outcome_a,
            ))

        ob_conn.close()

        records.sort(key=lambda r: r.game_start)
        if verbose:
            print(f"[data_loader] Built {len(records)} game records. Exclusions: {excl}")
        return records, excl

    def close(self):
        self._cache_conn.close()
