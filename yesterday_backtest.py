import datetime
import json
import urllib.request
import sys
from typing import List, Dict, Any
from collections import defaultdict

# Import the model
try:
    import nhl_model_final as nhl_model
except ImportError:
    sys.path.append('.')
    import nhl_model_final as nhl_model

# --- Monkey Patching for Historical Data ---

def fetch_standings_historical(date_str: str) -> Dict[str, Any]:
    """Fetches standings for a specific date."""
    url = f"https://api-web.nhle.com/v1/standings/{date_str}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return json.loads(response.read().decode())
        return {}
    except Exception as e:
        print(f"Error fetching standings for {date_str}: {e}")
        return {}

# Patching TeamStatDatabase to be date-aware
class DateAwareTeamStatDatabase(nhl_model.TeamStatDatabase):
    _current_date = None

    @classmethod
    def set_date(cls, date_str: str):
        if cls._current_date != date_str:
            cls._current_date = date_str
            cls._cache = {} # Clear cache for new date
            cls._standings_loaded = False

    @classmethod
    def _load_standings(cls):
        if cls._standings_loaded: return
        # Use our historical fetcher
        data = fetch_standings_historical(cls._current_date)
        if not data: return
        
        for team in data.get('standings', []):
            code = team.get('teamAbbrev', {}).get('default', '')
            if not code: continue
            
            cls._cache[code] = {
                "gf": team.get('goalsForPctg', 3.0),
                "ga": team.get('goalAgainst', 0) / max(team.get('gamesPlayed', 1), 1),
                "raw_gf": team.get('goalFor', 0),
                "raw_ga": team.get('goalAgainst', 0),
                "gp": team.get('gamesPlayed', 1),
                "l10": f"{team.get('l10Wins',0)}-{team.get('l10Losses',0)}-{team.get('l10OtLosses',0)}",
                "streak": f"{team.get('streakCode','')}{team.get('streakCount',0)}",
                "sog_for": 0.0,
                "sog_against": 0.0
            }
            # Recalculate per game
            gp = cls._cache[code]["gp"]
            if gp > 0:
                cls._cache[code]["gf"] = cls._cache[code]["raw_gf"] / gp
                cls._cache[code]["ga"] = cls._cache[code]["raw_ga"] / gp
                
        cls._standings_loaded = True

# Replace the class in the module
nhl_model.TeamStatDatabase = DateAwareTeamStatDatabase

# --- Backtest Logic ---

def get_yesterday_date():
    """Get yesterday's date. Default to Nov 30, 2025 if not specified."""
    # For strict backtesting, we'll use Nov 30, 2025 as "yesterday" (has completed games)
    return datetime.date(2025, 11, 30)

