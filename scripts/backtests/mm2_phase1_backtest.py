#!/usr/bin/env python3
"""
MM-2 Phase 1 Backtest
Registered spec: public/docs/mm2-backtest-spec.md (2026-06-14)

Signal logic implemented from mm2-backtest-spec.md and mm2-decision-rule.md.
signal_generator.py does not exist as a file; this script IS the canonical
implementation derived from the spec. Deviations from live session behavior
are expected to be small (live uses DeepSeek veto; backtest does not).

Signal strength formula (derived, not from existing code):
    underdog_momentum:      strength = wins_in_last5 * 20 + (40 - implied_pct)
    favorite_vs_hot_opp:    strength = opp_wins_in_last5 * 20 + (implied_pct - 65)
    threshold for action:   strength >= 60
    position sizing:        1 contract [60,80), 2 contracts [80,100), 3 contracts [100+)
"""

import csv
import datetime
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
HOME = Path.home()
ORDERBOOK_DB = HOME / ".openclaw/workspace/kalshi/mlb_orderbook.db"
OUTPUT_DIR = HOME / ".openclaw/workspace/public/docs/backtests"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_JSON = OUTPUT_DIR / "mm2_phase1_results.json"
TRADES_CSV   = OUTPUT_DIR / "mm2_phase1_trades.csv"

# ── Config ────────────────────────────────────────────────────────────────────
T_MINUS_MIN   = 45   # entry target: 45 min before game start
T_WINDOW_BACK = 60   # look back up to 60 min before game for ticker data
STRENGTH_THRESHOLD = 60
DAILY_LOSS_CAP     = 5.00  # dollars
SIGNAL_STRENGTH_THRESHOLD = 60

MONTH_MAP = {
    'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
    'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12
}

# Kalshi ticker team codes → MLB Stats API abbreviations (2026 season)
# ATH = Sacramento Athletics (relocated from Oakland)
KALSHI_TO_MLB = {
    'NYM':'NYM','LAD':'LAD','SEA':'SEA','SD':'SD','TEX':'TEX',
    'ATH':'ATH','COL':'COL','HOU':'HOU','TOR':'TOR','MIL':'MIL',
    'CLE':'CLE','CHC':'CHC','SF':'SF','ATL':'ATL','DET':'DET',
    'PHI':'PHI','STL':'STL','AZ':'ARI','CIN':'CIN','TB':'TB',
    'MIN':'MIN','BOS':'BOS','BAL':'BAL','PIT':'PIT','KC':'KC',
    'WSH':'WSH','NYY':'NYY','MIA':'MIA','LAA':'LAA','OAK':'ATH',
    'ARI':'ARI',
}

# ── MLB Stats API helpers ──────────────────────────────────────────────────────

def mlb_get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 ** attempt)
            else:
                raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                raise
    return {}

def fetch_team_map():
    """Return {abbrev: team_id} for all MLB teams."""
    data = mlb_get("https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2026")
    result = {}
    for t in data.get("teams", []):
        abbr = t.get("abbreviation","")
        tid  = t.get("id")
        if abbr and tid:
            result[abbr] = tid
    return result

def fetch_team_schedule(team_id, season=2026):
    """Fetch a team's full regular-season schedule and return list of
    {'date': 'YYYY-MM-DD', 'won': bool, 'opponent_id': int}."""
    url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1"
           f"&teamId={team_id}&season={season}&gameType=R"
           f"&hydrate=linescore,team&startDate={season}-03-01&endDate={season}-12-01")
    data = mlb_get(url)
    games = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            status = game.get("status", {}).get("detailedState", "")
            if status != "Final":
                continue
            home = game.get("teams", {}).get("home", {})
            away = game.get("teams", {}).get("away", {})
            home_id = home.get("team", {}).get("id")
            away_id = away.get("team", {}).get("id")
            home_score = home.get("score", 0) or 0
            away_score = away.get("score", 0) or 0
            if home_score == away_score:
                continue  # skip ties (rare)
            is_home = (home_id == team_id)
            won = (home_score > away_score) if is_home else (away_score > home_score)
            opp_id = away_id if is_home else home_id
            games.append({
                "date": game.get("officialDate",""),
                "won": won,
                "opponent_id": opp_id,
                "home_score": home_score,
                "away_score": away_score,
            })
    return games

def last5_wins(schedule, as_of_date):
    """Return count of wins in last 5 completed games before as_of_date."""
    past = [g for g in schedule if g["date"] < as_of_date]
    past.sort(key=lambda g: g["date"], reverse=True)
    recent5 = past[:5]
    if len(recent5) < 3:  # need at least 3 games for reliable signal
        return None  # insufficient data
    return sum(1 for g in recent5 if g["won"])

