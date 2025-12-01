import nhl_model_v3_0_8 as nhl_model
import json
import urllib.request
import sys

def granular_eval():
    game_id = 2025020308 # SEA @ DET
    date_str = "2025-11-18"
    
    print(f"--- Granular Evaluation: SEA @ DET ({date_str}) ---")
    
    # 1. Setup Environment
    # Note: v3.0.8 TeamStatDatabase does not have set_date method directly in the base class unless patched.
    # We will use the backtester's patched class if possible, or just skip if using live stats proxy is acceptable.
    # Given the previous context, we accepted live stats as proxy for recent games.
    # nhl_model.TeamStatDatabase.set_date(date_str) 

    
    # 2. Fetch Game Data
    fetcher = nhl_model.NHLScheduleFetcher()
    schedule = fetcher.fetch_games(date_str)
    game_data = next((g for g in schedule if g['id'] == game_id), None)
    
    if not game_data:
        print("Game not found.")
        return

    # 3. Parse Game (Blind)
    game = nhl_model.parse_game_from_api(game_data, date_str)
    if not game:
        print("Failed to parse game.")
        return
        
    print(f"Matchup: {game.away_team.code} (Away) vs {game.home_team.code} (Home)")
    
    # 4. Run Model (Full Analysis)
    print("\nRunning Model Analysis...")
    model = nhl_model.NHLModel_v3_0_3() # v3.0.9 class
    
    # First Pass: Strict
    picks = model.analyze_slate([game]) 
    
    print(f"DEBUG: Key Players Count: {len(game.key_players)}")
    
    # Second Pass: Force Mode if needed (to ensure 4 picks)
    if len(picks) < 4:
        print(f"  Strict mode yielded {len(picks)} picks. activating Force Mode to reach 4...")
        # We need to access internal methods to force picks
        # analyze_slate doesn't support force_all arg directly, but we can call internal methods
        context = nhl_model.ScenarioAnalyzer.analyze_scenario(game)
        forced_skater_picks = model._analyze_skaters(game, context['lean'], force_all=True)
        
        # Filter out duplicates
        existing_names = set(p.player_name for p in picks)
        for p in forced_skater_picks:
            if p.player_name not in existing_names:
                picks.append(p)
                
    # Sort by Confidence/EV
    picks.sort(key=lambda x: (x.confidence, x.ev), reverse=True)
    
    # Keep Top 4 (or more)
    if len(picks) > 4:
        picks = picks[:6] # Show top 6 to be safe
    
    print(f"\nModel Generated {len(picks)} Picks:")
    for p in picks:
        print(f"  [{p.confidence}] {p.player_name} {p.market} {p.side} {p.line} | EV: {p.ev:.1f}")
        print(f"     Rationale: {p.rationale}")

    # 5. Reveal Results
    print("\n--- Revealing Boxscore Results ---")
    box_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
    try:
        req = urllib.request.Request(box_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
             box = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching box: {e}")
        return

    def get_actual(name, market):
        name_last = name.split()[-1]
        for side in ['awayTeam', 'homeTeam']:
            for group in ['forwards', 'defense', 'goalies']:
                for p in box['playerByGameStats'][side].get(group, []):
                    if name_last in p['name']['default']:
                        if market == "Saves": return p.get('saves', 0)
                        if market == "SOG": return p.get('sog', 0)
                        if market == "Points": return p.get('points', 0)
                        if market == "Assists": return p.get('assists', 0)
                        if market == "Goals": return p.get('goals', 0)
        return -1

    score_card = []
    for p in picks:
        actual = get_actual(p.player_name, p.market)
        won = False
        if p.side == "Over" and actual > p.line: won = True
        elif p.side == "Under" and actual < p.line: won = True
        
        res_str = "✅ WIN" if won else "❌ LOSS"
        print(f"{res_str}: {p.player_name} {p.market} {p.side} {p.line} (Actual: {actual})")
        score_card.append(won)

    if score_card:
        print(f"\nFinal Grade: {sum(score_card)}/{len(score_card)} ({sum(score_card)/len(score_card)*100:.1f}%)")

if __name__ == "__main__":
    granular_eval()

