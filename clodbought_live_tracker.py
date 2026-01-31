#!/usr/bin/env python3
"""
CLODBOUGHT NHL MODEL v5.3.2 - LIVE TRACKING SYSTEM

Usage:
  python3 clodbought_live_tracker.py generate    # Generate today's picks
  python3 clodbought_live_tracker.py grade       # Grade yesterday's picks
  python3 clodbought_live_tracker.py status      # Show tracking status
  python3 clodbought_live_tracker.py report      # Full performance report
"""

import os
import sys
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
TRACKING_DIR = Path.home() / "Downloads" / "clodbought_tracking"
PICKS_FILE = TRACKING_DIR / "picks_log.json"
RESULTS_FILE = TRACKING_DIR / "results_log.json"
MODEL_PATH = Path.home() / "Downloads" / "nhl_model_v5_0_0.py"

def ensure_tracking_dir():
    """Create tracking directory if it doesn't exist."""
    TRACKING_DIR.mkdir(exist_ok=True)
    if not PICKS_FILE.exists():
        with open(PICKS_FILE, 'w') as f:
            json.dump({"picks": []}, f)
    if not RESULTS_FILE.exists():
        with open(RESULTS_FILE, 'w') as f:
            json.dump({"results": [], "summary": {"total_picks": 0, "hits": 0, "misses": 0, "pending": 0}}, f)

def load_picks():
    """Load picks log."""
    with open(PICKS_FILE) as f:
        return json.load(f)

