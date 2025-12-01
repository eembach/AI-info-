import datetime
import json
import random
import urllib.request
import sys
from typing import List, Dict, Any

# Import the model
# valid module name check
try:
    import nhl_model_final as nhl_model
except ImportError:
    # Fallback if filename is different in environment
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

def fetch_club_stats_historical(team_abbr: str, date_str: str) -> Dict[str, Any]:
    """
    Fetches club stats. The 'now' endpoint is the only one publicly documented for club-stats.
    However, for 'strict' backtesting, we ideally want historical.
    Since 'club-stats/now' is the only easy one, we will use it BUT relying heavily on 
    the 'standings/{date}' data which IS historical for Team Stats (GF/GA, etc).
    The 'club-stats' is mainly used for SOG data which might not be in standings.
    We will accept the 'current' SOG averages as a minor leakage (SOG averages are stable)
    OR we can try to derive SOG from boxscores if we were truly strict.
    For this exercise, we will trust Standings Data (GF/GA/Record) as the primary 'Scenario' driver
    and accept SOG 'Now' as a proxy, or try to scrape it. 
    Actually, let's just use 'now' for SOG and accept the slight leakage, 
    focusing on the Record/GF/GA being strict.
    """
    # Fallback to current stats for SOG details
    url = f"https://api-web.nhle.com/v1/club-stats/{team_abbr}/now"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return json.loads(response.read().decode())
        return {}
    except Exception as e:
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
                "ga": team.get('goalAgainst', 0) / max(team.get('gamesPlayed', 1), 1), # Approx GA/GP
                # Note: 'goalDifferentialPctg' + 'goalsForPctg' algebra in original was for 'now' endpoint structure?
                # The historical endpoint gives raw 'goalAgainst' and 'gamesPlayed'.
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

# Generate dates for Weeks 5-6 (Nov 1 - Nov 14, 2025)
DATES = []
start_date = datetime.date(2025, 11, 1)
end_date = datetime.date(2025, 11, 14)
delta = datetime.timedelta(days=1)
while start_date <= end_date:
    DATES.append(start_date.strftime("%Y-%m-%d"))
    start_date += delta