def get_game_outcome(schedule, game_date):
    """Return True (won) / False (lost) for the game on game_date, or None."""
    matches = [g for g in schedule if g["date"] == game_date]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]["won"]
    # Doubleheader — return None (ambiguous which market maps to which game)
    return None

# ── Ticker parser ──────────────────────────────────────────────────────────────

def parse_ticker(event_ticker):
    """Parse KXMLBGAME-26APR142210NYMLAD into (game_start_utc, team1_code, team2_code)."""
    m = re.match(r'KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})([A-Z]+)', event_ticker)
    if not m:
        return None, None, None
    yr, mon, day, hr, mn, teams_str = m.groups()
    try:
        dt = datetime.datetime(2000+int(yr), MONTH_MAP[mon], int(day),
                               int(hr), int(mn), tzinfo=datetime.timezone.utc)
    except (KeyError, ValueError):
        return None, None, None
    # Split teams_str: e.g. "NYMLAD" → "NYM" + "LAD" (variable length)
    # The game ticker has individual market tickers like KXMLBGAME-...-NYM and KXMLBGAME-...-LAD
    return dt, teams_str, None

def extract_teams_from_market_tickers(market_tickers_str):
    """Extract [team1, team2] from market_tickers field."""
    parts = market_tickers_str.split(',')
    teams = []
    for p in parts:
        m = re.search(r'-([A-Z]{2,4})$', p.strip())
        if m:
            teams.append(m.group(1))
    return teams

# ── Orderbook entry price ──────────────────────────────────────────────────────

def get_entry_price(conn, market_ticker, game_start, window_back_mins=60, target_mins=45):
    """Return (yes_bid, yes_ask) from last ticker event in entry window, or (None, None)."""
    t_target = game_start - datetime.timedelta(minutes=target_mins)
    t_back   = game_start - datetime.timedelta(minutes=window_back_mins)
    rows = conn.execute("""
        SELECT yes_bid, yes_ask, received_at FROM orderbook_events
        WHERE market_ticker=? AND event_type='ticker'
          AND yes_bid IS NOT NULL AND yes_ask IS NOT NULL
          AND received_at <= ? AND received_at >= ?
        ORDER BY received_at DESC LIMIT 1
    """, (market_ticker, t_target.isoformat(), t_back.isoformat())).fetchall()
    if not rows:
        return None, None
    return rows[0][0], rows[0][1]

# ── Signal logic ───────────────────────────────────────────────────────────────

def compute_signal(implied_pct, team_wins, opp_wins):
    """
    Returns (signal_type, strength) or (None, 0).
    Derived from mm2-backtest-spec.md — no signal_generator.py exists.
    strength formula:
      underdog_momentum:    wins * 20 + (40 - implied_pct)   [fires when implied < 40]
      favorite_vs_hot_opp:  opp_wins * 20 + (implied_pct - 65) [fires when implied > 65]
    """
    if implied_pct < 40.0 and team_wins is not None and team_wins >= 3:
        strength = team_wins * 20 + (40.0 - implied_pct)
        if strength >= SIGNAL_STRENGTH_THRESHOLD:
            return 'underdog_momentum', round(strength, 1)
    if implied_pct > 65.0 and opp_wins is not None and opp_wins >= 3:
        strength = opp_wins * 20 + (implied_pct - 65.0)
        if strength >= SIGNAL_STRENGTH_THRESHOLD:
            return 'favorite_vs_hot_opp', round(strength, 1)
    return None, 0

def contracts_for_strength(strength):
    if strength >= 100: return 3
    if strength >= 80:  return 2
    return 1

# ── Main backtest ──────────────────────────────────────────────────────────────