def fetch_boxscore(game_id: int) -> Dict[str, Any]:
    """Fetch boxscore for a game."""
    box_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
    try:
        req = urllib.request.Request(box_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching boxscore for {game_id}: {e}")
    return {}

def get_player_stats(name: str, box_data: Dict[str, Any], team_abbr: str = "") -> tuple:
    """Extract player stats from boxscore."""
    stats = {'goals': 0, 'assists': 0, 'points': 0, 'sog': 0, 'saves': 0}
    
    is_goalie_placeholder = "Goalie" in name
    target_last = name.split()[-1]
    
    teams = box_data.get('playerByGameStats', {})
    found_data = None
    
    for side in ['awayTeam', 'homeTeam']:
        t_dat = teams.get(side, {})
        
        if is_goalie_placeholder:
            box_team_info = box_data.get(side, {})
            if box_team_info.get('abbrev') == name.split()[0]:
                best_g = None
                max_toi = -1
                for g in t_dat.get('goalies', []):
                    toi_str = g.get('toi', '00:00')
                    try:
                        m, s = map(int, toi_str.split(':'))
                        toi_sec = m * 60 + s
                    except: 
                        toi_sec = 0
                    if toi_sec > max_toi:
                        max_toi = toi_sec
                        best_g = g
                found_data = best_g
                break
        else:
            for group in ['forwards', 'defense', 'goalies']:
                for p in t_dat.get(group, []):
                    api_name_full = p.get('name', {}).get('default', '')
                    api_last = api_name_full.split()[-1]
                    
                    if api_last.lower() == target_last.lower():
                        model_first = name.split()[0]
                        api_first_initial = api_name_full.split()[0][0]
                        
                        if model_first[0].lower() == api_first_initial.lower():
                            found_data = p
                            break
                if found_data: break
        if found_data: break
    
    if found_data:
        stats['goals'] = found_data.get('goals', 0)
        stats['assists'] = found_data.get('assists', 0)
        stats['points'] = found_data.get('points', 0)
        stats['sog'] = found_data.get('sog', 0)
        stats['saves'] = found_data.get('saves', 0)
    
    return stats, found_data is not None

def run_backtest():
    """Run strict blind backtest on yesterday's slate."""
    yesterday = get_yesterday_date()
    date_str = yesterday.strftime("%Y-%m-%d")
    
    print("=" * 80)
    print(f"STRICT BLIND BACKTEST: {date_str}")
    print("=" * 80)
    print(f"Model Version: v3.3.0 (Red Team Improvements + Optimizations)")
    print(f"Using ONLY data available up to {date_str}")
    print()
    
    # Set date context for historical data
    DateAwareTeamStatDatabase.set_date(date_str)
    
    # Fetch games from yesterday
    fetcher = nhl_model.NHLScheduleFetcher()
    games_data = fetcher.fetch_games(date_str)
    
    # Filter for completed games only (OFF means game is over, FINAL means final score posted)
    completed_games = [g for g in games_data if g.get('gameState') in ['FINAL', 'OFF', 'OFFICIAL']]
    
    if not completed_games:
        print(f"No completed games found for {date_str}")
        return
    
    print(f"Found {len(completed_games)} completed game(s) on {date_str}")
    print()
    
    # Initialize model
    model = nhl_model.NHLModel_Final()
    
    # Track results
    total_picks = 0
    correct_picks = 0
    results_by_market = defaultdict(lambda: {'wins': 0, 'losses': 0})
    results_by_confidence = defaultdict(lambda: {'wins': 0, 'losses': 0})
    results_by_side = defaultdict(lambda: {'wins': 0, 'losses': 0})
    results_log = []
    
    # Process each game
    for game_data in completed_games:
        game_id = game_data.get('id')
        away_team = game_data.get('awayTeam', {}).get('abbrev', '')
        home_team = game_data.get('homeTeam', {}).get('abbrev', '')
        
        print(f"\n{'='*80}")
        print(f"Game: {away_team} @ {home_team} (ID: {game_id})")
        print(f"{'='*80}")
        
        # Parse game object
        game_obj = nhl_model.parse_game_from_api(game_data)
        if not game_obj:
            print(f"  ⚠️  Failed to parse game")
            continue
        
        game_obj.date = yesterday
        
        # Run model analysis
        picks = model.analyze_slate([game_obj])
        
        if not picks:
            print(f"  ⚠️  No picks generated")
            continue
        
        # Fetch boxscore for grading
        box = fetch_boxscore(game_id)
        if not box:
            print(f"  ⚠️  Failed to fetch boxscore")
            continue
        
        print(f"\n  Generated {len(picks)} pick(s):")
        print()
        
        # Grade each pick
        for p in picks:
            actual, found = get_player_stats(p.player_name, box)
            
            if not found:
                print(f"  ⚠️  {p.player_name} {p.market} {p.side} {p.line} - Player not found in boxscore")
                continue
            
            # Get actual value
            val = 0
            if p.market == "Saves": val = actual['saves']
            elif p.market == "SOG": val = actual['sog']
            elif p.market == "Points": val = actual['points']
            elif p.market == "Assists": val = actual['assists']
            elif p.market == "Goals": val = actual['goals']
            
            # Determine win/loss
            won = False
            if p.side == "Over" and val > p.line: won = True
            elif p.side == "Under" and val < p.line: won = True
            
            # Update counters
            total_picks += 1
            if won: correct_picks += 1
            
            results_by_market[p.market][('wins' if won else 'losses')] += 1
            results_by_confidence[int(p.confidence)][('wins' if won else 'losses')] += 1
            results_by_side[p.side][('wins' if won else 'losses')] += 1
            
            status = "✅ WIN" if won else "❌ LOSS"
            margin = abs(val - p.line)
            
            print(f"  {status} | {p.player_name:25s} | {p.market:6s} {p.side:5s} {p.line:4.1f} | "
                  f"Actual: {val:4.1f} | Conf: {int(p.confidence)} | EV: {p.ev:5.2f} | "
                  f"Margin: {margin:4.1f}")
            
            results_log.append({
                "game": f"{away_team}@{home_team}",
                "player": p.player_name,
                "market": p.market,
                "side": p.side,
                "line": p.line,
                "actual": val,
                "confidence": p.confidence,
                "ev": p.ev,
                "won": won
            })
    
    # Print summary
    print()
    print("=" * 80)
    print("BACKTEST RESULTS SUMMARY")
    print("=" * 80)
    print()
    
    if total_picks == 0:
        print("No picks to evaluate.")
        return
    
    win_rate = (correct_picks / total_picks) * 100
    print(f"Overall Performance:")
    print(f"  Total Picks: {total_picks}")
    print(f"  Wins: {correct_picks}")
    print(f"  Losses: {total_picks - correct_picks}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print()
    
    print("By Market:")
    for market in sorted(results_by_market.keys()):
        wins = results_by_market[market]['wins']
        losses = results_by_market[market]['losses']
        total = wins + losses
        if total > 0:
            rate = (wins / total) * 100
            print(f"  {market:8s}: {wins:2d}W-{losses:2d}L ({rate:5.1f}%)")
    print()
    
    print("By Confidence:")
    for conf in sorted(results_by_confidence.keys(), reverse=True):
        wins = results_by_confidence[conf]['wins']
        losses = results_by_confidence[conf]['losses']
        total = wins + losses
        if total > 0:
            rate = (wins / total) * 100
            print(f"  {conf}-Star: {wins:2d}W-{losses:2d}L ({rate:5.1f}%)")
    print()
    
    print("By Side:")
    for side in sorted(results_by_side.keys()):
        wins = results_by_side[side]['wins']
        losses = results_by_side[side]['losses']
        total = wins + losses
        if total > 0:
            rate = (wins / total) * 100
            print(f"  {side:5s}: {wins:2d}W-{losses:2d}L ({rate:5.1f}%)")
    print()
    
    # Critical Evaluation
    print("=" * 80)
    print("CRITICAL EVALUATION")
    print("=" * 80)
    print()
    
    # Check if win rate meets threshold
    if win_rate >= 55.0:
        print("✅ Win rate above 55% threshold - Model performing well")
    elif win_rate >= 52.0:
        print("⚠️  Win rate between 52-55% - Model performing adequately")
    else:
        print("❌ Win rate below 52% - Model needs improvement")
    
    # Check 5-star performance
    conf_5_wins = results_by_confidence[5]['wins']
    conf_5_losses = results_by_confidence[5]['losses']
    conf_5_total = conf_5_wins + conf_5_losses
    if conf_5_total > 0:
        conf_5_rate = (conf_5_wins / conf_5_total) * 100
        print(f"\n5-Star Picks: {conf_5_wins}W-{conf_5_losses}L ({conf_5_rate:.1f}%)")
        if conf_5_rate >= 60.0:
            print("  ✅ 5-star picks exceeding 60% - High confidence logic is strong")
        elif conf_5_rate >= 55.0:
            print("  ⚠️  5-star picks at 55-60% - Acceptable but could improve")
        else:
            print("  ❌ 5-star picks below 55% - High confidence logic needs refinement")
    
    # Check market-specific performance
    print("\nMarket-Specific Analysis:")
    for market in sorted(results_by_market.keys()):
        wins = results_by_market[market]['wins']
        losses = results_by_market[market]['losses']
        total = wins + losses
        if total > 0:
            rate = (wins / total) * 100
            if rate >= 55.0:
                print(f"  ✅ {market}: {rate:.1f}% - Strong")
            elif rate >= 50.0:
                print(f"  ⚠️  {market}: {rate:.1f}% - Acceptable")
            else:
                print(f"  ❌ {market}: {rate:.1f}% - Weak, needs improvement")
    
    # Check side performance
    print("\nSide-Specific Analysis:")
    over_wins = results_by_side['Over']['wins']
    over_losses = results_by_side['Over']['losses']
    over_total = over_wins + over_losses
    if over_total > 0:
        over_rate = (over_wins / over_total) * 100
        print(f"  Over: {over_wins}W-{over_losses}L ({over_rate:.1f}%)")
    
    under_wins = results_by_side['Under']['wins']
    under_losses = results_by_side['Under']['losses']
    under_total = under_wins + under_losses
    if under_total > 0:
        under_rate = (under_wins / under_total) * 100
        print(f"  Under: {under_wins}W-{under_losses}L ({under_rate:.1f}%)")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    run_backtest()