def run_backtest():
    total_picks = 0
    correct_picks = 0
    results_log = []

    # 1. Gather Pool of Games
    pool = []
    fetcher = nhl_model.NHLScheduleFetcher()
    
    print(f"Gathering ALL games from {DATES[0]} to {DATES[-1]}...")
    for d in DATES:
        games = fetcher.fetch_games(d)
        for g_data in games:
            if g_data['gameState'] in ['FINAL', 'OFF']: # Ensure played
                 pool.append((d, g_data))
    
    print(f"Found {len(pool)} games in pool.")
    
    # 2. Select Random Sample of 50 Games (Large Scale)
    if len(pool) > 50:
        selected_games = random.sample(pool, 50)
    else:
        selected_games = pool
        
    print(f"Running Strict Backtest (v3.1.5 Depth Edge) on {len(selected_games)} random games...")
    
    # 3. Analyze
    model = nhl_model.NHLModel_Final()
    
    for date_str, game_data in selected_games:
        # Update DB Date context
        DateAwareTeamStatDatabase.set_date(date_str)
        
        # Parse Game (This triggers stat lookup using the patched DB)
        # We need to strip the score from game_data so parse_game_from_api doesn't see it?
        # Actually parse_game_from_api doesn't look at score, it looks at teams/times.
        # But we need to be careful not to use post-game stats.
        
        # Re-parse game cleanly
        game_obj = nhl_model.parse_game_from_api(game_data)
        if not game_obj: continue
        game_obj.date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date() # Fix date
        
        # Run Model via analyze_slate to ensure Conflict Resolution and EV filtering are applied
        # We wrap the single game in a list
        picks = model.analyze_slate([game_obj])
        
        # Select Top Picks (Highest Confidence 5-Star Only)
        # Filter for 5-Star
        five_star = [p for p in picks if p.confidence >= 5.0]
        
        # Sort by Edge
        five_star.sort(key=lambda x: x.edge, reverse=True)
        top_picks = five_star # Take all 5-stars
        
        # Grade Picks
        # Fetch Boxscore for results
        # We can extract results from the original game_data 'awayTeam'/'homeTeam' score/sog
        # But for player props we need the boxscore
        # For this exercise, we might need to fetch the boxscore if the summary isn't enough.
        # game_data has 'awayTeam': {'score': X, 'sog': Y}, but not player stats.
        
        # Fetch full boxscore
        # We use a simple fetcher here
        box_url = f"https://api-web.nhle.com/v1/gamecenter/{game_data['id']}/boxscore"
        try:
            req = urllib.request.Request(box_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                 box = json.loads(response.read().decode())
        except:
            print(f"Failed to fetch box for {game_data['id']}")
            continue
            
        # Helper to find player stats in box
        def get_player_stats(pid, name, box_data, team_abbr):
            stats = {'goals': 0, 'assists': 0, 'points': 0, 'sog': 0, 'saves': 0}
            
            # Special Handling for Goalies (Placeholder Name)
            is_goalie_placeholder = "Goalie" in name
            
            # Extract target last name from model name (e.g. "Auston Matthews" -> "Matthews")
            target_last = name.split()[-1]
            
            teams = box_data.get('playerByGameStats', {})
            found_data = None
            
            # Determine which side the player is on based on team_abbr
            # We pass team_abbr from the game object context if possible, but the Pick doesn't have it.
            # We'll just search both sides.
            
            for side in ['awayTeam', 'homeTeam']:
                t_dat = teams.get(side, {})
                
                # GOALIE LOGIC
                if is_goalie_placeholder:
                    # If we are looking for "TOR Goalie", we need to check if this side IS Toronto.
                    # We can check the boxscore team info
                    box_team_info = box_data.get(side, {})
                    if box_team_info.get('abbrev') == name.split()[0]: # "TOR" == "TOR"
                        # Found the team. Pick the goalie with most TOI (Starter)
                        best_g = None
                        max_toi = -1
                        for g in t_dat.get('goalies', []):
                             # Parse TOI "60:00" -> seconds
                             toi_str = g.get('toi', '00:00')
                             try:
                                 m, s = map(int, toi_str.split(':'))
                                 toi_sec = m * 60 + s
                             except: toi_sec = 0
                             
                             if toi_sec > max_toi:
                                 max_toi = toi_sec
                                 best_g = g
                        found_data = best_g
                        break
                
                # SKATER LOGIC
                else:
                    for group in ['forwards', 'defense', 'goalies']:
                        for p in t_dat.get(group, []):
                            # API Name format: "A. Matthews"
                            api_name_full = p.get('name', {}).get('default', '')
                            # Extract last name
                            api_last = api_name_full.split()[-1]
                            
                            # Compare Last Names (Case Insensitive)
                            if api_last.lower() == target_last.lower():
                                # Double check for common names like "Hughes" (Jack, Quinn, Luke)
                                # If model name is "Jack Hughes", API is "J. Hughes" -> First initial check
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
                stats['sog'] = found_data.get('sog', 0) # API uses 'sog' for skaters
                stats['saves'] = found_data.get('saves', 0) # API uses 'saves' for goalies
            
            return stats, found_data is not None

        print(f"\nGame: {game_obj.id} ({date_str})")
        
        for p in top_picks:
            actual, found = get_player_stats(0, p.player_name, box, "")
            
            if not found:
                print(f"  ? {p.player_name} {p.market} {p.side} {p.line} (Actual: N/A - Not Found) [Conf: {p.confidence}]")
                continue

            val = 0
            if p.market == "Saves": val = actual['saves']
            elif p.market == "SOG": val = actual['sog']
            elif p.market == "Points": val = actual['points']
            elif p.market == "Assists": val = actual['assists']
            elif p.market == "Goals": val = actual['goals']
            
            won = False
            if p.side == "Over" and val > p.line: won = True
            elif p.side == "Under" and val < p.line: won = True
            
            status = "✅" if won else "❌"
            total_picks += 1
            if won: correct_picks += 1
            
            print(f"  {status} {p.player_name} {p.market} {p.side} {p.line} (Actual: {val}) [Conf: {p.confidence}]")
            results_log.append({"game": game_obj.id, "pick": p, "won": won, "actual": val})

    print(f"\n--- Final Results ---")
    print(f"Total Picks: {total_picks}")
    print(f"Correct: {correct_picks}")
    if total_picks > 0:
        print(f"Win Rate: {correct_picks/total_picks*100:.1f}%")

if __name__ == "__main__":
    run_backtest()

