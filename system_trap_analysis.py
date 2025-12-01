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

# --- Historical Data Patching ---

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
        return {}

class DateAwareTeamStatDatabase(nhl_model.TeamStatDatabase):
    _current_date = None

    @classmethod
    def set_date(cls, date_str: str):
        if cls._current_date != date_str:
            cls._current_date = date_str
            cls._cache = {}
            cls._standings_loaded = False

    @classmethod
    def _load_standings(cls):
        if cls._standings_loaded: return
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
            gp = cls._cache[code]["gp"]
            if gp > 0:
                cls._cache[code]["gf"] = cls._cache[code]["raw_gf"] / gp
                cls._cache[code]["ga"] = cls._cache[code]["raw_ga"] / gp
                
        cls._standings_loaded = True

nhl_model.TeamStatDatabase = DateAwareTeamStatDatabase

def fetch_boxscore(game_id: int) -> Dict[str, Any]:
    """Fetch boxscore for a game."""
    box_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
    try:
        req = urllib.request.Request(box_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return json.loads(response.read().decode())
    except:
        pass
    return {}

def analyze_system_trap_games():
    """Analyze System Trap games to evaluate scenario fit."""
    
    # Use Nov 30, 2025 slate (all were System Trap games)
    date_str = "2025-11-30"
    DateAwareTeamStatDatabase.set_date(date_str)
    
    fetcher = nhl_model.NHLScheduleFetcher()
    games_data = fetcher.fetch_games(date_str)
    completed_games = [g for g in games_data if g.get('gameState') in ['FINAL', 'OFF', 'OFFICIAL']]
    
    print("=" * 100)
    print("SYSTEM TRAP SCENARIO ANALYSIS")
    print("=" * 100)
    print()
    
    trap_game_analysis = []
    
    for game_data in completed_games:
        game_id = game_data.get('id')
        away_team = game_data.get('awayTeam', {}).get('abbrev', '')
        home_team = game_data.get('homeTeam', {}).get('abbrev', '')
        
        # Parse game
        game_obj = nhl_model.parse_game_from_api(game_data)
        if not game_obj:
            continue
        
        game_obj.date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Analyze scenario
        context = nhl_model.ScenarioAnalyzer.analyze_scenario(game_obj)
        scenarios = context["tags"]
        lean = context["lean"]
        
        # Fetch boxscore for actual results
        box = fetch_boxscore(game_id)
        if not box:
            continue
        
        # Extract actual game stats
        home_score = box.get('homeTeam', {}).get('score', 0)
        away_score = box.get('awayTeam', {}).get('score', 0)
        home_sog = box.get('homeTeam', {}).get('sog', 0)
        away_sog = box.get('awayTeam', {}).get('sog', 0)
        
        total_goals = home_score + away_score
        total_sog = home_sog + away_sog
        
        # Calculate team stats
        home_vol = game_obj.home_team.avg_sog_for + game_obj.home_team.avg_sog_against
        away_vol = game_obj.away_team.avg_sog_for + game_obj.away_team.avg_sog_against
        proj_total_sog = game_obj.home_team.avg_sog_for + game_obj.away_team.avg_sog_for
        
        # Check if System Trap scenarios are present
        is_system_trap = "System Trap" in str(scenarios) or "Trap Game" in scenarios
        
        if is_system_trap:
            analysis = {
                "game": f"{away_team}@{home_team}",
                "game_id": game_id,
                "scenarios": scenarios,
                "lean": lean,
                "home_team": home_team,
                "away_team": away_team,
                "home_stats": {
                    "avg_sog_for": game_obj.home_team.avg_sog_for,
                    "avg_sog_against": game_obj.home_team.avg_sog_against,
                    "goals_for": game_obj.home_team.goals_for_per_game,
                    "goals_against": game_obj.home_team.goals_against_per_game,
                    "vol": home_vol
                },
                "away_stats": {
                    "avg_sog_for": game_obj.away_team.avg_sog_for,
                    "avg_sog_against": game_obj.away_team.avg_sog_against,
                    "goals_for": game_obj.away_team.goals_for_per_game,
                    "goals_against": game_obj.away_team.goals_against_per_game,
                    "vol": away_vol
                },
                "projected": {
                    "total_sog": proj_total_sog,
                    "total_goals": game_obj.home_team.goals_for_per_game + game_obj.away_team.goals_for_per_game
                },
                "actual": {
                    "home_score": home_score,
                    "away_score": away_score,
                    "total_goals": total_goals,
                    "home_sog": home_sog,
                    "away_sog": away_sog,
                    "total_sog": total_sog
                },
                "fit": {
                    "sog_fit": "UNDER" if total_sog < proj_total_sog else "OVER",
                    "goals_fit": "UNDER" if total_goals < (game_obj.home_team.goals_for_per_game + game_obj.away_team.goals_for_per_game) else "OVER",
                    "lean_fit": "CORRECT" if (lean["total"] == "Under" and total_goals < 5.5) or (lean["total"] == "Over" and total_goals > 5.5) else "WRONG"
                }
            }
            
            trap_game_analysis.append(analysis)
    
    # Print detailed analysis
    print(f"Found {len(trap_game_analysis)} System Trap game(s):")
    print()
    
    for i, analysis in enumerate(trap_game_analysis, 1):
        print(f"{'='*100}")
        print(f"Game {i}: {analysis['game']}")
        print(f"{'='*100}")
        print()
        
        print("SCENARIOS DETECTED:")
        for scenario in analysis['scenarios']:
            print(f"  • {scenario}")
        print()
        
        print("LEAN:")
        print(f"  Side: {analysis['lean']['side']}")
        print(f"  Total: {analysis['lean']['total']}")
        print()
        
        print("TEAM STATS:")
        print(f"  {analysis['home_team']}:")
        print(f"    Avg SOG For: {analysis['home_stats']['avg_sog_for']:.1f}")
        print(f"    Avg SOG Against: {analysis['home_stats']['avg_sog_against']:.1f}")
        print(f"    Total Volume: {analysis['home_stats']['vol']:.1f}")
        print(f"    Goals For: {analysis['home_stats']['goals_for']:.2f}")
        print(f"    Goals Against: {analysis['home_stats']['goals_against']:.2f}")
        print()
        print(f"  {analysis['away_team']}:")
        print(f"    Avg SOG For: {analysis['away_stats']['avg_sog_for']:.1f}")
        print(f"    Avg SOG Against: {analysis['away_stats']['avg_sog_against']:.1f}")
        print(f"    Total Volume: {analysis['away_stats']['vol']:.1f}")
        print(f"    Goals For: {analysis['away_stats']['goals_for']:.2f}")
        print(f"    Goals Against: {analysis['away_stats']['goals_against']:.2f}")
        print()
        
        print("PROJECTED vs ACTUAL:")
        print(f"  Total SOG: Projected {analysis['projected']['total_sog']:.1f} | Actual {analysis['actual']['total_sog']} | Fit: {analysis['fit']['sog_fit']}")
        print(f"  Total Goals: Projected {analysis['projected']['total_goals']:.2f} | Actual {analysis['actual']['total_goals']} | Fit: {analysis['fit']['goals_fit']}")
        print(f"  Lean Fit: {analysis['fit']['lean_fit']}")
        print()
        
        # Identify scenario fit issues
        print("SCENARIO FIT ANALYSIS:")
        issues = []
        
        # Check if System Trap was accurate
        if analysis['actual']['total_sog'] > 60:
            issues.append(f"⚠️  System Trap misclassified: Actual SOG ({analysis['actual']['total_sog']}) exceeded threshold (58)")
        
        if analysis['actual']['total_goals'] > 6:
            issues.append(f"⚠️  High scoring despite System Trap: {analysis['actual']['total_goals']} goals")
        
        if analysis['fit']['lean_fit'] == "WRONG":
            issues.append(f"❌ Lean prediction wrong: Predicted {analysis['lean']['total']}, actual was opposite")
        
        # Check for specific patterns
        if "System Trap (Home)" in analysis['scenarios'] and analysis['actual']['home_sog'] > 30:
            issues.append(f"⚠️  Home team generated high volume ({analysis['actual']['home_sog']} SOG) despite System Trap tag")
        
        if "System Trap (Away)" in analysis['scenarios'] and analysis['actual']['away_sog'] > 30:
            issues.append(f"⚠️  Away team generated high volume ({analysis['actual']['away_sog']} SOG) despite System Trap tag")
        
        if "Suppression Siege" in str(analysis['scenarios']) and analysis['actual']['total_goals'] > 5:
            issues.append(f"⚠️  Suppression Siege but high scoring: {analysis['actual']['total_goals']} goals")
        
        if not issues:
            print("  ✅ Scenario fit appears accurate")
        else:
            for issue in issues:
                print(f"  {issue}")
        
        print()
    
    # Summary analysis
    print("=" * 100)
    print("SUMMARY ANALYSIS")
    print("=" * 100)
    print()
    
    # Categorize games by outcome patterns
    categories = {
        "True Low Event": [],  # Low SOG, Low Goals
        "Low SOG, High Goals": [],  # Efficiency game
        "High SOG, Low Goals": [],  # Goalie duel
        "Misclassified": []  # Shouldn't have been System Trap
    }
    
    for analysis in trap_game_analysis:
        total_sog = analysis['actual']['total_sog']
        total_goals = analysis['actual']['total_goals']
        
        if total_sog < 55 and total_goals < 5:
            categories["True Low Event"].append(analysis)
        elif total_sog < 55 and total_goals >= 5:
            categories["Low SOG, High Goals"].append(analysis)
        elif total_sog >= 55 and total_goals < 5:
            categories["High SOG, Low Goals"].append(analysis)
        else:
            categories["Misclassified"].append(analysis)
    
    print("OUTCOME CATEGORIES:")
    for category, games in categories.items():
        if games:
            print(f"\n  {category} ({len(games)} game(s)):")
            for game in games:
                print(f"    • {game['game']}: {game['actual']['total_sog']} SOG, {game['actual']['total_goals']} Goals")
                print(f"      Scenarios: {', '.join(game['scenarios'])}")
    
    print()
    print("=" * 100)
    print("RECOMMENDATIONS")
    print("=" * 100)
    print()
    
    # Generate recommendations based on patterns
    if categories["Low SOG, High Goals"]:
        print("1. EFFICIENCY TRAP SCENARIO:")
        print("   Games with low SOG but high goals suggest high shooting percentage.")
        print("   Consider adding 'Efficiency Trap' scenario for teams with:")
        print("   - Low SOG volume (< 28 SOG/game)")
        print("   - High shooting percentage (> 11%)")
        print("   - Low goals against (< 2.8 GA/game)")
        print()
    
    if categories["High SOG, Low Goals"]:
        print("2. GOALIE DUEL SCENARIO:")
        print("   Games with high SOG but low goals suggest elite goaltending.")
        print("   Consider adding 'Goalie Duel' scenario for games with:")
        print("   - High SOG volume (> 60 total)")
        print("   - Low goals (< 5 total)")
        print("   - Both goalies with high save %")
        print()
    
    if categories["Misclassified"]:
        print("3. SYSTEM TRAP THRESHOLD REFINEMENT:")
        print("   Some games were misclassified as System Trap.")
        print("   Consider:")
        print("   - Stricter threshold (< 56.0 instead of < 58.0)")
        print("   - Require BOTH teams to be low-event")
        print("   - Check recent form (L10 games) not just season averages")
        print()
    
    # Check for specific scenario combinations that need refinement
    print("4. SCENARIO COMBINATION ANALYSIS:")
    scenario_combos = defaultdict(list)
    for analysis in trap_game_analysis:
        combo_key = " + ".join(sorted([s for s in analysis['scenarios'] if "System Trap" in s or "Trap" in s]))
        scenario_combos[combo_key].append(analysis)
    
    for combo, games in scenario_combos.items():
        if len(games) > 0:
            avg_sog = sum(g['actual']['total_sog'] for g in games) / len(games)
            avg_goals = sum(g['actual']['total_goals'] for g in games) / len(games)
            print(f"   '{combo}':")
            print(f"     Games: {len(games)}")
            print(f"     Avg SOG: {avg_sog:.1f}")
            print(f"     Avg Goals: {avg_goals:.1f}")
            print()

if __name__ == "__main__":
    analyze_system_trap_games()