def save_picks(data):
    """Save picks log."""
    with open(PICKS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_results():
    """Load results log."""
    with open(RESULTS_FILE) as f:
        return json.load(f)

def save_results(data):
    """Save results log."""
    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_nhl_games(date_str):
    """Fetch games from NHL API."""
    url = f"https://api-web.nhle.com/v1/score/{date_str}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"Error fetching games: {e}")
        return {}

def get_boxscore(game_id):
    """Fetch boxscore for a game."""
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except:
        return {}

def extract_player_stats(boxscore):
    """Extract player stats from boxscore."""
    stats = {}
    for side in ["homeTeam", "awayTeam"]:
        if side not in boxscore:
            continue
        team = boxscore[side].get("abbrev", "")
        player_stats = boxscore[side].get("playerByGameStats", {})

        for pos in ["forwards", "defense"]:
            for p in player_stats.get(pos, []):
                name = p.get("name", {}).get("default", "")
                stats[name] = {"sog": p.get("sog", 0), "team": team}

        for g in player_stats.get("goalies", []):
            name = g.get("name", {}).get("default", "")
            saves_str = g.get("saveShotsAgainst", "0/0")
            saves = int(saves_str.split("/")[0]) if "/" in saves_str else 0
            stats[name] = {"saves": saves, "team": team}
            stats[f"{team} Goalie"] = {"saves": saves, "team": team}

    return stats

def generate_picks(date_str=None):
    """Generate picks for a date using the model."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*70}")
    print(f"CLODBOUGHT LIVE TRACKER - Generating Picks for {date_str}")
    print(f"{'='*70}\n")

    # Run the model and capture output
    import subprocess
    cmd = f"python3 {MODEL_PATH} --date {date_str}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    output = result.stdout

    # Print model output
    print(output)

    # Parse picks from output
    picks = []
    lines = output.split('\n')
    in_picks_section = False

    for line in lines:
        if "ALIGNED PROPS" in line:
            in_picks_section = True
            continue
        if in_picks_section and line.strip().startswith(('-', '•')):
            continue
        if in_picks_section and "|" in line and ("Under" in line or "Over" in line):
            # Parse pick line like: "  Jared McCann SOG Under 3.5 | Edge: +17.6pp | Prob: 70.0%"
            parts = line.split("|")
            if len(parts) >= 1:
                pick_part = parts[0].strip()
                # Extract player, market, direction, line
                words = pick_part.split()
                if len(words) >= 4:
                    # Find Under/Over position
                    for i, w in enumerate(words):
                        if w in ["Under", "Over"]:
                            player = " ".join(words[:i-1])
                            market = words[i-1]
                            direction = w
                            line = float(words[i+1]) if i+1 < len(words) else 0

                            prob = 0.5
                            if len(parts) >= 3 and "Prob:" in parts[2]:
                                try:
                                    prob = float(parts[2].split(":")[1].strip().replace("%", "")) / 100
                                except:
                                    pass

                            picks.append({
                                "player": player,
                                "market": market,
                                "direction": direction,
                                "line": line,
                                "prob": prob,
                                "date": date_str,
                                "generated_at": datetime.now().isoformat(),
                                "status": "pending"
                            })
                            break

    # Also parse the simpler format from BLIND PICKS section
    for i, line in enumerate(lines):
        if "BLIND PICKS:" in line or ("." in line and ("SOG Under" in line or "SOG Over" in line or "Saves Under" in line or "Saves Over" in line)):
            # Try to parse lines like: "   1. Jared McCann         SOG Under 3.5"
            if ". " in line:
                parts = line.split(". ", 1)
                if len(parts) == 2:
                    pick_text = parts[1].strip()
                    words = pick_text.split()
                    for j, w in enumerate(words):
                        if w in ["Under", "Over"] and j >= 2:
                            player = " ".join(words[:j-1])
                            market = words[j-1]
                            direction = w
                            try:
                                line_val = float(words[j+1]) if j+1 < len(words) else 0
                            except:
                                continue

                            # Check if already added
                            already_exists = any(
                                p["player"] == player and p["market"] == market and p["line"] == line_val
                                for p in picks
                            )
                            if not already_exists:
                                picks.append({
                                    "player": player,
                                    "market": market,
                                    "direction": direction,
                                    "line": line_val,
                                    "prob": 0.6,  # Default
                                    "date": date_str,
                                    "generated_at": datetime.now().isoformat(),
                                    "status": "pending"
                                })
                            break

    # Save picks
    picks_data = load_picks()

    # Remove any existing picks for this date
    picks_data["picks"] = [p for p in picks_data["picks"] if p["date"] != date_str]

    # Add new picks
    picks_data["picks"].extend(picks)
    save_picks(picks_data)

    print(f"\n{'='*70}")
    print(f"SAVED {len(picks)} PICKS FOR {date_str}")
    print(f"{'='*70}")

    # Show summary
    print("\nTOP PICKS (by probability):")
    sorted_picks = sorted(picks, key=lambda x: x["prob"], reverse=True)[:10]
    for i, p in enumerate(sorted_picks, 1):
        print(f"  {i}. {p['player']:20} {p['market']} {p['direction']} {p['line']} ({p['prob']*100:.0f}%)")

    return picks

def grade_picks(date_str=None):
    """Grade picks for a specific date."""
    if date_str is None:
        # Default to yesterday
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"\n{'='*70}")
    print(f"CLODBOUGHT LIVE TRACKER - Grading Picks for {date_str}")
    print(f"{'='*70}\n")

    # Load picks for this date
    picks_data = load_picks()
    day_picks = [p for p in picks_data["picks"] if p["date"] == date_str]

    if not day_picks:
        print(f"No picks found for {date_str}")
        return

    print(f"Found {len(day_picks)} picks to grade\n")

    # Fetch game data
    games = get_nhl_games(date_str)
    if not games.get("games"):
        print("No game data available yet")
        return

    # Collect all player stats
    all_stats = {}
    for game in games.get("games", []):
        box = get_boxscore(game["id"])
        if box:
            stats = extract_player_stats(box)
            all_stats.update(stats)

    # Grade each pick
    results_data = load_results()
    hits = 0
    misses = 0

    print("RESULTS:")
    print("-" * 70)

    for pick in day_picks:
        player = pick["player"]
        market = pick["market"]
        direction = pick["direction"]
        line = pick["line"]

        stat_key = "sog" if market == "SOG" else "saves"
        player_data = all_stats.get(player, {})
        actual = player_data.get(stat_key)

        if actual is None:
            # Try team goalie format
            for name, data in all_stats.items():
                if player in name or (player.endswith("Goalie") and player.split()[0] == data.get("team")):
                    actual = data.get(stat_key)
                    break

        if actual is None:
            print(f"  ? {player:20} {market} {direction} {line} | NOT FOUND")
            pick["status"] = "not_found"
            continue

        if direction == "Under":
            hit = actual < line
            margin = line - actual
        else:
            hit = actual > line
            margin = actual - line

        if hit:
            hits += 1
            status = "✅ HIT"
            pick["status"] = "hit"
        else:
            misses += 1
            status = "❌ MISS"
            pick["status"] = "miss"

        pick["actual"] = actual
        pick["margin"] = margin
        pick["graded_at"] = datetime.now().isoformat()

        print(f"  {status} {player:20} {market} {direction} {line} | Actual: {actual} | Margin: {margin:+.1f}")

    # Update results summary
    total = hits + misses
    if total > 0:
        pct = hits / total * 100
        roi = (hits * 0.91 - misses) / total * 100

        # Add to daily results
        results_data["results"].append({
            "date": date_str,
            "hits": hits,
            "misses": misses,
            "total": total,
            "pct": pct,
            "roi": roi,
            "graded_at": datetime.now().isoformat()
        })

        # Update summary
        results_data["summary"]["total_picks"] += total
        results_data["summary"]["hits"] += hits
        results_data["summary"]["misses"] += misses

        save_results(results_data)
        save_picks(picks_data)

        print("-" * 70)
        print(f"\nDAILY RESULT: {hits}/{total} ({pct:.1f}%)")
        print(f"ROI: {roi:+.1f}%")

        if pct >= 52.4:
            print("✅ PROFITABLE DAY")
        else:
            print("❌ LOSING DAY")

def show_status():
    """Show current tracking status."""
    print(f"\n{'='*70}")
    print("CLODBOUGHT LIVE TRACKER - STATUS")
    print(f"{'='*70}\n")

    picks_data = load_picks()
    results_data = load_results()

    # Pending picks
    pending = [p for p in picks_data["picks"] if p["status"] == "pending"]
    print(f"PENDING PICKS: {len(pending)}")

    if pending:
        dates = set(p["date"] for p in pending)
        for date in sorted(dates):
            day_pending = [p for p in pending if p["date"] == date]
            print(f"  {date}: {len(day_pending)} picks")

    print()

    # Results summary
    summary = results_data["summary"]
    total = summary["total_picks"]

    if total > 0:
        hits = summary["hits"]
        pct = hits / total * 100
        roi = (hits * 0.91 - summary["misses"]) / total * 100

        print(f"CUMULATIVE RESULTS:")
        print(f"  Total Picks:  {total}")
        print(f"  Hits:         {hits}")
        print(f"  Hit Rate:     {pct:.1f}%")
        print(f"  ROI:          {roi:+.1f}%")
        print()

        # By day
        print("DAILY BREAKDOWN:")
        for r in results_data["results"][-10:]:  # Last 10 days
            day_pct = r["pct"]
            grade = "🟢" if day_pct >= 65 else "🟡" if day_pct >= 52.4 else "🔴"
            print(f"  {r['date']}: {r['hits']}/{r['total']} ({day_pct:.1f}%) {grade}")
    else:
        print("No graded results yet")

def show_report():
    """Show full performance report."""
    print(f"\n{'='*70}")
    print("CLODBOUGHT LIVE TRACKER - FULL REPORT")
    print(f"{'='*70}\n")

    results_data = load_results()
    summary = results_data["summary"]
    total = summary["total_picks"]

    if total == 0:
        print("No results to report yet")
        return

    hits = summary["hits"]
    misses = summary["misses"]
    pct = hits / total * 100
    roi = (hits * 0.91 - misses) / total * 100

    # Calculate confidence interval
    import math
    z = 1.96
    p = hits / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    spread = z * math.sqrt((p * (1-p) + z**2 / (4 * total)) / total) / denominator
    lower = max(0, center - spread) * 100
    upper = min(1, center + spread) * 100

    print(f"""
┌─────────────────────────────────────────────────────────────┐
│  CLODBOUGHT v5.3.2 LIVE TRACKING REPORT                    │
├─────────────────────────────────────────────────────────────┤
│  Total Picks:     {total:<6}                                  │
│  Hits:            {hits:<6}                                  │
│  Hit Rate:        {pct:.1f}%                                  │
│  95% CI:          {lower:.1f}% - {upper:.1f}%                      │
│  ROI at -110:     {roi:+.1f}%                                 │
├─────────────────────────────────────────────────────────────┤
│  Days Tracked:    {len(results_data['results']):<6}                                  │
│  Winning Days:    {sum(1 for r in results_data['results'] if r['pct'] > 52.4):<6}                                  │
└─────────────────────────────────────────────────────────────┘
""")

    # Compare to backtest
    print("COMPARISON TO BACKTEST:")
    print(f"  Backtest (Dec-Jan):  72.7%")
    print(f"  Live Tracking:       {pct:.1f}%")
    print(f"  Difference:          {pct - 72.7:+.1f}pp")

    if pct >= 65:
        print("\n✅ MODEL PERFORMING AS EXPECTED")
    elif pct >= 55:
        print("\n⚠️ MODEL UNDERPERFORMING - Monitor closely")
    else:
        print("\n❌ MODEL FAILING - Consider stopping")

def main():
    ensure_tracking_dir()

    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == "generate":
        date_str = sys.argv[2] if len(sys.argv) > 2 else None
        generate_picks(date_str)
    elif command == "grade":
        date_str = sys.argv[2] if len(sys.argv) > 2 else None
        grade_picks(date_str)
    elif command == "status":
        show_status()
    elif command == "report":
        show_report()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)

if __name__ == "__main__":
    main()
