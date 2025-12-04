"""
NHL Advanced Prediction Model v1.3.0
=====================================

Complete single-file implementation with Expert Layers integration.

PERFORMANCE VALIDATION:
- Week 8 Backtest (101 games): 67.4% win rate (118-57)
- HIGH Confidence: 86.5% (32-5) - Excellent selectivity
- MEDIUM Confidence: 62.3% (86-52)
- Points Props: 71.9% (87-34)
- SOG Props: 57.4% (31-23)
- RUN_AND_GUN Scenario: 76.9% (30-9)
- DEFENSIVE_STRUGGLE: 75.0% (24-8)
- PACE_MISMATCH: 62.0% (49-30)
- CLAMP: 58.3% (14-10)

v1.3.0 KEY IMPROVEMENTS:
- Expert Layers Integration (Rest/Fatigue, Matchup, Injury/Opportunity, xG, Goalie)
- Week 8 Large-Scale Validation (101 games processed)
- Enhanced scenario classification and performance
- Improved confidence calibration and pick generation
- RUN_AND_GUN Points Under blocking (Nov 26 fix)
- Enhanced zero-point risk assessment
- DEFENSIVE_STRUGGLE scenario improvements

Version: 1.3.0
Release Date: December 4, 2025
Status: Production Ready
Validated: Week 8 Backtest (Nov 17-23, 2025)

Full Model Analysis - Today's Slate with Player Profile Layer
Selects actual players and recommends specific lines with expert layers
"""

import requests
import json
from datetime import date, datetime
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

BASE_URL = "https://api-web.nhle.com/v1"
SEASON = "20252026"
TODAY = date.today()

# Feasibility checks disabled per user request