def run_backtest():
    print(f"[{datetime.datetime.now():%H:%M:%S}] Connecting to orderbook DB...")
    conn = sqlite3.connect(ORDERBOOK_DB)

    # Step 1: Fetch all games from DB
    all_games = conn.execute(
        "SELECT event_ticker, market_tickers, game_date FROM games ORDER BY event_ticker"
    ).fetchall()
    print(f"[{datetime.datetime.now():%H:%M:%S}] {len(all_games)} games in DB")

    # Step 2: Build MLB team ID map
    print(f"[{datetime.datetime.now():%H:%M:%S}] Fetching MLB team map...")
    team_map = fetch_team_map()  # abbrev -> id
    time.sleep(0.3)

    # Step 3: Identify all teams appearing in our DB tickers, fetch their schedules
    all_team_codes = set()
    for (event_ticker, market_tickers, _) in all_games:
        teams = extract_teams_from_market_tickers(market_tickers)
        all_team_codes.update(teams)

    print(f"[{datetime.datetime.now():%H:%M:%S}] Teams in DB: {sorted(all_team_codes)}")

    team_schedules = {}  # mlb_abbrev -> [{date, won, ...}]
    for code in sorted(all_team_codes):
        mlb_abbrev = KALSHI_TO_MLB.get(code, code)
        tid = team_map.get(mlb_abbrev)
        if not tid:
            print(f"  WARNING: no MLB team ID for {code}/{mlb_abbrev} — skipping")
            continue
        print(f"  Fetching {code} ({mlb_abbrev}, id={tid})...", end=" ", flush=True)
        try:
            sched = fetch_team_schedule(tid)
            team_schedules[code] = sched
            print(f"{len(sched)} games")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(0.4)

    # Step 4: Iterate games, apply signal, compute P&L
    print(f"\n[{datetime.datetime.now():%H:%M:%S}] Processing games...")

    excl = defaultdict(int)
    trades = []
    daily_pnl = defaultdict(float)
    daily_stop_days = set()

    total_processed = 0
    total_signaled  = 0

    for i, (event_ticker, market_tickers, _) in enumerate(all_games):
        if i % 100 == 0:
            print(f"  {i}/{len(all_games)} games processed, {len(trades)} trades so far")

        game_start, _, _ = parse_ticker(event_ticker)
        if game_start is None:
            excl['parse_error'] += 1
            continue

        game_date = game_start.strftime('%Y-%m-%d')
        teams = extract_teams_from_market_tickers(market_tickers)
        if len(teams) != 2:
            excl['bad_market_tickers'] += 1
            continue

        team_a, team_b = teams[0], teams[1]

        # Get each team's market ticker
        mkt_a = f"{event_ticker}-{team_a}"
        mkt_b = f"{event_ticker}-{team_b}"

        # Get entry prices for both sides
        bid_a, ask_a = get_entry_price(conn, mkt_a, game_start)
        if bid_a is None:
            excl['no_snapshot'] += 1
            continue

        # Compute implied probability for team_a (BUY_YES side)
        mid_a = (bid_a + ask_a) / 2.0
        implied_pct_a = mid_a * 100.0  # convert to percentage points

        # Get recent form
        sched_a = team_schedules.get(team_a)
        sched_b = team_schedules.get(team_b)
        if sched_a is None or sched_b is None:
            excl['missing_recent_form'] += 1
            continue

        wins_a = last5_wins(sched_a, game_date)
        wins_b = last5_wins(sched_b, game_date)
        if wins_a is None or wins_b is None:
            excl['missing_recent_form'] += 1
            continue

        # Get game outcome for team_a
        outcome_a = get_game_outcome(sched_a, game_date)
        if outcome_a is None:
            # Try team_b perspective
            outcome_b = get_game_outcome(sched_b, game_date)
            if outcome_b is None:
                excl['no_outcome'] += 1
                continue
            outcome_a = not outcome_b

        settlement_a = 1.0 if outcome_a else 0.0

        total_processed += 1

        # Apply signal to team_a (BUY_YES on team_a)
        sig_type_a, strength_a = compute_signal(implied_pct_a, wins_a, wins_b)

        # Apply signal to team_b (BUY_YES on team_b = implied_pct_b = 100 - mid_a*100)
        implied_pct_b = 100.0 - implied_pct_a
        sig_type_b, strength_b = compute_signal(implied_pct_b, wins_b, wins_a)

        # Pick strongest signal (only one trade per game)
        if sig_type_a and sig_type_b:
            if strength_a >= strength_b:
                sig_type, strength, buy_team, entry_mid, settlement = sig_type_a, strength_a, team_a, mid_a, settlement_a
            else:
                sig_type, strength, buy_team, entry_mid, settlement = sig_type_b, strength_b, team_b, 1.0 - mid_a, 1.0 - settlement_a
        elif sig_type_a:
            sig_type, strength, buy_team, entry_mid, settlement = sig_type_a, strength_a, team_a, mid_a, settlement_a
        elif sig_type_b:
            sig_type, strength, buy_team, entry_mid, settlement = sig_type_b, strength_b, team_b, 1.0 - mid_a, 1.0 - settlement_a
        else:
            continue  # no signal

        total_signaled += 1

        # Daily loss cap
        if daily_pnl[game_date] <= -DAILY_LOSS_CAP:
            daily_stop_days.add(game_date)
            excl['daily_cap_hit'] += 1
            continue

        contracts = contracts_for_strength(strength)
        pnl = (settlement - entry_mid) * contracts
        daily_pnl[game_date] += pnl

        trades.append({
            'game_date': game_date,
            'ticker': event_ticker,
            'buy_team': buy_team,
            'signal_type': sig_type,
            'strength': strength,
            'entry_price': round(entry_mid * 100, 2),  # in cents
            'contracts': contracts,
            'settlement_price': round(settlement * 100, 1),  # in cents
            'pnl_dollars': round(pnl, 4),
        })

    print(f"[{datetime.datetime.now():%H:%M:%S}] Done. {len(trades)} trades from {total_processed} eligible games.")

    # ── Compute metrics ────────────────────────────────────────────────────────
    net_pnl = sum(t['pnl_dollars'] for t in trades)
    wins_count = sum(1 for t in trades if t['pnl_dollars'] > 0)
    win_rate = wins_count / len(trades) if trades else 0.0

    avg_entry = sum(t['entry_price'] for t in trades) / len(trades) if trades else 0.0
    breakeven_wr = avg_entry / 100.0  # entry price as a fraction = breakeven win rate

    avg_return = net_pnl / len(trades) if trades else 0.0

    # Max drawdown
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x['game_date']):
        running += t['pnl_dollars']
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    # Top-2 trade share
    sorted_profits = sorted([t['pnl_dollars'] for t in trades if t['pnl_dollars'] > 0], reverse=True)
    gross_profit = sum(t['pnl_dollars'] for t in trades if t['pnl_dollars'] > 0)
    top2_share = (sum(sorted_profits[:2]) / gross_profit) if gross_profit > 0 else 0.0

    # By signal type
    by_type = defaultdict(lambda: {'trades':0,'wins':0,'pnl':0.0})
    for t in trades:
        bt = by_type[t['signal_type']]
        bt['trades'] += 1
        if t['pnl_dollars'] > 0:
            bt['wins'] += 1
        bt['pnl'] += t['pnl_dollars']

    # Daily P&L distribution
    daily_dist = [{'date': d, 'pnl': round(v,4)} for d,v in sorted(daily_pnl.items()) if v != 0]

    results = {
        "spec_version": "1.0",
        "backtest_date": datetime.datetime.utcnow().isoformat() + "Z",
        "data_window": {
            "earliest_game": min(t['game_date'] for t in trades) if trades else None,
            "latest_game":   max(t['game_date'] for t in trades) if trades else None,
        },
        "eligibility": {
            "total_games_in_db": len(all_games),
            "eligible_for_backtest": total_processed,
            "signaled": total_signaled,
            "exclusion_breakdown": dict(excl),
        },
        "signal_breakdown": {
            "total_games_signaled": total_signaled,
            "underdog_momentum": by_type['underdog_momentum']['trades'],
            "favorite_vs_hot_opp": by_type['favorite_vs_hot_opp']['trades'],
            "skip_count": total_processed - total_signaled,
        },
        "performance": {
            "trades_executed": len(trades),
            "net_pnl_dollars": round(net_pnl, 2),
            "net_pnl_pct_of_50": round(net_pnl / 50.0 * 100, 1),
            "win_rate": round(win_rate, 4),
            "breakeven_win_rate": round(breakeven_wr, 4),
            "edge_over_breakeven_pp": round((win_rate - breakeven_wr) * 100, 1),
            "avg_return_per_trade": round(avg_return, 4),
            "max_drawdown_dollars": round(max_dd, 2),
            "daily_stop_hits": len(daily_stop_days),
            "top_2_trade_share_of_gross_profit": round(top2_share, 4),
        },
        "by_signal_type": {
            k: {
                "trades": v['trades'],
                "win_rate": round(v['wins']/v['trades'], 4) if v['trades'] else 0,
                "pnl": round(v['pnl'], 2),
            } for k, v in by_type.items()
        },
        "daily_pnl_distribution": daily_dist,
    }

    # Write outputs
    RESULTS_JSON.write_text(json.dumps(results, indent=2))
    print(f"Results → {RESULTS_JSON}")

    with open(TRADES_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['game_date','ticker','buy_team','signal_type',
                                           'strength','entry_price','contracts',
                                           'settlement_price','pnl_dollars'])
        w.writeheader()
        w.writerows(trades)
    print(f"Trades  → {TRADES_CSV}")

    return results

if __name__ == '__main__':
    t0 = time.time()
    results = run_backtest()
    elapsed = time.time() - t0
    p = results['performance']
    print(f"\n{'='*50}")
    print(f"BACKTEST COMPLETE ({elapsed:.0f}s)")
    print(f"Trades:     {p['trades_executed']}")
    print(f"Net P&L:    ${p['net_pnl_dollars']:.2f} ({p['net_pnl_pct_of_50']:.1f}% of $50)")
    print(f"Win rate:   {p['win_rate']:.1%} vs breakeven {p['breakeven_win_rate']:.1%}")
    print(f"Edge:       {p['edge_over_breakeven_pp']:+.1f}pp over breakeven")
    print(f"Max DD:     ${p['max_drawdown_dollars']:.2f}")
    print(f"Daily stops: {p['daily_stop_hits']}")
    print(f"Top-2 share: {p['top_2_trade_share_of_gross_profit']:.1%}")