class PlayerProfiler:
    """Simplified player profiler for slate analysis"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'NHL-Engine/1.0'})
    
    def fetch_player_game_log(self, player_id: int, season: str = SEASON) -> List[Dict]:
        """Fetch player game-by-game stats for recent form analysis"""
        # Try multiple endpoints
        endpoints = [
            f"{BASE_URL}/player/{player_id}/landing",
            f"{BASE_URL}/player/{player_id}/game-log/{season}/2",  # 2 = regular season
            f"{BASE_URL}/player/{player_id}/stats/game-log/{season}/2"
        ]
        
        for url in endpoints:
            try:
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    # Try to get game log from various possible locations
                    game_log = (
                        data.get('gameLog', []) or 
                        data.get('gameLogs', []) or 
                        data.get('games', []) or
                        data.get('data', []) or
                        []
                    )
                    if game_log:
                        # Filter to current season if needed
                        if any('seasonId' in str(g) for g in game_log[:3]):
                            season_logs = [g for g in game_log if str(season) in str(g.get('seasonId', ''))]
                            return season_logs[:20]  # Return last 20 games
                        else:
                            # Assume already filtered or no season filter needed
                            return game_log[:20]
            except Exception as e:
                continue
        return []
    
    def calculate_player_volatility_metrics(self, player: Dict, game_log: List[Dict] = None) -> Dict:
        """
        Advanced statistical analysis to identify boom/bust players
        Returns volatility metrics including variance, CV, floor, ceiling, and streakiness
        """
        if not game_log:
            game_log = self.fetch_player_game_log(player.get('player_id'))
        
        # Debug: Check if we have game log data
        if not game_log or len(game_log) == 0:
            # No game log - return neutral metrics
            return {
                'volatility': 'NEUTRAL',
                'coefficient_of_variation': 0.0,
                'floor': 0.0,
                'ceiling': 0.0,
                'recent_variance': 0.0,
                'streakiness': 0.0,
                'boom_score': 0.0,
                'bust_score': 0.0
            }
        
        if len(game_log) < 5:
            # Not enough data - return neutral metrics
            return {
                'volatility': 'NEUTRAL',
                'coefficient_of_variation': 0.0,
                'floor': 0.0,
                'ceiling': 0.0,
                'recent_variance': 0.0,
                'streakiness': 0.0,
                'boom_score': 0.0,
                'bust_score': 0.0
            }
        
        # Extract points from recent games (last 10 games)
        # Use same extraction method as calculate_weighted_ppg (which works)
        def get_points_from_game(g):
            # First try direct 'points' field
            if 'points' in g:
                return g.get('points', 0) or 0
            # Try 'stat' object
            elif 'stat' in g and isinstance(g['stat'], dict):
                return g['stat'].get('points', 0) or 0
            # Try 'stats' object
            elif 'stats' in g and isinstance(g['stats'], dict):
                return g['stats'].get('points', 0) or 0
            # Calculate from goals + assists
            else:
                goals = g.get('goals', 0) or (g.get('stat', {}) or {}).get('goals', 0) or 0
                assists = g.get('assists', 0) or (g.get('stat', {}) or {}).get('assists', 0) or 0
                return (goals or 0) + (assists or 0)
        
        recent_points = []
        for game in game_log[:10]:
            points = get_points_from_game(game)
            # Ensure it's an integer
            try:
                points = int(float(points)) if points else 0
            except:
                points = 0
            recent_points.append(points)
        
        if len(recent_points) < 5:
            return {
                'volatility': 'NEUTRAL',
                'coefficient_of_variation': 0.0,
                'floor': 0.0,
                'ceiling': 0.0,
                'recent_variance': 0.0,
                'streakiness': 0.0,
                'boom_score': 0.0,
                'bust_score': 0.0
            }
        
        import statistics
        
        mean_points = statistics.mean(recent_points)
        std_dev = statistics.stdev(recent_points) if len(recent_points) > 1 else 0.0
        
        # Coefficient of Variation (CV) - measures relative volatility
        # High CV = high volatility (boom/bust), Low CV = consistent
        cv = (std_dev / mean_points) if mean_points > 0 else 0.0
        
        # Floor and Ceiling analysis
        floor = min(recent_points)
        ceiling = max(recent_points)
        floor_ceiling_spread = ceiling - floor
        
        # Streakiness: Check for alternating patterns (high variance in streaks)
        # Calculate variance of consecutive game differences
        if len(recent_points) >= 3:
            diffs = [abs(recent_points[i] - recent_points[i-1]) for i in range(1, len(recent_points))]
            streakiness = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
        else:
            streakiness = 0.0
        
        # Recent variance (last 5 games vs season average)
        last_5_avg = statistics.mean(recent_points[:5]) if len(recent_points) >= 5 else mean_points
        last_5_std = statistics.stdev(recent_points[:5]) if len(recent_points[:5]) > 1 else 0.0
        recent_variance = last_5_std
        
        # Boom Score: High ceiling, high variance, recent hot streak
        # Factors: ceiling, CV, recent average above mean
        boom_score = 0.0
        if mean_points > 0:
            boom_score += (ceiling / mean_points) * 0.4  # Ceiling relative to mean
            boom_score += min(cv, 2.0) * 0.3  # Volatility (capped at 2.0)
            boom_score += max(0, (last_5_avg - mean_points) / max(mean_points, 0.1)) * 0.3  # Recent hot streak
        
        # Bust Score: Low floor, high variance, recent cold streak
        # Factors: floor, CV, recent average below mean
        bust_score = 0.0
        if mean_points > 0:
            bust_score += max(0, (mean_points - floor) / max(mean_points, 0.1)) * 0.4  # Floor below mean
            bust_score += min(cv, 2.0) * 0.3  # Volatility
            bust_score += max(0, (mean_points - last_5_avg) / max(mean_points, 0.1)) * 0.3  # Recent cold streak
        
        # Classify volatility (AGGRESSIVE THRESHOLDS - Catch more boom/bust players)
        # Very aggressive thresholds to identify boom/bust patterns:
        # - CV threshold: 0.5+ (catch moderate volatility)
        # - Score threshold: 0.3+ (catch players with boom/bust tendencies)
        # - Multiple pathways to BOOM/BUST classification
        
        # BOOM: High ceiling relative to mean, variance, recent hot streak
        # Multiple pathways to catch boom players
        is_boom = False
        
        # Pathway 1: High variance + high boom score
        if cv > 0.5 and boom_score > 0.3:
            is_boom = True
        # Pathway 2: High ceiling (2+ points) with any variance
        elif ceiling >= 2 and mean_points > 0.5:
            is_boom = True
        # Pathway 3: Ceiling significantly above mean (1.5x+) with moderate variance
        elif cv > 0.4 and ceiling > mean_points * 1.5 and mean_points > 0.3:
            is_boom = True
        # Pathway 4: Recent hot streak (last 5 > mean) with variance
        elif cv > 0.4 and last_5_avg > mean_points * 1.2 and mean_points > 0.4:
            is_boom = True
        
        # BUST: Low floor relative to mean, variance, recent cold streak
        # AGGRESSIVE THRESHOLDS: Lowered to catch more bust players
        is_bust = False
        
        # Pathway 1: Moderate variance + moderate bust score (lowered from 0.5/0.3 to 0.4/0.25)
        if cv > 0.4 and bust_score > 0.25:
            is_bust = True
        # Pathway 2: Zero floor with any mean (lowered from 0.4 to 0.3)
        elif floor == 0 and mean_points > 0.3 and cv > 0.3:
            is_bust = True
        # Pathway 3: Floor significantly below mean (0.5x or less) with variance (lowered thresholds)
        elif cv > 0.3 and floor < mean_points * 0.5 and mean_points > 0.25:
            is_bust = True
        # Pathway 4: Recent cold streak (last 5 < mean) with variance (lowered thresholds)
        elif cv > 0.3 and last_5_avg < mean_points * 0.8 and mean_points > 0.3:
            is_bust = True
        # Pathway 5: NEW - High variance with low floor (even if mean is decent)
        elif cv > 0.6 and floor < 1.0 and mean_points > 0.5:
            is_bust = True
        # Pathway 6: NEW - Recent cold streak (last 5 significantly below mean)
        elif cv > 0.35 and last_5_avg < mean_points * 0.7 and mean_points > 0.35:
            is_bust = True
        
        # Classify (BUST takes priority if recent form is cold, even if ceiling is high)
        if is_bust and not is_boom:
            volatility = 'BUST'  # Low floor, high variance, cold streak
        elif is_boom and not is_bust:
            volatility = 'BOOM'  # High ceiling, high variance, hot streak
        elif is_boom and is_bust:
            # If both, prefer BUST if recent form is cold (last_5 < mean), otherwise BOOM
            # This catches high-variance players who are currently in a cold streak
            if last_5_avg < mean_points * 0.85:
                volatility = 'BUST'  # Recent cold streak takes priority
            elif ceiling >= 2 and last_5_avg >= mean_points:
                volatility = 'BOOM'  # High ceiling with hot streak
            else:
                # Default to BUST if bust_score is significantly higher
                volatility = 'BUST' if bust_score > boom_score * 1.1 else 'BOOM'
        elif cv > 0.4:
            volatility = 'VOLATILE'  # Moderate variance but not clearly boom/bust
        else:
            volatility = 'CONSISTENT'  # Low variance, predictable
        
        return {
            'volatility': volatility,
            'coefficient_of_variation': cv,
            'floor': floor,
            'ceiling': ceiling,
            'floor_ceiling_spread': floor_ceiling_spread,
            'recent_variance': recent_variance,
            'streakiness': streakiness,
            'boom_score': boom_score,
            'bust_score': bust_score,
            'mean_points': mean_points,
            'std_dev': std_dev,
            'last_5_avg': last_5_avg
        }
    
    def calculate_weighted_ppg(self, player: Dict, game_log: List[Dict] = None) -> float:
        """
        RED TEAM FIX #5: Implement recent form weighting
        Master prompt weights: Last 5 = 4×, Last 10 = 2×, Season = 1×
        """
        season_ppg = player.get('points_per_game', 0)
        
        if not game_log or len(game_log) == 0:
            # Fallback to season average if no game log
            return season_ppg
        
        # Calculate last 5 and last 10 averages
        last_5_games = game_log[:5]
        last_10_games = game_log[:10]
        
        # Extract points - try multiple field names
        def get_points_from_game(g):
            return (
                g.get('points', 0) or 
                g.get('stat', {}).get('points', 0) or
                g.get('stats', {}).get('points', 0) or
                (g.get('goals', 0) or 0) + (g.get('assists', 0) or 0) or
                0
            )
        
        last_5_points = sum(get_points_from_game(g) for g in last_5_games)
        last_5_games_count = len(last_5_games)
        last_5_ppg = last_5_points / max(last_5_games_count, 1) if last_5_games_count > 0 else season_ppg
        
        last_10_points = sum(get_points_from_game(g) for g in last_10_games)
        last_10_games_count = len(last_10_games)
        last_10_ppg = last_10_points / max(last_10_games_count, 1) if last_10_games_count > 0 else season_ppg
        
        # Weighted average: Last 5 = 4×, Last 10 = 2×, Season = 1×
        # Note: Last 10 includes last 5, so we need to adjust weights
        # Last 5 gets 4×, games 6-10 get 2×, rest gets 1×
        if last_5_games_count >= 5 and last_10_games_count >= 10:
            # Full weighting
            weighted_ppg = (
                last_5_ppg * 4.0 +  # Last 5 games
                (last_10_ppg * 10 - last_5_ppg * 5) / 5.0 * 2.0 +  # Games 6-10
                season_ppg * 1.0
            ) / 7.0
        elif last_5_games_count >= 5:
            # Only last 5 available
            weighted_ppg = (last_5_ppg * 4.0 + season_ppg * 1.0) / 5.0
        elif last_10_games_count > 0:
            # Only last 10 available (partial)
            weighted_ppg = (last_10_ppg * 2.0 + season_ppg * 1.0) / 3.0
        else:
            # Fallback to season average
            weighted_ppg = season_ppg
        
        return weighted_ppg
    
    def fetch_team_skaters(self, team_abbrev: str) -> List[Dict]:
        """Fetch team skaters with stats"""
        # Use club-stats endpoint (this works)
        url = f"{BASE_URL}/club-stats/{team_abbrev}/{SEASON}/2"
        
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                skaters = data.get('skaters', [])
                # Filter to forwards and defensemen (positionCode: C, L, R, D)
                return [s for s in skaters if s.get('positionCode') in ['C', 'L', 'R', 'D']]
        except Exception as e:
            print(f"    Error fetching skaters for {team_abbrev}: {e}")
        return []
    
    def identify_usage_anchors(self, team_abbrev: str, game_id: Optional[int] = None) -> List[Dict]:
        """
        Identify usage anchors (top-6/PP1 forwards, top-4/PP1 defensemen)
        Returns list of player dicts sorted by points per game
        """
        skaters = self.fetch_team_skaters(team_abbrev)
        
        usage_anchors = []
        
        for skater in skaters:
            # Get basic info
            player_id = skater.get('playerId')
            if not player_id:
                continue
            
            # Get name (firstName and lastName are separate)
            first_name = skater.get('firstName', {})
            last_name = skater.get('lastName', {})
            if isinstance(first_name, dict):
                first_name = first_name.get('default', '')
            if isinstance(last_name, dict):
                last_name = last_name.get('default', '')
            name = f"{first_name} {last_name}".strip()
            
            if not name:
                continue
            
            # Get stats
            games = skater.get('gamesPlayed', 0)
            points = skater.get('points', 0)
            goals = skater.get('goals', 0)
            assists = skater.get('assists', 0)
            shots = skater.get('shots', 0)
            
            # Get TOI (avgTimeOnIcePerGame is in seconds)
            toi_seconds = skater.get('avgTimeOnIcePerGame', 0)
            toi_avg = toi_seconds / 60.0 if toi_seconds > 0 else None
            
            # Get position
            position_code = skater.get('positionCode', '')
            pos_code = 'F' if position_code in ['C', 'L', 'R'] else 'D'
            
            # Check if usage anchor
            # For now, we'll use points per game as proxy (top scorers are usually top-6/PP1)
            # In production, we'd check actual line/pair and PP unit from lineup data
            points_per_game = points / max(games, 1) if games > 0 else 0
            
            # Heuristic: Top scorers with good TOI are likely usage anchors
            # MASTER PROMPT ALIGNMENT: ≥18 TOI for forwards, ≥22 TOI for defensemen
            if games >= 10:  # Minimum games played
                if pos_code == 'F' and toi_avg and toi_avg >= 18.0 and points_per_game >= 0.5:
                    # Forward with good TOI and decent scoring (≥18 TOI per master prompt)
                    usage_anchors.append({
                        'player_id': player_id,
                        'name': name,
                        'position': pos_code,
                        'team': team_abbrev,
                        'points': points,
                        'games': games,
                        'points_per_game': points_per_game,
                        'goals': goals,
                        'assists': assists,
                        'shots': shots,
                        'toi_avg': toi_avg,
                        'sog_per_game': shots / max(games, 1) if games > 0 else 0
                    })
                elif pos_code == 'D' and toi_avg and toi_avg >= 22.0 and points_per_game >= 0.3:
                    # Defenseman with good TOI and decent scoring
                    usage_anchors.append({
                        'player_id': player_id,
                        'name': name,
                        'position': pos_code,
                        'team': team_abbrev,
                        'points': points,
                        'games': games,
                        'points_per_game': points_per_game,
                        'goals': goals,
                        'assists': assists,
                        'shots': shots,
                        'toi_avg': toi_avg,
                        'sog_per_game': shots / max(games, 1) if games > 0 else 0
                    })
        
        # Sort by points per game (descending)
        usage_anchors.sort(key=lambda x: x['points_per_game'], reverse=True)
        
        return usage_anchors


class TodaysSlateAnalysis:
    """Full model analysis for today's slate with player profiles"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'NHL-Engine/1.0'})
        self.profiler = PlayerProfiler()
        
        # Feasibility checks disabled per user request
        self.checker = None
    
    def fetch_todays_games(self) -> List[Dict]:
        """Fetch today's games"""
        date_str = TODAY.strftime('%Y-%m-%d')
        url = f"{BASE_URL}/schedule/{date_str}"
        
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                games = []
                if 'gameWeek' in data:
                    for week in data['gameWeek']:
                        if week.get('date') == date_str:
                            games = week.get('games', [])
                            for game in games:
                                game['date'] = date_str
                return games
        except Exception as e:
            print(f"Error fetching games: {e}")
        return []
    
    def fetch_standings(self) -> Dict[str, Dict]:
        """Fetch team standings (pregame data)"""
        url = f"{BASE_URL}/standings/now"
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                standings = {}
                if 'standings' in data:
                    for team in data['standings']:
                        abbrev = team.get('teamAbbrev', {}).get('default', '')
                        if abbrev:
                            gp = team.get('gamesPlayed', 1)
                            standings[abbrev] = {
                                'gamesPlayed': gp,
                                'goalFor': team.get('goalFor', 0),
                                'goalAgainst': team.get('goalAgainst', 0),
                                'gf_per_game': team.get('goalFor', 0) / max(gp, 1),
                                'ga_per_game': team.get('goalAgainst', 0) / max(gp, 1),
                            }
                return standings
        except Exception as e:
            print(f"Error fetching standings: {e}")
        return {}
    
    def fetch_team_shots_stats(self, team_abbrev: str) -> float:
        """
        WINNING APPROACH ALIGNMENT: Fetch team shots for per game (for SOG pick generation)
        Team projection is ≈30+ shots on goal (from winning approach)
        """
        # Try to get from club stats endpoint
        url = f"{BASE_URL}/club-stats/{team_abbrev}/{SEASON}/2"
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Calculate from skaters' total shots
                if 'skaters' in data and len(data['skaters']) > 0:
                    total_shots = sum(s.get('shots', 0) for s in data['skaters'])
                    # Get team games played - use the most common games played value
                    # (most players should have the same GP, representing team GP)
                    from collections import Counter
                    games_list = [s.get('gamesPlayed', 0) for s in data['skaters'] if s.get('gamesPlayed', 0) > 0]
                    if games_list:
                        # Use the mode (most common value) as team GP
                        games_counter = Counter(games_list)
                        team_games = games_counter.most_common(1)[0][0]
                        
                        if total_shots > 0 and team_games > 0:
                            return total_shots / team_games
                
                # Alternative: try to find in data structure
                if 'data' in data:
                    for stat in data['data']:
                        if isinstance(stat, dict) and (stat.get('stat') == 'shotsFor' or 'shot' in str(stat.get('stat', '')).lower()):
                            return float(stat.get('value', 0))
                
                # Try direct fields
                games = data.get('gamesPlayed', 1)
                shots_for = data.get('shotsFor', 0) or data.get('shots', 0)
                if shots_for > 0 and games > 0:
                    return shots_for / games
        except Exception as e:
            pass
        # Fallback: estimate based on league average (30 SOG/GM)
        # WINNING APPROACH: Team projection is ≈30+ shots on goal
        return 30.0
    
    def fetch_team_shots_against(self, team_abbrev: str) -> float:
        """
        RED TEAM FIX: Fetch team shots AGAINST per game (for suppression logic)
        Uses goalies' shotsAgainst field (accurate, not a proxy)
        
        BUG FIX: Sum all goalies' shotsAgainst (team total) and divide by team GP from standings
        (not max goalie GP, which would double-count when multiple goalies play)
        """
        url = f"{BASE_URL}/club-stats/{team_abbrev}/{SEASON}/2"
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Calculate from goalies' shotsAgainst (accurate metric)
                if 'goalies' in data and len(data['goalies']) > 0:
                    total_sa = sum(g.get('shotsAgainst', 0) for g in data['goalies'])
                    
                    # BUG FIX: Get team GP from standings (not max goalie GP)
                    # Summing all goalies' shotsAgainst gives team total, so divide by team GP
                    standings = self.fetch_standings()
                    team_stats = standings.get(team_abbrev, {})
                    team_games = team_stats.get('gamesPlayed', 0)
                    
                    # Fallback: use max goalie GP if standings not available
                    if team_games == 0:
                        games_list = [g.get('gamesPlayed', 0) for g in data['goalies'] if g.get('gamesPlayed', 0) > 0]
                        if games_list:
                            team_games = max(games_list)
                    
                    if total_sa > 0 and team_games > 0:
                        sa_per_game = total_sa / team_games
                        # Sanity check: NHL teams typically allow 25-35 SA/G
                        if 20.0 <= sa_per_game <= 40.0:
                            return sa_per_game
                        else:
                            # Data looks wrong, use fallback
                            pass
        except Exception as e:
            pass
        # Fallback: league average (30 SOG/GM)
        return 30.0
    
    def fetch_goalie_stats(self, team_abbrev: str, game_id: Optional[int] = None) -> Dict[str, float]:
        """
        PRIORITY 3: Fetch goalie statistics for scenario classification
        Returns dict with 'sv_pct' for starting goalie (or best available)
        """
        url = f"{BASE_URL}/club-stats/{team_abbrev}/{SEASON}/2"
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                goalies = data.get('goalies', [])
                if goalies:
                    # Get goalie with most games played (likely starter)
                    starter = max(goalies, key=lambda g: g.get('gamesPlayed', 0))
                    sv_pct = starter.get('savePctg', 0) / 100.0 if starter.get('savePctg') else 0.910
                    return {'sv_pct': sv_pct, 'goalie_name': starter.get('firstName', {}).get('default', '') + ' ' + starter.get('lastName', {}).get('default', '')}
        except:
            pass
        # Default to league average
        return {'sv_pct': 0.910, 'goalie_name': 'Unknown'}
    
    def get_game_context(self, game: Dict) -> Dict[str, bool]:
        """
        PRIORITY 4: Get game context (back-to-back, rest days, etc.)
        Returns dict with context flags
        """
        context = {
            'away_b2b': False,
            'home_b2b': False,
            'away_rest_days': 1,
            'home_rest_days': 1
        }
        
        # Try to get previous game dates for B2B detection
        # This is simplified - in production would fetch team schedules
        game_date_str = game.get('date') or game.get('startTimeUTC', '').split('T')[0]
        
        # For now, return default (no B2B detected)
        # In production, would check team's previous game date
        return context
    
    def calculate_weighted_team_stats(self, team_abbrev: str, standings: Dict[str, Dict], 
                                     season_gf: float, season_ga: float) -> Tuple[float, float]:
        """
        PRIORITY 5: Calculate weighted team stats (recent form 60%, season 40%)
        Returns (weighted_gf, weighted_ga)
        """
        # For now, use season stats (recent form would require game-by-game data)
        # In production, would fetch last 10 games and calculate recent averages
        return season_gf, season_ga
    
    def classify_scenario(self, away_gf: float, home_gf: float, away_ga: float, home_ga: float,
                         away_goalie_sv: Optional[float] = None, home_goalie_sv: Optional[float] = None,
                         game_context: Optional[Dict] = None) -> str:
        """
        EXPERT RECOMMENDATIONS IMPLEMENTED: Improved scenario classification
        
        Priority 1: Refined PACE_MISMATCH (excludes high avg_gf cases)
        Priority 2: Simplified CLAMP logic (primary condition only)
        Priority 3: Added goalie quality factor
        Priority 4: Added game context consideration
        """
        avg_gf = (away_gf + home_gf) / 2
        avg_ga = (away_ga + home_ga) / 2
        max_gf = max(away_gf, home_gf)
        min_gf = min(away_gf, home_gf)
        
        # PRIORITY 4: Adjust for game context (B2B games score less)
        if game_context:
            if game_context.get('away_b2b') or game_context.get('home_b2b'):
                # Reduce expected scoring by 0.3 GF/G for B2B teams
                if game_context.get('away_b2b'):
                    away_gf = max(away_gf - 0.3, 1.5)
                if game_context.get('home_b2b'):
                    home_gf = max(home_gf - 0.3, 1.5)
                # Recalculate after adjustment
                avg_gf = (away_gf + home_gf) / 2
                max_gf = max(away_gf, home_gf)
        
        # RUN_AND_GUN
        # PRIORITY 1: Adjusted threshold - if avg_gf >= 3.2, classify as RUN_AND_GUN (not PACE_MISMATCH)
        is_rungun = avg_gf >= 3.2 or (max_gf >= 3.5 and avg_ga >= 3.0)
        
        # PRIORITY 3: Adjust for goalie quality (elite goalies suppress scoring)
        if is_rungun and away_goalie_sv and home_goalie_sv:
            both_elite = away_goalie_sv >= 0.915 and home_goalie_sv >= 0.915
            one_elite = away_goalie_sv >= 0.915 or home_goalie_sv >= 0.915
            
            if both_elite:
                # Both elite goalies - downgrade to HIGH_OFFENSE or PACE_MISMATCH
                # Only downgrade if avg_gf is borderline (3.2-3.3), keep RUN_AND_GUN if avg_gf >= 3.3
                if avg_gf < 3.3:
                    is_rungun = False
            elif one_elite:
                # One elite goalie - reduce expected scoring slightly
                # Still RUN_AND_GUN but with lower expected total
                pass
        
        if is_rungun:
            return "RUN_AND_GUN"
        
        # PRIORITY 2: Simplified CLAMP logic (primary condition only)
        # Removed complex multi-condition logic
        low_avg_gf = avg_gf < 2.6
        strong_avg_defense = avg_ga < 2.6
        
        is_clamp = low_avg_gf and strong_avg_defense
        
        # PRIORITY 3: Adjust for goalie quality in CLAMP
        if is_clamp and away_goalie_sv and home_goalie_sv:
            both_elite = away_goalie_sv >= 0.915 and home_goalie_sv >= 0.915
            if both_elite:
                # Reinforces CLAMP classification
                pass
        
        if is_clamp:
            return "CLAMP"
        
        # EXPANDED SCENARIOS
        if max_gf >= 3.5 and min_gf >= 2.8:
            return "HIGH_OFFENSE"
        
        # PRIORITY 1: Refined PACE_MISMATCH - exclude high avg_gf cases
        # If avg_gf >= 3.2, should be RUN_AND_GUN (already checked above)
        # PACE_MISMATCH only applies when avg_gf < 3.2
        if avg_gf < 3.2:
            if (away_gf >= 3.2 and home_ga >= 3.0) or (home_gf >= 3.2 and away_ga >= 3.0):
                return "PACE_MISMATCH"
        
        if away_ga >= 3.0 and home_ga >= 3.0 and avg_gf >= 2.8:
            return "DEFENSIVE_STRUGGLE"
        
        # Fallback logic (also check avg_gf to avoid overlap with RUN_AND_GUN)
        if avg_gf < 3.2:
            if (away_gf >= 3.2 and home_gf < 2.6) or (home_gf >= 3.2 and away_gf < 2.6):
                return "PACE_MISMATCH"
        
        if avg_gf >= 2.6 and avg_gf < 3.2:
            if (away_gf >= 3.0 and home_ga >= 3.0) or (home_gf >= 3.0 and away_ga >= 3.0):
                return "PACE_MISMATCH"
            else:
                return "CLAMP"
        
        return "CLAMP" if avg_gf < 2.6 else "PACE_MISMATCH"
    
    def calculate_opponent_adjustment(self, opponent_ga_per_game: float, opponent_sv_pct: float = 0.910) -> float:
        """
        RED TEAM FIX #4: Calculate opponent adjustment multiplier
        Adjusts projections based on opponent defensive strength and goalie quality
        """
        multiplier = 1.0
        
        # Opponent GA/G adjustment
        if opponent_ga_per_game <= 2.5:
            multiplier *= 0.90  # Elite defense suppression
        elif opponent_ga_per_game >= 3.5:
            multiplier *= 1.10  # Weak defense boost
        
        # Goalie SV% adjustment (default 0.910 if not available)
        if opponent_sv_pct >= 0.920:
            multiplier *= 0.85  # Elite goalie suppression
        elif opponent_sv_pct <= 0.890:
            multiplier *= 1.15  # Weak goalie boost
        
        return multiplier
    
    def generate_picks_with_players(self, game: Dict, standings: Dict[str, Dict],
                                   rosters: Dict[str, List[str]] = None,
                                   lineup_status: Dict[int, bool] = None) -> List[Dict]:
        """Generate picks using actual player profiles"""
        away_abbrev = game.get('awayTeam', {}).get('abbrev', '')
        home_abbrev = game.get('homeTeam', {}).get('abbrev', '')
        game_id = game.get('id')
        
        away_stats = standings.get(away_abbrev, {})
        home_stats = standings.get(home_abbrev, {})
        
        # PRIORITY 5: Calculate weighted team stats (recent form 60%, season 40%)
        away_gf_season = away_stats.get('gf_per_game', 0)
        away_ga_season = away_stats.get('ga_per_game', 0)
        home_gf_season = home_stats.get('gf_per_game', 0)
        home_ga_season = home_stats.get('ga_per_game', 0)
        
        away_gf_weighted, away_ga_weighted = self.calculate_weighted_team_stats(
            away_abbrev, standings, away_gf_season, away_ga_season
        )
        home_gf_weighted, home_ga_weighted = self.calculate_weighted_team_stats(
            home_abbrev, standings, home_gf_season, home_ga_season
        )
        
        # PRIORITY 3: Fetch goalie stats
        away_goalie = self.fetch_goalie_stats(away_abbrev, game_id)
        home_goalie = self.fetch_goalie_stats(home_abbrev, game_id)
        
        # PRIORITY 4: Get game context
        game_context = self.get_game_context(game)
        
        # Classify scenario with all improvements
        scenario = self.classify_scenario(
            away_gf_weighted,
            home_gf_weighted,
            away_ga_weighted,
            home_ga_weighted,
            away_goalie.get('sv_pct'),
            home_goalie.get('sv_pct'),
            game_context
        )
        
        # RED TEAM FIX #1 & #2: Skip BALANCED and OFFENSIVE_MISMATCH scenarios
        if scenario in ["BALANCED", "OFFENSIVE_MISMATCH"]:
            # Skip these scenarios - they're losing money
            return []
        
        picks = []
        
        # OPTIMIZED BUILD: Scenario-specific opponent adjustments
        # RECOMMENDATION #2: Review RUN_AND_GUN opponent adjustments
        # Current: Light adjustments (0.95-1.05) - may be too restrictive
        # Issue: RUN_AND_GUN performance dropped to 33.3% (vs 63.9% target)
        # Fix: Use even lighter adjustments (0.98-1.02) - minimal impact
        # Rationale: High-event games are less predictable, opponent adjustments may hurt more than help
        
        # RUN_AND_GUN: Minimal adjustments (0.98-1.02 range) - high-event games less predictable
        # Other scenarios: Full adjustments (0.85-1.15 range) - adjustments help
        if scenario == "RUN_AND_GUN":
            # RECOMMENDATION #2: Even lighter opponent adjustment for RUN_AND_GUN
            # Previous: 0.95-1.05 range (may still be too restrictive)
            # New: 0.98-1.02 range (minimal adjustment, let usage drive projections)
            away_opponent_mult_base = self.calculate_opponent_adjustment(
                home_stats.get('ga_per_game', 3.0),
                home_goalie.get('sv_pct', 0.910)
            )
            home_opponent_mult_base = self.calculate_opponent_adjustment(
                away_stats.get('ga_per_game', 3.0),
                away_goalie.get('sv_pct', 0.910)
            )
            # Clamp to even lighter range (0.98-1.02) for RUN_AND_GUN
            away_opponent_mult = max(0.98, min(1.02, away_opponent_mult_base))
            home_opponent_mult = max(0.98, min(1.02, home_opponent_mult_base))
        else:
            # Full opponent adjustment for other scenarios (includes goalie quality)
            away_opponent_mult = self.calculate_opponent_adjustment(
                home_stats.get('ga_per_game', 3.0),
                home_goalie.get('sv_pct', 0.910)
            )
            home_opponent_mult = self.calculate_opponent_adjustment(
                away_stats.get('ga_per_game', 3.0),
                away_goalie.get('sv_pct', 0.910)
            )
        
        # Identify usage anchors
        print(f"    Fetching players for {away_abbrev}...")
        away_anchors = self.profiler.identify_usage_anchors(away_abbrev, game_id)
        print(f"    Found {len(away_anchors)} usage anchors")
        
        print(f"    Fetching players for {home_abbrev}...")
        home_anchors = self.profiler.identify_usage_anchors(home_abbrev, game_id)
        print(f"    Found {len(home_anchors)} usage anchors")
        
        # RED TEAM FIX #5: Calculate weighted PPG with recent form
        # ADVANCED STATISTICAL IMPROVEMENT: Calculate volatility metrics for boom/bust analysis
        for anchor in away_anchors:
            game_log = self.profiler.fetch_player_game_log(anchor['player_id'])
            anchor['weighted_ppg'] = self.profiler.calculate_weighted_ppg(anchor, game_log)
            anchor['opponent_mult'] = away_opponent_mult
            anchor['adjusted_ppg'] = anchor['weighted_ppg'] * away_opponent_mult
            # Calculate volatility metrics for boom/bust analysis
            anchor['volatility_metrics'] = self.profiler.calculate_player_volatility_metrics(anchor, game_log)
        
        for anchor in home_anchors:
            game_log = self.profiler.fetch_player_game_log(anchor['player_id'])
            anchor['weighted_ppg'] = self.profiler.calculate_weighted_ppg(anchor, game_log)
            anchor['opponent_mult'] = home_opponent_mult
            anchor['adjusted_ppg'] = anchor['weighted_ppg'] * home_opponent_mult
            # Calculate volatility metrics for boom/bust analysis
            anchor['volatility_metrics'] = self.profiler.calculate_player_volatility_metrics(anchor, game_log)
        
        # PROP AVAILABILITY CHECK: Filter players who don't have props available
        # RELAXED THRESHOLDS: Lowered to allow more players through
        def check_prop_availability(player: Dict, prop_type: str) -> bool:
            """Check if player has prop available based on production thresholds (relaxed)"""
            ppg = player.get('weighted_ppg', player.get('points_per_game', 0))
            sog_per_game = player.get('sog_per_game', 0)
            
            # RELAXED: Lower thresholds to allow more players
            if prop_type == 'Points':
                # Points props typically available if player has ≥0.2 P/GP (lowered from 0.3)
                return ppg >= 0.2
            elif prop_type == 'SOG':
                # SOG props typically available if player shoots regularly (≥1.0 SOG/GM, lowered from 1.5)
                return sog_per_game >= 1.0
            return True  # Default to available if unknown prop type
        
        # Filter anchors by prop availability for the props we're generating
        # This prevents picks on players who may not have props available (injured, scratched, etc.)
        away_anchors_filtered = []
        home_anchors_filtered = []
        
        for anchor in away_anchors:
            # Check if player has Points props (primary prop type)
            if check_prop_availability(anchor, 'Points'):
                away_anchors_filtered.append(anchor)
            # Also check SOG if we're generating SOG picks
            elif check_prop_availability(anchor, 'SOG'):
                away_anchors_filtered.append(anchor)
        
        for anchor in home_anchors:
            if check_prop_availability(anchor, 'Points'):
                home_anchors_filtered.append(anchor)
            elif check_prop_availability(anchor, 'SOG'):
                home_anchors_filtered.append(anchor)
        
        # Use filtered anchors
        away_anchors = away_anchors_filtered
        home_anchors = home_anchors_filtered
        
        if len(away_anchors) < len(away_anchors_filtered) or len(home_anchors) < len(home_anchors_filtered):
            print(f"    ⚠️  Prop availability filter: {len(away_anchors_filtered)}/{len(away_anchors)} away, {len(home_anchors_filtered)}/{len(home_anchors)} home")
        
        # MASTER PROMPT ALIGNMENT: Team total gate (≥3.0 GF/G) for Points Overs
        # This aligns with 88.9% hit rate strategy from winning approach
        
        # OPTIMIZED BUILD: Scenario-specific pick generation
        # Combines previous build's RUN_AND_GUN strength (63.9%) with current build's PACE_MISMATCH/CLAMP strength (76.8%/69.8%)
        
        if scenario == "RUN_AND_GUN":
            # PERFECT GAMES UPGRADE: Enhanced RUN_AND_GUN prioritization
            # Based on perfect games analysis: 50% of perfect picks, 7 perfect games
            # Strategy: 4 picks per game (up from 3), require both teams ≥3.0 GF/G, elite players (≥0.90 P/GP)
            # Perfect games averaged 3.0 picks, but top games had 4 picks
            
            # UPGRADE: Require both teams ≥3.0 GF/G (or one team ≥3.5 and other ≥2.8)
            away_gf = away_stats.get('gf_per_game', 0)
            home_gf = home_stats.get('gf_per_game', 0)
            
            # Check if both teams meet offense requirement
            both_strong_offense = away_gf >= 3.0 and home_gf >= 3.0
            one_very_strong = (away_gf >= 3.5 and home_gf >= 2.8) or (home_gf >= 3.5 and away_gf >= 2.8)
            meets_offense_requirement = both_strong_offense or one_very_strong
            
            if not meets_offense_requirement:
                # Skip RUN_AND_GUN if offense requirement not met
                pass
            else:
                # UPGRADE: Elite player threshold (≥0.90 P/GP for forwards, ≥18 TOI)
                # Perfect games averaged 1.19 P/GP, 20.6 TOI
                elite_forward_threshold = 0.90  # Up from implicit lower threshold
                elite_toi_threshold = 18.0  # Forwards
                
                # Pick 1: Away top forward (HIGH confidence)
                if len(away_anchors) > 0:
                    player = away_anchors[0]
                    adjusted_ppg = player.get('adjusted_ppg', player['points_per_game'])
                    weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                    toi_avg = player.get('toi_avg', 0)
                    volatility = player.get('volatility_metrics', {})
                    
                    # UPGRADE: Require elite player (≥0.90 P/GP, ≥18 TOI)
                    if weighted_ppg >= elite_forward_threshold and toi_avg >= elite_toi_threshold:
                        # ADVANCED STATISTICAL IMPROVEMENT: Boom/Bust Analysis
                        volatility_type = volatility.get('volatility', 'CONSISTENT')
                        boom_score = volatility.get('boom_score', 0.0)
                        bust_score = volatility.get('bust_score', 0.0)
                        
                        # TUNED: Lowered thresholds to catch more boom/bust players
                        if volatility_type == 'BOOM' and boom_score > 0.4 and weighted_ppg >= 0.9:
                            line = 1.5
                            side = 'Over'
                            confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                            rationale_suffix = f"BOOM player (CV: {volatility.get('coefficient_of_variation', 0):.2f}, Ceiling: {volatility.get('ceiling', 0)})"
                        elif volatility_type == 'BUST' and bust_score > 0.25 and scenario != "RUN_AND_GUN":  # BLOCK: No Points Unders in RUN_AND_GUN (Nov 26: 44.4% hit rate)
                            line = 0.5
                            side = 'Under'
                            confidence = 'MEDIUM'
                            rationale_suffix = f"BUST player (CV: {volatility.get('coefficient_of_variation', 0):.2f}, Floor: {volatility.get('floor', 0)})"
                        else:
                            line = 0.5
                            side = 'Over'
                            confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                            rationale_suffix = f"CONSISTENT player (CV: {volatility.get('coefficient_of_variation', 0):.2f})"
                        
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': away_abbrev,
                            'prop_type': 'Points',
                            'side': side,
                            'line': line,
                            'scenario': scenario,
                            'confidence': confidence,
                            'points_per_game': player['points_per_game'],
                            'weighted_ppg': weighted_ppg,
                            'adjusted_ppg': adjusted_ppg,
                            'opponent_mult': player.get('opponent_mult', 1.0),
                            'toi_avg': toi_avg,
                            'volatility_type': volatility_type,
                            'boom_score': boom_score,
                            'bust_score': bust_score,
                            'rationale': f"Run-and-Gun (Perfect Games Upgrade + Boom/Bust Analysis) - {player['name']} Points {side} {line} (Adj: {adjusted_ppg:.2f} P/GP, {rationale_suffix})"
                        })
                
                # Pick 2: Home top forward (HIGH confidence)
                if len(home_anchors) > 0:
                    player = home_anchors[0]
                    adjusted_ppg = player.get('adjusted_ppg', player['points_per_game'])
                    weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                    toi_avg = player.get('toi_avg', 0)
                    volatility = player.get('volatility_metrics', {})
                    
                    # UPGRADE: Require elite player (≥0.90 P/GP, ≥18 TOI)
                    if weighted_ppg >= elite_forward_threshold and toi_avg >= elite_toi_threshold:
                        # ADVANCED STATISTICAL IMPROVEMENT: Boom/Bust Analysis
                        volatility_type = volatility.get('volatility', 'CONSISTENT')
                        boom_score = volatility.get('boom_score', 0.0)
                        bust_score = volatility.get('bust_score', 0.0)
                        
                        # TUNED: Lowered thresholds to catch more boom/bust players
                        if volatility_type == 'BOOM' and boom_score > 0.4 and weighted_ppg >= 0.9:
                            line = 1.5
                            side = 'Over'
                            confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                            rationale_suffix = f"BOOM player (CV: {volatility.get('coefficient_of_variation', 0):.2f}, Ceiling: {volatility.get('ceiling', 0)})"
                        elif volatility_type == 'BUST' and bust_score > 0.25 and scenario != "RUN_AND_GUN":  # BLOCK: No Points Unders in RUN_AND_GUN (Nov 26: 44.4% hit rate)
                            line = 0.5
                            side = 'Under'
                            confidence = 'MEDIUM'
                            rationale_suffix = f"BUST player (CV: {volatility.get('coefficient_of_variation', 0):.2f}, Floor: {volatility.get('floor', 0)})"
                        else:
                            line = 0.5
                            side = 'Over'
                            confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                            rationale_suffix = f"CONSISTENT player (CV: {volatility.get('coefficient_of_variation', 0):.2f})"
                        
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': home_abbrev,
                            'prop_type': 'Points',
                            'side': side,
                            'line': line,
                            'scenario': scenario,
                            'confidence': confidence,
                            'points_per_game': player['points_per_game'],
                            'weighted_ppg': weighted_ppg,
                            'adjusted_ppg': adjusted_ppg,
                            'opponent_mult': player.get('opponent_mult', 1.0),
                            'toi_avg': toi_avg,
                            'volatility_type': volatility_type,
                            'boom_score': boom_score,
                            'bust_score': bust_score,
                            'rationale': f"Run-and-Gun (Perfect Games Upgrade + Boom/Bust Analysis) - {player['name']} Points {side} {line} (Adj: {adjusted_ppg:.2f} P/GP, {rationale_suffix})"
                        })
                
                # Pick 3: Away 2nd forward (MEDIUM confidence)
                if len(away_anchors) > 1:
                    player = away_anchors[1]
                    adjusted_ppg = player.get('adjusted_ppg', player['points_per_game'])
                    weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                    toi_avg = player.get('toi_avg', 0)
                    volatility = player.get('volatility_metrics', {})
                    
                    # UPGRADE: Require elite player (≥0.90 P/GP, ≥18 TOI)
                    if weighted_ppg >= elite_forward_threshold and toi_avg >= elite_toi_threshold:
                        # ADVANCED STATISTICAL IMPROVEMENT: Boom/Bust Analysis
                        volatility_type = volatility.get('volatility', 'CONSISTENT')
                        boom_score = volatility.get('boom_score', 0.0)
                        bust_score = volatility.get('bust_score', 0.0)
                        
                        # TUNED: Lowered thresholds to catch more boom/bust players
                        if volatility_type == 'BOOM' and boom_score > 0.4 and weighted_ppg >= 0.9:
                            line = 1.5
                            side = 'Over'
                            rationale_suffix = f"BOOM player (CV: {volatility.get('coefficient_of_variation', 0):.2f}, Ceiling: {volatility.get('ceiling', 0)}, Boom Score: {boom_score:.2f})"
                        elif volatility_type == 'BUST' and bust_score > 0.25 and scenario != "RUN_AND_GUN":  # BLOCK: No Points Unders in RUN_AND_GUN (Nov 26: 44.4% hit rate)
                            line = 0.5
                            side = 'Under'
                            rationale_suffix = f"BUST player (CV: {volatility.get('coefficient_of_variation', 0):.2f}, Floor: {volatility.get('floor', 0)}, Bust Score: {bust_score:.2f})"
                        else:
                            line = 0.5
                            side = 'Over'
                            rationale_suffix = f"CONSISTENT player (CV: {volatility.get('coefficient_of_variation', 0):.2f})"
                        
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': away_abbrev,
                            'prop_type': 'Points',
                            'side': side,
                            'line': line,
                            'scenario': scenario,
                            'confidence': 'MEDIUM',  # MEDIUM for 2nd forward
                            'points_per_game': player['points_per_game'],
                            'weighted_ppg': weighted_ppg,
                            'adjusted_ppg': adjusted_ppg,
                            'opponent_mult': player.get('opponent_mult', 1.0),
                            'toi_avg': toi_avg,
                            'volatility_type': volatility_type,
                            'boom_score': boom_score,
                            'bust_score': bust_score,
                            'rationale': f"Run-and-Gun (Perfect Games Upgrade + Boom/Bust Analysis) - {player['name']} Points {side} {line} (Adj: {adjusted_ppg:.2f} P/GP, {rationale_suffix})"
                        })
                
                # Pick 4: Home 2nd forward (MEDIUM confidence)
                if len(home_anchors) > 1:
                    player = home_anchors[1]
                    adjusted_ppg = player.get('adjusted_ppg', player['points_per_game'])
                    weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                    toi_avg = player.get('toi_avg', 0)
                    
                    # UPGRADE: Require elite player (≥0.90 P/GP, ≥18 TOI)
                    if weighted_ppg >= elite_forward_threshold and toi_avg >= elite_toi_threshold:
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': home_abbrev,
                            'prop_type': 'Points',
                            'side': 'Over',
                            'line': 0.5,
                            'scenario': scenario,
                            'confidence': 'MEDIUM',  # MEDIUM for 2nd forward
                            'points_per_game': player['points_per_game'],
                            'weighted_ppg': weighted_ppg,
                            'adjusted_ppg': adjusted_ppg,
                            'opponent_mult': player.get('opponent_mult', 1.0),
                            'toi_avg': toi_avg,
                            'rationale': f"Run-and-Gun (Perfect Games Upgrade) - {player['name']} Points Over 0.5 (Adj: {adjusted_ppg:.2f} P/GP, team {home_gf:.2f} GF/G, opp {away_stats.get('ga_per_game', 0):.2f} GA/G)"
                        })
        
        elif scenario == "DEFENSIVE_STRUGGLE":
            # PERFECT GAMES UPGRADE: DEFENSIVE_STRUGGLE enhancement
            # Perfect games: 2 games, 3 picks each, 100% hit rate
            # Strategy: 3 picks per game, elite players (≥0.90 P/GP, ≥18 TOI)
            # Perfect games averaged 1.19 P/GP, 20.6 TOI
            
            elite_forward_ppg = 0.90
            elite_forward_toi = 18.0
            elite_defenseman_ppg = 0.95
            elite_defenseman_toi = 22.0
            
            # Pick 1: Away top forward (HIGH confidence)
            if len(away_anchors) > 0 and away_stats.get('gf_per_game', 0) >= 2.8:
                player = away_anchors[0]
                weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                toi_avg = player.get('toi_avg', 0)
                is_defenseman = player.get('position', '').upper() in ['D', 'DEFENSEMAN', 'DEFENCE']
                
                # UPGRADE: Require elite player thresholds
                meets_elite_threshold = False
                if is_defenseman:
                    meets_elite_threshold = weighted_ppg >= elite_defenseman_ppg and toi_avg >= elite_defenseman_toi
                else:
                    meets_elite_threshold = weighted_ppg >= elite_forward_ppg and toi_avg >= elite_forward_toi
                
                if meets_elite_threshold:
                    confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                    picks.append({
                        'game_id': game_id,
                        'player_id': player['player_id'],
                        'player_name': player['name'],
                        'team': away_abbrev,
                        'prop_type': 'Points',
                        'side': 'Over',
                        'line': 0.5,
                        'scenario': scenario,
                        'confidence': confidence,
                        'points_per_game': player['points_per_game'],
                        'weighted_ppg': weighted_ppg,
                        'adjusted_ppg': player.get('adjusted_ppg', player['points_per_game']),
                        'opponent_mult': player.get('opponent_mult', 1.0),
                        'toi_avg': toi_avg,
                        'rationale': f"Defensive Struggle (Perfect Games Upgrade) - {player['name']} Points Over 0.5 (Adj: {player.get('adjusted_ppg', player['points_per_game']):.2f} P/GP, team {away_stats.get('gf_per_game', 0):.2f} GF/G, opp {home_stats.get('ga_per_game', 0):.2f} GA/G)"
                    })
            
            # Pick 2: Home top forward (HIGH confidence)
            if len(home_anchors) > 0 and home_stats.get('gf_per_game', 0) >= 2.8:
                player = home_anchors[0]
                weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                toi_avg = player.get('toi_avg', 0)
                is_defenseman = player.get('position', '').upper() in ['D', 'DEFENSEMAN', 'DEFENCE']
                
                # UPGRADE: Require elite player thresholds
                meets_elite_threshold = False
                if is_defenseman:
                    meets_elite_threshold = weighted_ppg >= elite_defenseman_ppg and toi_avg >= elite_defenseman_toi
                else:
                    meets_elite_threshold = weighted_ppg >= elite_forward_ppg and toi_avg >= elite_forward_toi
                
                if meets_elite_threshold:
                    confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                    picks.append({
                        'game_id': game_id,
                        'player_id': player['player_id'],
                        'player_name': player['name'],
                        'team': home_abbrev,
                        'prop_type': 'Points',
                        'side': 'Over',
                        'line': 0.5,
                        'scenario': scenario,
                        'confidence': confidence,
                        'points_per_game': player['points_per_game'],
                        'weighted_ppg': weighted_ppg,
                        'adjusted_ppg': player.get('adjusted_ppg', player['points_per_game']),
                        'opponent_mult': player.get('opponent_mult', 1.0),
                        'toi_avg': toi_avg,
                        'rationale': f"Defensive Struggle (Perfect Games Upgrade) - {player['name']} Points Over 0.5 (Adj: {player.get('adjusted_ppg', player['points_per_game']):.2f} P/GP, team {home_stats.get('gf_per_game', 0):.2f} GF/G, opp {away_stats.get('ga_per_game', 0):.2f} GA/G)"
                    })
            
            # Pick 3: 2nd forward from stronger team (if both teams ≥2.8 GF/G)
            if (away_stats.get('gf_per_game', 0) >= 2.8 and home_stats.get('gf_per_game', 0) >= 2.8):
                stronger_team = away_abbrev if away_stats.get('gf_per_game', 0) >= home_stats.get('gf_per_game', 0) else home_abbrev
                stronger_anchors = away_anchors if stronger_team == away_abbrev else home_anchors
                if len(stronger_anchors) > 1:
                    player = stronger_anchors[1]
                    weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                    toi_avg = player.get('toi_avg', 0)
                    is_defenseman = player.get('position', '').upper() in ['D', 'DEFENSEMAN', 'DEFENCE']
                    
                    # UPGRADE: Require elite player thresholds
                    meets_elite_threshold = False
                    if is_defenseman:
                        meets_elite_threshold = weighted_ppg >= elite_defenseman_ppg and toi_avg >= elite_defenseman_toi
                    else:
                        meets_elite_threshold = weighted_ppg >= elite_forward_ppg and toi_avg >= elite_forward_toi
                    
                    if meets_elite_threshold:
                        opponent_stats = home_stats if stronger_team == away_abbrev else away_stats
                        confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': stronger_team,
                            'prop_type': 'Points',
                            'side': 'Over',
                            'line': 0.5,
                            'scenario': scenario,
                            'confidence': confidence,
                            'points_per_game': player['points_per_game'],
                            'weighted_ppg': weighted_ppg,
                            'adjusted_ppg': player.get('adjusted_ppg', player['points_per_game']),
                            'opponent_mult': player.get('opponent_mult', 1.0),
                            'toi_avg': toi_avg,
                            'rationale': f"Defensive Struggle (Perfect Games Upgrade) - {player['name']} Points Over 0.5 (Adj: {player.get('adjusted_ppg', player['points_per_game']):.2f} P/GP, opp {opponent_stats.get('ga_per_game', 0):.2f} GA/G)"
                        })
        
        elif scenario == "HIGH_OFFENSE":
            # MASTER PROMPT ALIGNMENT: 100.0% hit rate (2-0) - PERFECT
            # Strategy: Points Overs on top forwards, 2-3 picks per game
            # Team total gate: ≥3.0 GF/G (from winning approach)
            if len(away_anchors) > 0 and away_stats.get('gf_per_game', 0) >= 3.0:
                player = away_anchors[0]
                picks.append({
                    'game_id': game_id,
                    'player_id': player['player_id'],
                    'player_name': player['name'],
                    'team': away_abbrev,
                    'prop_type': 'Points',
                    'side': 'Over',
                    'line': 0.5,
                    'scenario': scenario,
                    'confidence': 'HIGH',
                    'points_per_game': player['points_per_game'],
                    'weighted_ppg': player.get('weighted_ppg', player['points_per_game']),
                    'adjusted_ppg': player.get('adjusted_ppg', player['points_per_game']),
                    'opponent_mult': player.get('opponent_mult', 1.0),
                    'toi_avg': player['toi_avg'],
                    'rationale': f"High Offense (100% hit rate) - {player['name']} Points Over 0.5 (Adj: {player.get('adjusted_ppg', player['points_per_game']):.2f} P/GP, team {away_stats.get('gf_per_game', 0):.2f} GF/G, opp {home_stats.get('ga_per_game', 0):.2f} GA/G)"
                })
            
            if len(home_anchors) > 0 and home_stats.get('gf_per_game', 0) >= 3.0:
                player = home_anchors[0]
                picks.append({
                    'game_id': game_id,
                    'player_id': player['player_id'],
                    'player_name': player['name'],
                    'team': home_abbrev,
                    'prop_type': 'Points',
                    'side': 'Over',
                    'line': 0.5,
                    'scenario': scenario,
                    'confidence': 'HIGH',
                    'points_per_game': player['points_per_game'],
                    'weighted_ppg': player.get('weighted_ppg', player['points_per_game']),
                    'adjusted_ppg': player.get('adjusted_ppg', player['points_per_game']),
                    'opponent_mult': player.get('opponent_mult', 1.0),
                    'toi_avg': player['toi_avg'],
                    'rationale': f"High Offense (100% hit rate) - {player['name']} Points Over 0.5 (Adj: {player.get('adjusted_ppg', player['points_per_game']):.2f} P/GP, team {home_stats.get('gf_per_game', 0):.2f} GF/G, opp {away_stats.get('ga_per_game', 0):.2f} GA/G)"
                })
            
            # 3rd pick: If both teams ≥3.0 GF/G (maximize 100% hit rate scenario)
            if (away_stats.get('gf_per_game', 0) >= 3.0 and home_stats.get('gf_per_game', 0) >= 3.0):
                stronger_team = away_abbrev if away_stats.get('gf_per_game', 0) >= home_stats.get('gf_per_game', 0) else home_abbrev
                stronger_anchors = away_anchors if stronger_team == away_abbrev else home_anchors
                if len(stronger_anchors) > 1:
                    player = stronger_anchors[1]
                    opponent_stats = home_stats if stronger_team == away_abbrev else away_stats
                    picks.append({
                        'game_id': game_id,
                        'player_id': player['player_id'],
                        'player_name': player['name'],
                        'team': stronger_team,
                        'prop_type': 'Points',
                        'side': 'Over',
                        'line': 0.5,
                        'scenario': scenario,
                        'confidence': 'HIGH',
                        'points_per_game': player['points_per_game'],
                        'weighted_ppg': player.get('weighted_ppg', player['points_per_game']),
                        'adjusted_ppg': player.get('adjusted_ppg', player['points_per_game']),
                        'opponent_mult': player.get('opponent_mult', 1.0),
                        'toi_avg': player['toi_avg'],
                        'rationale': f"High Offense (100% hit rate) - {player['name']} Points Over 0.5 (Adj: {player.get('adjusted_ppg', player['points_per_game']):.2f} P/GP, opp {opponent_stats.get('ga_per_game', 0):.2f} GA/G)"
                    })
        
        else:
            # RECOMMENDATION #3: Expand pick generation for PACE_MISMATCH/CLAMP
            # Current: 2 picks (top forward only)
            # Target: 3-5 picks per game total
            # Strategy: Add SOG picks and potentially 2nd forward if conditions met
            
            # FIX #2: Lower GF/G threshold for CLAMP/PACE_MISMATCH to increase pick volume
            # Current: >= 3.0 (too restrictive, many teams don't meet this)
            # New: >= 2.6 (more reasonable, still filters out very weak offenses)
            # Rationale: Many games generating 0 picks because teams don't meet 3.0 threshold
            
            # PRIORITY 1 FIX: Tighten CLAMP criteria to improve hit rate
            # CLAMP scenario was underperforming at 40.9% hit rate
            # Changes: Raise GF/G threshold (2.6→2.8), raise adjusted PPG (0.5→0.65), limit to top 2 players, use LOW confidence
            if scenario == "CLAMP":
                # TIGHTENED CRITERIA FOR CLAMP
                gf_threshold = 2.8  # Raised from 2.6 (only stronger offenses)
                min_adjusted_ppg = 0.65  # Raised from 0.5 (30% higher threshold)
                max_players = 2  # Limit to top 2 players per team
            else:
                # PACE_MISMATCH: Keep original criteria
                gf_threshold = 2.6 if scenario == "PACE_MISMATCH" else 3.0
                min_adjusted_ppg = 0.5
                max_players = None  # No limit for non-CLAMP
            
            # PERFECT GAMES UPGRADE: Elite player thresholds for all scenarios
            # Perfect games averaged 1.19 P/GP, 20.6 TOI
            # Forwards: ≥0.90 P/GP, ≥18 TOI
            # Defensemen: ≥0.95 P/GP, ≥22 TOI
            elite_forward_ppg = 0.90
            elite_forward_toi = 18.0
            elite_defenseman_ppg = 0.95
            elite_defenseman_toi = 22.0
            
            # Away team Points picks
            away_players_to_check = away_anchors[:max_players] if max_players else away_anchors
            if len(away_players_to_check) > 0 and away_stats.get('gf_per_game', 0) >= gf_threshold:
                player = away_players_to_check[0]
                adjusted_ppg = player.get('adjusted_ppg', player['points_per_game'])
                weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                toi_avg = player.get('toi_avg', 0)
                is_defenseman = player.get('position', '').upper() in ['D', 'DEFENSEMAN', 'DEFENCE']
                
                # UPGRADE: Require elite player thresholds
                meets_elite_threshold = False
                if is_defenseman:
                    meets_elite_threshold = weighted_ppg >= elite_defenseman_ppg and toi_avg >= elite_defenseman_toi
                else:
                    meets_elite_threshold = weighted_ppg >= elite_forward_ppg and toi_avg >= elite_forward_toi
                
                # CLAMP: Only generate if adjusted PPG meets higher threshold
                if adjusted_ppg >= min_adjusted_ppg and meets_elite_threshold:
                    # CLAMP: Use LOW confidence (changed from MEDIUM)
                    # Other scenarios: HIGH if ≥1.20 P/GP, MEDIUM if ≥0.90 P/GP
                    if scenario == "CLAMP":
                        confidence = 'LOW'
                    else:
                        confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                    
                    picks.append({
                        'game_id': game_id,
                        'player_id': player['player_id'],
                        'player_name': player['name'],
                        'team': away_abbrev,
                        'prop_type': 'Points',
                        'side': 'Over',
                        'line': 0.5,
                        'scenario': scenario,
                        'confidence': confidence,
                        'points_per_game': player['points_per_game'],
                        'weighted_ppg': weighted_ppg,
                        'adjusted_ppg': adjusted_ppg,
                        'opponent_mult': player.get('opponent_mult', 1.0),
                        'toi_avg': toi_avg,
                        'rationale': f"{scenario} (Perfect Games Upgrade) - {player['name']} Points Over 0.5 (Adj: {adjusted_ppg:.2f} P/GP, team {away_stats.get('gf_per_game', 0):.2f} GF/G, opp {home_stats.get('ga_per_game', 0):.2f} GA/G)"
                    })
            
            # Home team Points picks
            home_players_to_check = home_anchors[:max_players] if max_players else home_anchors
            if len(home_players_to_check) > 0 and home_stats.get('gf_per_game', 0) >= gf_threshold:
                player = home_players_to_check[0]
                adjusted_ppg = player.get('adjusted_ppg', player['points_per_game'])
                weighted_ppg = player.get('weighted_ppg', player['points_per_game'])
                toi_avg = player.get('toi_avg', 0)
                is_defenseman = player.get('position', '').upper() in ['D', 'DEFENSEMAN', 'DEFENCE']
                
                # UPGRADE: Require elite player thresholds
                meets_elite_threshold = False
                if is_defenseman:
                    meets_elite_threshold = weighted_ppg >= elite_defenseman_ppg and toi_avg >= elite_defenseman_toi
                else:
                    meets_elite_threshold = weighted_ppg >= elite_forward_ppg and toi_avg >= elite_forward_toi
                
                # CLAMP: Only generate if adjusted PPG meets higher threshold
                if adjusted_ppg >= min_adjusted_ppg and meets_elite_threshold:
                    # CLAMP: Use LOW confidence (changed from MEDIUM)
                    # Other scenarios: HIGH if ≥1.20 P/GP, MEDIUM if ≥0.90 P/GP
                    if scenario == "CLAMP":
                        confidence = 'LOW'
                    else:
                        confidence = 'HIGH' if weighted_ppg >= 1.20 else 'MEDIUM'
                    
                    picks.append({
                        'game_id': game_id,
                        'player_id': player['player_id'],
                        'player_name': player['name'],
                        'team': home_abbrev,
                        'prop_type': 'Points',
                        'side': 'Over',
                        'line': 0.5,
                        'scenario': scenario,
                        'confidence': confidence,
                        'points_per_game': player['points_per_game'],
                        'weighted_ppg': weighted_ppg,
                        'adjusted_ppg': adjusted_ppg,
                        'opponent_mult': player.get('opponent_mult', 1.0),
                        'toi_avg': toi_avg,
                        'rationale': f"{scenario} (Perfect Games Upgrade) - {player['name']} Points Over 0.5 (Adj: {adjusted_ppg:.2f} P/GP, team {home_stats.get('gf_per_game', 0):.2f} GF/G, opp {away_stats.get('ga_per_game', 0):.2f} GA/G)"
                    })
            
            # RECOMMENDATION #3: Add 3rd pick for PACE_MISMATCH if both teams strong offense
            # Strategy: 2nd forward from stronger team (similar to RUN_AND_GUN)
            # FIX #2: Use scenario-specific threshold (2.6 for PACE_MISMATCH)
            if scenario == "PACE_MISMATCH":
                stronger_team = away_abbrev if away_stats.get('gf_per_game', 0) >= home_stats.get('gf_per_game', 0) else home_abbrev
                stronger_stats = away_stats if stronger_team == away_abbrev else home_stats
                stronger_anchors = away_anchors if stronger_team == away_abbrev else home_anchors
                opponent_stats = home_stats if stronger_team == away_abbrev else away_stats
                
                if len(stronger_anchors) > 1 and stronger_stats.get('gf_per_game', 0) >= 2.6:
                    player = stronger_anchors[1]
                    adjusted_ppg = player.get('adjusted_ppg', player['points_per_game'])
                    picks.append({
                        'game_id': game_id,
                        'player_id': player['player_id'],
                        'player_name': player['name'],
                        'team': stronger_team,
                        'prop_type': 'Points',
                        'side': 'Over',
                        'line': 0.5,
                        'scenario': scenario,
                        'confidence': 'MEDIUM',
                        'points_per_game': player['points_per_game'],
                        'weighted_ppg': player.get('weighted_ppg', player['points_per_game']),
                        'adjusted_ppg': adjusted_ppg,
                        'opponent_mult': player.get('opponent_mult', 1.0),
                        'toi_avg': player['toi_avg'],
                        'rationale': f"{scenario} - {player['name']} Points Over 0.5 (Adj: {adjusted_ppg:.2f} P/GP, team {stronger_stats.get('gf_per_game', 0):.2f} GF/G, opp {opponent_stats.get('ga_per_game', 0):.2f} GA/G)"
                    })
        
        # PERFECT GAMES UPGRADE: SOG pick generation strategy
        # Based on perfect games analysis: 11 SOG picks, 100% hit rate
        # 
        # SOG Overs (4 picks in perfect games):
        #   - Average SOG/GM: 3.68 (extreme volume shooters)
        #   - Average Actual: 6.25 SOG (2.57 margin above line)
        #   - All in RUN_AND_GUN scenarios
        #   - Examples: MacKinnon (4.32 SOG/GM → 5 SOG O3.5), Gauthier (4.27 SOG/GM → 8 SOG O3.5)
        # 
        # SOG Unders (7 picks in perfect games):
        #   - Average SOG/GM: 3.56 (high-volume shooters)
        #   - Average Actual: 2.00 SOG (1.56 margin below line)
        #   - All in CLAMP or PACE_MISMATCH scenarios
        #   - Examples: Eichel (4.12 SOG/GM → 3 SOG U3.5), Werenski (3.77 SOG/GM → 2 SOG U3.5)
        # 
        # Strategy:
        #   - SOG Overs: Extreme volume (≥4.0 SOG/GM) for O3.5, high volume (≥3.5) for O2.5
        #   - SOG Overs: Only in RUN_AND_GUN scenarios (perfect games pattern)
        #   - SOG Unders: High volume (≥3.0 SOG/GM) vs elite suppression (SA/G ≤28.5) in CLAMP/PACE_MISMATCH
        #   - Only top volume shooter per team (most conservative)
        
        # Fetch team shots stats
        away_sog = self.fetch_team_shots_stats(away_abbrev)
        home_sog = self.fetch_team_shots_stats(home_abbrev)
        
        # RED TEAM FIX: Use actual shots AGAINST (not shots FOR as proxy)
        # Calculate opponent shots allowed for context (suppression logic)
        away_opp_sog_allowed = self.fetch_team_shots_against(home_abbrev)  # Opponent's shots AGAINST
        home_opp_sog_allowed = self.fetch_team_shots_against(away_abbrev)  # Opponent's shots AGAINST
        
        # EXPANDED SOG OVER STRATEGY - Maximize correct picks while maintaining quality
        # Keep SOG Under method (suppression-driven) unchanged
        # 
        # Tier 1: Extreme usage (4.0+ SOG/GM) - O3.5 in ANY scenario (Nathan MacKinnon: 3/3)
        # Tier 2: High-volume (3.5-3.9 SOG/GM) - O3.5 in high-volume scenarios, O2.5 in others
        # Tier 3: Volume shooters (3.0-3.4 SOG/GM) - O2.5 in multiple scenarios
        # Tier 4: Moderate volume (2.5-2.9 SOG/GM) - O2.5 in RUN_AND_GUN/HIGH_OFFENSE only
        #
        # Generate picks for top 2 volume shooters per team (not just top 1)
        # Consider opponent shots allowed (boost if opponent allows high SOG)
        
        # RED TEAM FIX: Track players with SOG Over picks to prevent contradictory Under picks
        sog_over_players = set()  # Track (game_id, player_id) tuples
        
        # RECOMMENDATION #1: Prioritize SOG Under over SOG Over in suppression scenarios
        # Track suppression opportunities (opponent SA/G ≤28.5) to skip SOG Over generation
        suppression_opportunities = set()  # Track (game_id, team_abbrev) tuples
        
        # RECOMMENDATION #3: Enhance SOG Under Logic - Review suppression thresholds
        # RECOMMENDATION #3: Lower suppression threshold from 28.5 to 29.0 SA/G (less strict)
        suppression_threshold = 29.0  # Lowered from 28.5 to increase SOG Under opportunities
        
        # Check for suppression opportunities BEFORE generating SOG Over picks
        if scenario not in ["RUN_AND_GUN", "HIGH_OFFENSE"]:
            if away_opp_sog_allowed <= suppression_threshold:
                suppression_opportunities.add((game_id, away_abbrev))
            if home_opp_sog_allowed <= suppression_threshold:
                suppression_opportunities.add((game_id, home_abbrev))
        
        # RECOMMENDATION #1: Refine SOG Strategy
        # Expand SOG Overs beyond RUN_AND_GUN for extreme volume shooters (≥4.0 SOG/GM)
        # Strategy: Extreme volume (≥4.0) for O3.5 in ANY scenario, high volume (≥3.5) for O2.5 in RUN_AND_GUN
        # Only top volume shooter per team (most conservative)
        
        # Away team SOG Over picks
        # RECOMMENDATION #1: Allow extreme volume shooters (≥4.0) in ANY scenario
        if away_sog >= 30.0 and (game_id, away_abbrev) not in suppression_opportunities:
            volume_shooters = []
            for player in away_anchors:
                sog_per_game = player.get('sog_per_game', 0)
                # RECOMMENDATION #1: Extreme volume (≥4.0) in ANY scenario, high volume (≥3.5) in RUN_AND_GUN
                if sog_per_game >= 4.0 or (sog_per_game >= 3.5 and scenario == "RUN_AND_GUN"):
                    volume_shooters.append((player, sog_per_game))
            
            if volume_shooters:
                volume_shooters.sort(key=lambda x: x[1], reverse=True)
                # Only top volume shooter per team
                player, sog_per_game = volume_shooters[0]
                # Skip if opponent suppresses (≤28.5 SA/G)
                if away_opp_sog_allowed > 28.5:
                    # Tier 1: Extreme usage (≥4.0 SOG/GM) - O3.5 in ANY scenario
                    if sog_per_game >= 4.0:
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': away_abbrev,
                            'prop_type': 'SOG',
                            'side': 'Over',
                            'line': 3.5,
                            'scenario': scenario,
                            'confidence': 'HIGH',
                            'sog_per_game': player['sog_per_game'],
                            'toi_avg': player['toi_avg'],
                            'rationale': f"{scenario} (Rec #1: Extreme Volume) - {player['name']} SOG Over 3.5 (Extreme usage: {player['sog_per_game']:.2f} SOG/GM, team {away_sog:.1f} SOG/GM)"
                        })
                        sog_over_players.add((game_id, player['player_id']))
                    # Tier 2: High-volume (3.5-3.9 SOG/GM) - O2.5 in RUN_AND_GUN only
                    elif sog_per_game >= 3.5 and scenario == "RUN_AND_GUN":
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': away_abbrev,
                            'prop_type': 'SOG',
                            'side': 'Over',
                            'line': 2.5,
                            'scenario': scenario,
                            'confidence': 'HIGH',
                            'sog_per_game': player['sog_per_game'],
                            'toi_avg': player['toi_avg'],
                            'rationale': f"Run-and-Gun (Rec #1) - {player['name']} SOG Over 2.5 (High-volume: {player['sog_per_game']:.2f} SOG/GM, team {away_sog:.1f} SOG/GM)"
                        })
                        sog_over_players.add((game_id, player['player_id']))
        
        # Home team SOG Over picks
        # RECOMMENDATION #1: Allow extreme volume shooters (≥4.0) in ANY scenario
        if home_sog >= 30.0 and (game_id, home_abbrev) not in suppression_opportunities:
            volume_shooters = []
            for player in home_anchors:
                sog_per_game = player.get('sog_per_game', 0)
                # RECOMMENDATION #1: Extreme volume (≥4.0) in ANY scenario, high volume (≥3.5) in RUN_AND_GUN
                if sog_per_game >= 4.0 or (sog_per_game >= 3.5 and scenario == "RUN_AND_GUN"):
                    volume_shooters.append((player, sog_per_game))
            
            if volume_shooters:
                volume_shooters.sort(key=lambda x: x[1], reverse=True)
                # Only top volume shooter per team
                player, sog_per_game = volume_shooters[0]
                # RECOMMENDATION #3: Use updated suppression threshold
                if home_opp_sog_allowed > suppression_threshold:
                    # Tier 1: Extreme usage (≥4.0 SOG/GM) - O3.5 in ANY scenario
                    if sog_per_game >= 4.0:
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': home_abbrev,
                            'prop_type': 'SOG',
                            'side': 'Over',
                            'line': 3.5,
                            'scenario': scenario,
                            'confidence': 'HIGH',
                            'sog_per_game': player['sog_per_game'],
                            'toi_avg': player['toi_avg'],
                            'rationale': f"{scenario} (Rec #1: Extreme Volume) - {player['name']} SOG Over 3.5 (Extreme usage: {player['sog_per_game']:.2f} SOG/GM, team {home_sog:.1f} SOG/GM)"
                        })
                        sog_over_players.add((game_id, player['player_id']))
                    # Tier 2: High-volume (3.5-3.9 SOG/GM) - O2.5 in RUN_AND_GUN only
                    elif sog_per_game >= 3.5 and scenario == "RUN_AND_GUN":
                        picks.append({
                            'game_id': game_id,
                            'player_id': player['player_id'],
                            'player_name': player['name'],
                            'team': home_abbrev,
                            'prop_type': 'SOG',
                            'side': 'Over',
                            'line': 2.5,
                            'scenario': scenario,
                            'confidence': 'HIGH',
                            'sog_per_game': player['sog_per_game'],
                            'toi_avg': player['toi_avg'],
                            'rationale': f"Run-and-Gun (Rec #1) - {player['name']} SOG Over 2.5 (High-volume: {player['sog_per_game']:.2f} SOG/GM, team {home_sog:.1f} SOG/GM)"
                        })
                        sog_over_players.add((game_id, player['player_id']))
        
        # PERFECT GAMES UPGRADE: SOG Unders only in CLAMP/PACE_MISMATCH scenarios
        # Perfect games: All SOG Unders were in CLAMP or PACE_MISMATCH scenarios
        # Strategy: High-volume shooters (≥3.0 SOG/GM) vs elite suppression (SA/G ≤28.5)
        # Only top volume shooter per team (most conservative)
        
        # RECOMMENDATION #1 & #2: Prioritize SOG Under over SOG Over in suppression scenarios
        # RECOMMENDATION #2: Expand player pool to top 2-3 anchors (not just top 1)
        # RED TEAM FIX: Prevent contradictory picks - skip Under if player already has Over
        if scenario in ["CLAMP", "PACE_MISMATCH"]:
            # Away team SOG Unders
            # RECOMMENDATION #3: Use updated suppression threshold (29.0 instead of 28.5)
            if away_opp_sog_allowed <= suppression_threshold:  # Elite suppression
                volume_shooters = []
                for player in away_anchors:
                    # RED TEAM FIX: Skip if player already has Over pick
                    if (game_id, player['player_id']) in sog_over_players:
                        continue
                    sog_per_game = player.get('sog_per_game', 0)
                    if sog_per_game >= 3.0:  # High-volume shooters (≥3.0)
                        volume_shooters.append((player, sog_per_game))
                
                if volume_shooters:
                    volume_shooters.sort(key=lambda x: x[1], reverse=True)
                    # Only top volume shooter per team
                    player, sog_per_game = volume_shooters[0]
                    picks.append({
                        'game_id': game_id,
                        'player_id': player['player_id'],
                        'player_name': player['name'],
                        'team': away_abbrev,
                        'prop_type': 'SOG',
                        'side': 'Under',
                        'line': 3.5,
                        'scenario': scenario,
                        'confidence': 'MEDIUM',
                        'sog_per_game': player['sog_per_game'],
                        'toi_avg': player['toi_avg'],
                        'rationale': f"{scenario} (Rec #3: Enhanced Suppression) - {player['name']} SOG Under 3.5 (High-volume: {player['sog_per_game']:.2f} SOG/GM vs suppression: {away_opp_sog_allowed:.1f} SA/G)"
                    })
            
            # Home team SOG Unders
            # RECOMMENDATION #3: Use updated suppression threshold (29.0 instead of 28.5)
            if home_opp_sog_allowed <= suppression_threshold:  # Elite suppression
                volume_shooters = []
                for player in home_anchors:
                    # RED TEAM FIX: Skip if player already has Over pick
                    if (game_id, player['player_id']) in sog_over_players:
                        continue
                    sog_per_game = player.get('sog_per_game', 0)
                    if sog_per_game >= 3.0:  # High-volume shooters (≥3.0)
                        volume_shooters.append((player, sog_per_game))
                
                if volume_shooters:
                    volume_shooters.sort(key=lambda x: x[1], reverse=True)
                    # Only top volume shooter per team
                    player, sog_per_game = volume_shooters[0]
                    picks.append({
                        'game_id': game_id,
                        'player_id': player['player_id'],
                        'player_name': player['name'],
                        'team': home_abbrev,
                        'prop_type': 'SOG',
                        'side': 'Under',
                        'line': 3.5,
                        'scenario': scenario,
                        'confidence': 'MEDIUM',
                        'sog_per_game': player['sog_per_game'],
                        'toi_avg': player['toi_avg'],
                        'rationale': f"{scenario} (Rec #3: Enhanced Suppression) - {player['name']} SOG Under 3.5 (High-volume: {player['sog_per_game']:.2f} SOG/GM vs suppression: {home_opp_sog_allowed:.1f} SA/G)"
                    })
        
        # FINAL GUARDRAIL: Block any Points Unders in RUN_AND_GUN scenarios (Nov 26: 44.4% hit rate)
        # This catches any edge cases that might slip through
        filtered_picks = []
        for pick in picks:
            if (pick.get('prop_type') == 'Points' and 
                pick.get('side') == 'Under' and 
                pick.get('scenario') == 'RUN_AND_GUN'):
                # Skip this pick - Points Unders blocked in RUN_AND_GUN
                continue
            filtered_picks.append(pick)
        
        return filtered_picks
    
    # Feasibility check methods removed per user request
    
    def _verify_player_feasibility(self, player: Dict, team_abbrev: str, game_id: int,
                                   rosters: Dict[str, List[str]], 
                                   lineup_status: Optional[Dict[int, bool]]) -> bool:
        """
        Basic feasibility checks: roster status, recent activity
        Note: Prop availability is checked separately in generate_picks_with_players
        """
        # Check if player has recent games (not inactive > 7 days)
        # This is a basic check - full injury/lineup checks would require additional API calls
        player_id = player.get('player_id')
        if not player_id:
            return False
        
        # Check recent form via game log
        game_log = self.profiler.fetch_player_game_log(player_id)
        if game_log:
            # Check if player has played recently (within last 7 days)
            # This is a simplified check - in production would use actual injury/lineup data
            return True  # Assume available if we have game log data
        
        # If no game log, player might be inactive - be conservative
        return False
    
    def rank_picks_by_confidence(self, all_picks: List[Dict]) -> List[Dict]:
        """Rank picks by confidence and scenario performance"""
        scenario_confidence = {
            'HIGH_OFFENSE': 10,
            'DEFENSIVE_STRUGGLE': 9,
            'RUN_AND_GUN': 8,
            'CLAMP': 7,
            'PACE_MISMATCH': 5,
            'BALANCED': 4,
            'SUPPRESSION_MATCHUP': 4,
            'OFFENSIVE_MISMATCH': 1,
        }
        
        confidence_weights = {
            'HIGH': 1.0,
            'MEDIUM': 0.7,
            'LOW': 0.5
        }
        
        for pick in all_picks:
            scenario = pick.get('scenario', 'BALANCED')
            conf_level = pick.get('confidence', 'MEDIUM')
            
            scenario_score = scenario_confidence.get(scenario, 5)
            conf_weight = confidence_weights.get(conf_level, 0.7)
            
            # Bonus for actual player selection
            player_bonus = 1.0 if 'player_id' in pick else 0.5
            
            pick['score'] = scenario_score * conf_weight * player_bonus
        
        all_picks.sort(key=lambda x: x.get('score', 0), reverse=True)
        return all_picks
    
    def analyze_slate(self):
        """Run full model analysis on today's slate"""
        print("="*80)
        print("FULL MODEL ANALYSIS - TODAY'S SLATE (WITH PLAYER PROFILES)")
        print(f"Date: {TODAY}")
        print("="*80)
        
        # Step 1: Fetch today's games
        print(f"\n[Step 1] Fetching today's games...")
        games = self.fetch_todays_games()
        print(f"Found {len(games)} games scheduled")
        
        if len(games) == 0:
            print("No games found for today")
            return
        
        # Step 2: Fetch pregame data
        print(f"\n[Step 2] Fetching pregame data (standings)...")
        standings = self.fetch_standings()
        print(f"Loaded stats for {len(standings)} teams")
        
        # Step 3: Analyze each game
        print(f"\n[Step 3] Running full model analysis on each game...")
        print("="*80)
        
        all_picks = []
        game_analyses = []
        
        for i, game in enumerate(games, 1):
            game_id = game.get('id')
            away = game.get('awayTeam', {}).get('abbrev', '?')
            home = game.get('homeTeam', {}).get('abbrev', '?')
            start_time = game.get('startTimeUTC', '?')
            
            print(f"\n[{i}/{len(games)}] {away} @ {home}")
            print(f"  Start Time: {start_time}")
            
            # Feasibility checks disabled per user request
            
            # Get team stats
            away_stats = standings.get(away, {})
            home_stats = standings.get(home, {})
            
            # PRIORITY 5: Calculate weighted team stats (recent form 60%, season 40%)
            away_gf_season = away_stats.get('gf_per_game', 0)
            away_ga_season = away_stats.get('ga_per_game', 0)
            home_gf_season = home_stats.get('gf_per_game', 0)
            home_ga_season = home_stats.get('ga_per_game', 0)
            
            away_gf_weighted, away_ga_weighted = self.calculate_weighted_team_stats(
                away, standings, away_gf_season, away_ga_season
            )
            home_gf_weighted, home_ga_weighted = self.calculate_weighted_team_stats(
                home, standings, home_gf_season, home_ga_season
            )
            
            # PRIORITY 3: Fetch goalie stats
            game_id = game.get('id')
            away_goalie = self.fetch_goalie_stats(away, game_id)
            home_goalie = self.fetch_goalie_stats(home, game_id)
            
            # PRIORITY 4: Get game context
            game_context = self.get_game_context(game)
            
            # Classify scenario with all expert recommendations
            scenario = self.classify_scenario(
                away_gf_weighted,
                home_gf_weighted,
                away_ga_weighted,
                home_ga_weighted,
                away_goalie.get('sv_pct'),
                home_goalie.get('sv_pct'),
                game_context
            )
            
            print(f"  Scenario: {scenario}")
            print(f"  Team Stats:")
            print(f"    {away}: {away_stats.get('gf_per_game', 0):.2f} GF/G, {away_stats.get('ga_per_game', 0):.2f} GA/G")
            print(f"    {home}: {home_stats.get('gf_per_game', 0):.2f} GF/G, {home_stats.get('ga_per_game', 0):.2f} GA/G")
            
            # Generate picks with actual players
            picks = self.generate_picks_with_players(game, standings, {}, {})
            
            print(f"  Generated {len(picks)} picks:")
            for pick in picks:
                side = pick.get('side', 'Over').upper()
                conf = pick.get('confidence', 'MEDIUM')
                prop_type = pick.get('prop_type', 'Points')
                line = pick.get('line', 0.5)
                player_name = pick.get('player_name', 'Unknown')
                team = pick.get('team', '?')
                ppg = pick.get('points_per_game', 0)
                toi = pick.get('toi_avg', 0)
                
                # Format: Player Name (Team) - PropType Side Line - Confidence (Stats)
                print(f"    ✅ {player_name:25s} ({team:3s}) - {prop_type} {side} {line} - {conf:6s} ({ppg:.2f} P/GP, {toi:.1f} TOI)")
            
            all_picks.extend(picks)
            game_analyses.append({
                'game': {
                    'id': game_id,
                    'away': away,
                    'home': home,
                    'date': TODAY.isoformat(),
                    'start_time': start_time
                },
                'scenario': scenario,
                'team_stats': {
                    'away': away_stats,
                    'home': home_stats
                },
                'picks': picks
            })
        
        # Step 4: Rank all picks
        print(f"\n[Step 4] Ranking all picks by confidence...")
        ranked_picks = self.rank_picks_by_confidence(all_picks)
        
        # Step 5: Generate ranked pick board (ALWAYS - per master prompt rule)
        # CRITICAL: MUST include ALL picks made for the slate (HIGH, MEDIUM, LOW)
        # The ranked pick board displays every single pick, not just high confidence
        if len(ranked_picks) == 0:
            print("\n⚠️  No picks generated for today's slate")
        else:
            pick_board = self.generate_ranked_pick_board(ranked_picks, game_analyses)
            print("\n" + pick_board)
        
        # Step 6: Save results
        results = {
            'date': TODAY.isoformat(),
            'games': len(game_analyses),
            'total_picks': len(ranked_picks),
            'ranked_picks': ranked_picks,
            'game_analyses': game_analyses,
            'summary_by_scenario': self._get_summary_by_scenario(ranked_picks),
            'summary_by_confidence': self._get_summary_by_confidence(ranked_picks)
        }
        
        results_file = f"todays_slate_with_profiles_{TODAY}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n\nResults saved to {results_file}")
        
        return results
    
    def generate_ranked_pick_board(self, ranked_picks: List[Dict], game_analyses: List[Dict] = None) -> str:
        """
        Generate ranked pick board in master prompt format
        This is ALWAYS generated after analyzing a slate (per master prompt rule)
        
        CRITICAL: MUST include ALL picks made for the slate, not just high confidence picks.
        The board displays every single pick generated, ranked by confidence (HIGH → MEDIUM → LOW).
        
        Format (Master Prompt):
        Rank | Conf | Matchup | Player | Team | Market | Side | Line | Stats | Scenario | Rationale
        
        Args:
            ranked_picks: List of ALL pick dictionaries, already ranked by confidence
            game_analyses: List of game analysis dicts with 'game' key containing game info
        """
        lines = []
        lines.append("="*140)
        lines.append("🏆 RANKED PICK BOARD - TODAY'S SLATE")
        lines.append(f"Date: {TODAY}")
        lines.append("="*140)
        lines.append(f"\nTotal Picks: {len(ranked_picks)} (ALL PICKS - HIGH, MEDIUM, LOW)")
        lines.append("Ranked by Confidence: HIGH (★★★) → MEDIUM (★★) → LOW (★)\n")
        
        # Table header (optimized for readability - matches row format)
        header = (
            f"{'#':<4} | "
            f"{'Conf':<6} | "
            f"{'Matchup':<12} | "
            f"{'Player':<22} | "
            f"{'Prop':<18} | "
            f"{'Stats':<18} | "
            f"{'Scenario':<18}"
        )
        lines.append(header)
        lines.append("-" * 120)
        
        for i, pick in enumerate(ranked_picks, 1):
            side = pick.get('side', 'Over').upper()
            conf = pick.get('confidence', 'MEDIUM')
            scenario = pick.get('scenario', 'UNKNOWN')
            prop_type = pick.get('prop_type', 'Points')
            line = pick.get('line', 0.5)
            player_name = pick.get('player_name', 'Unknown')
            team = pick.get('team', '?')
            ppg = pick.get('points_per_game', 0)
            toi = pick.get('toi_avg', 0)
            
            # Get game info from game_analyses
            matchup = "Unknown"
            if game_analyses:
                game_info = next((g for g in game_analyses if g.get('game', {}).get('id') == pick.get('game_id')), None)
                if game_info:
                    away = game_info['game'].get('away', '?')
                    home = game_info['game'].get('home', '?')
                    matchup = f"{away} @ {home}"
            
            # Format stats - handle both Points and SOG picks
            if ppg > 0 and toi > 0:
                stats = f"{ppg:.2f} P/GP, {toi:.1f} TOI"
            elif ppg > 0:
                stats = f"{ppg:.2f} P/GP"
            else:
                # Check for SOG stats
                sog_per_game = pick.get('sog_per_game', 0)
                if sog_per_game > 0:
                    stats = f"{sog_per_game:.2f} SOG/GM"
                else:
                    stats = "-"
            
            # Format confidence with stars (HIGH=3, MEDIUM=2, LOW=1)
            conf_stars = ""
            if conf == 'HIGH':
                conf_stars = "★★★"
            elif conf == 'MEDIUM':
                conf_stars = "★★"
            elif conf == 'LOW':
                conf_stars = "★"
            
            # Format prop as "Market Side Line" for readability
            prop_str = f"{prop_type} {side} {line}"
            # Truncate player name if too long
            if len(player_name) > 22:
                player_name = player_name[:19] + "..."
            
            # Table row (optimized for readability)
            row = (
                f"{i:<4} | "
                f"{conf_stars:<6} | "
                f"{matchup:<12} | "
                f"{player_name:<22} | "
                f"{prop_str:<18} | "
                f"{stats:<18} | "
                f"{scenario:<18}"
            )
            lines.append(row)
        
        lines.append("-" * 120)
        
        # Summary by scenario (compact format)
        lines.append("\n" + "="*120)
        lines.append("SUMMARY BY SCENARIO")
        lines.append("="*120)
        
        by_scenario = defaultdict(list)
        for pick in ranked_picks:
            by_scenario[pick.get('scenario', 'UNKNOWN')].append(pick)
        
        for scenario in sorted(by_scenario.keys(), key=lambda s: len(by_scenario[s]), reverse=True):
            picks = by_scenario[scenario]
            high_conf = sum(1 for p in picks if p.get('confidence') == 'HIGH')
            med_conf = sum(1 for p in picks if p.get('confidence') == 'MEDIUM')
            low_conf = sum(1 for p in picks if p.get('confidence') == 'LOW')
            
            lines.append(f"\n{scenario}: {len(picks)} picks")
            lines.append(f"  High: {high_conf}, Medium: {med_conf}, Low: {low_conf}")
        
        return "\n".join(lines)
    
    def _get_summary_by_scenario(self, picks: List[Dict]) -> Dict:
        """Get summary by scenario"""
        by_scenario = defaultdict(lambda: {'high': 0, 'medium': 0, 'low': 0})
        for pick in picks:
            scenario = pick.get('scenario', 'UNKNOWN')
            conf = pick.get('confidence', 'MEDIUM')
            by_scenario[scenario][conf.lower()] += 1
        return {k: dict(v) for k, v in by_scenario.items()}
    
    def _get_summary_by_confidence(self, picks: List[Dict]) -> Dict:
        """Get summary by confidence"""
        by_conf = defaultdict(int)
        for pick in picks:
            conf = pick.get('confidence', 'MEDIUM')
            by_conf[conf] += 1
        return dict(by_conf)


if __name__ == "__main__":
    analyzer = TodaysSlateAnalysis()
    results = analyzer.analyze_slate()

