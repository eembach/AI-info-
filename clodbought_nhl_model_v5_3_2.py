#!/usr/bin/env python3
"""
Clodbought NHL Player-Prop Model v5.3.2 (Shot-Volume Architecture)

v5.2 BREAKTHROUGH - Based on correlation analysis:
- v5.0/5.1 predicted GOALS-based environment -> environment alignment didn't help
- v5.2 predicts SHOT VOLUME instead -> the TRUE predictor of prop outcomes

CRITICAL FINDING FROM BACKTEST:
- Low Shot Games (≤55 SOG): 84.5% Under hit rate (+14.6pp vs baseline)
- High Shot Games (65+ SOG): 20.0% Under hit rate (-49.9pp vs baseline)
- Goals-based environment prediction had ZERO correlation with outcomes

SHOT VOLUME is the key because:
1. SOG Unders directly depend on total shots in the game
2. Saves Unders depend on shots faced (opponent's shot volume)
3. Blowouts (77.3% Under hit) cap saves when goalies get pulled

KEY FACTORS FOR SHOT VOLUME PREDICTION:
1. Team pace/tempo (SOG for/against per game) - 40% weight
2. Goaltending matchup (elite goalies slow pace) - 25% weight
3. Defensive systems (trap teams limit attempts) - 20% weight
4. Situational (blowout potential, B2B fatigue) - 15% weight

PLAYER PROP CORRELATION TO SHOT VOLUME:
- Low-Shot Game -> SOG Unders, Saves Unders (84.5% hit rate)
- High-Shot Game -> SOG Overs, Saves Overs
- Blowout Potential -> Unders (77.3% hit rate)

The key is SHOT VOLUME prediction, not goals prediction.
"""

import datetime
import json
import math
import urllib.request
import argparse
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Set
from enum import Enum
import statistics

# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    """Model configuration with research-backed thresholds."""

    # Environment Classification Thresholds
    HIGH_EVENT_XGF_THRESHOLD = 3.2      # Combined xGF above this = high event
    LOW_EVENT_XGF_THRESHOLD = 2.6       # Combined xGF below this = low event
    HIGH_PACE_SOG_THRESHOLD = 32.0      # Team SOG/game above this = pace team
    LOW_PACE_SOG_THRESHOLD = 28.0       # Team SOG/game below this = slow team

    # Goalie Impact Thresholds (most important factor)
    ELITE_GOALIE_SV_PCT = 0.915         # Save % above this = elite
    BACKUP_GOALIE_SV_PCT = 0.905        # Save % below this = backup-tier
    GOALIE_HOT_STREAK_THRESHOLD = 0.925 # L5 save % above this = hot

    # Fatigue/Situational Factors
    B2B_SCORING_BOOST = 0.15            # +15% expected goals on B2B nights
    TRAVEL_PENALTY = 0.05               # -5% for cross-country travel

    # Special Teams
    ELITE_PP_THRESHOLD = 25.0           # PP% above this = elite
    WEAK_PK_THRESHOLD = 75.0            # PK% below this = exploitable

    # Probability Calibration (from v4 backtest learnings)
    # Raw model probabilities need to be shrunk toward 50%
    # v5.3.2: Reduced from 0.35 to 0.25 - model was under-confident
    CALIBRATION_SHRINKAGE = 0.25        # Shrink probabilities 25% toward 0.5

    # Minimum confidence for output
    MIN_EDGE_PP = 2.0                   # Minimum edge in percentage points
    MIN_CONFIDENCE = 0.53               # Minimum calibrated probability

    # Player Selection
    MIN_TOI_FOR_PROPS = 14.0            # Minimum TOI to consider for props
    MIN_SOG_AVG = 2.0                   # Minimum SOG average for SOG props


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class GameEnvironment(Enum):
    """Game environment classifications."""
    HIGH_EVENT = "High-Event"           # Expect lots of shots, goals, saves
    LOW_EVENT = "Low-Event"             # Expect suppressed stats
    NEUTRAL = "Neutral"                 # No strong lean
    VOLATILE = "Volatile"               # High variance, mixed signals


class PropDirection(Enum):
    """Which direction to bet based on environment."""
    OVER = "Over"
    UNDER = "Under"
    NO_PLAY = "No Play"


@dataclass
class GoalieProfile:
    """Goalie data for environment prediction."""
    name: str
    team: str
    player_id: int = 0

    # Season stats
    save_pct: float = 0.910
    gaa: float = 2.80
    games_played: int = 0

    # Recent form (L5 games)
    l5_save_pct: float = 0.910
    l5_gaa: float = 2.80

    # Status
    is_confirmed: bool = False
    is_starter: bool = True
    is_backup: bool = False

    @property
    def is_elite(self) -> bool:
        return self.save_pct >= Config.ELITE_GOALIE_SV_PCT

    @property
    def is_hot(self) -> bool:
        return self.l5_save_pct >= Config.GOALIE_HOT_STREAK_THRESHOLD

    @property
    def quality_score(self) -> float:
        """0-100 score for goalie quality."""
        base = (self.save_pct - 0.880) / 0.040 * 50  # 0.880 = 0, 0.920 = 50
        form_bonus = (self.l5_save_pct - self.save_pct) * 200  # +/- 20 for form
        return min(100, max(0, base + form_bonus + 50))


@dataclass
class TeamProfile:
    """Team data for environment prediction."""
    code: str
    name: str

    # Offensive metrics
    xgf_per_game: float = 2.8           # Expected goals for per game
    sog_per_game: float = 30.0          # Shots on goal per game
    goals_per_game: float = 3.0
    pp_pct: float = 20.0

    # Defensive metrics
    xga_per_game: float = 2.8           # Expected goals against per game
    sog_against_per_game: float = 30.0
    goals_against_per_game: float = 3.0
    pk_pct: float = 80.0

    # Situational
    is_home: bool = False
    is_b2b: bool = False
    days_rest: int = 2

    # Goalie
    starter: Optional[GoalieProfile] = None

    @property
    def pace_score(self) -> float:
        """0-100 score for team pace (higher = more shots)."""
        combined = self.sog_per_game + self.sog_against_per_game
        # League average ~60 combined SOG, range typically 52-68
        return (combined - 52) / 16 * 100

    @property
    def offensive_quality(self) -> float:
        """0-100 score for offensive quality."""
        return (self.xgf_per_game - 2.2) / 1.2 * 100  # 2.2 = 0, 3.4 = 100

    @property
    def defensive_quality(self) -> float:
        """0-100 score for defensive quality (higher = better defense)."""
        return (3.4 - self.xga_per_game) / 1.2 * 100  # 2.2 = 100, 3.4 = 0


@dataclass
class EnvironmentPrediction:
    """Prediction for game environment."""
    environment: GameEnvironment
    confidence: float                   # 0-1 confidence in prediction

    # Expected metrics
    expected_total_goals: float
    expected_total_sog: float
    expected_home_saves: float
    expected_away_saves: float

    # Direction recommendations
    sog_direction: PropDirection
    saves_direction: PropDirection
    goals_direction: PropDirection

    # Key factors driving prediction
    factors: List[str]

    # Raw scores for debugging
    high_event_score: float = 0.0
    low_event_score: float = 0.0


@dataclass
class PlayerProp:
    """A player prop opportunity."""
    player_name: str
    team: str
    market: str                         # "SOG", "Saves", "Points", "Goals"
    line: float
    direction: PropDirection

    # Model outputs
    expected_value: float               # Our projection
    book_implied: float                 # What line implies
    edge_pp: float                      # Edge in percentage points
    probability: float                  # Calibrated probability of hitting

    # Context
    environment: GameEnvironment
    alignment_score: float              # How well prop aligns with environment
    rationale: str

    # Correlation info for parlay building
    correlation_group: str              # Props in same group are correlated


@dataclass
class Game:
    """Game with environment prediction."""
    game_id: str
    date: datetime.date
    time: str

    home_team: TeamProfile
    away_team: TeamProfile

    # Environment prediction
    environment: Optional[EnvironmentPrediction] = None

    # Generated props
    props: List[PlayerProp] = field(default_factory=list)


@dataclass
class Parlay:
    """A correlated parlay."""
    parlay_id: str
    game_id: str
    legs: List[PlayerProp]

    # All legs should have same environment alignment
    environment: GameEnvironment
    correlation_type: str               # "Same-Script", "Cross-Game"

    # Calculations
    joint_probability: float
    expected_payout: float
    edge: float

    rationale: str


# =============================================================================
# NHL API CLIENT
# =============================================================================

class NHLAPIClient:
    """Centralized NHL API client."""

    BASE_URL = "https://api-web.nhle.com/v1"
    _cache: Dict[str, Any] = {}

    @classmethod
    def _fetch(cls, endpoint: str) -> Optional[Dict]:
        """Fetch with caching."""
        url = f"{cls.BASE_URL}/{endpoint}"
        if url in cls._cache:
            return cls._cache[url]

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())
                cls._cache[url] = data
                return data
        except Exception as e:
            print(f"API Error: {endpoint} - {e}")
            return None

    @classmethod
    def get_schedule(cls, date_str: str) -> List[Dict]:
        """Get games for a date."""
        data = cls._fetch(f"schedule/{date_str}")
        if not data:
            return []
        for day in data.get('gameWeek', []):
            if day['date'] == date_str:
                return day.get('games', [])
        return []

    @classmethod
    def get_standings(cls) -> Dict[str, Dict]:
        """Get current standings with team stats."""
        data = cls._fetch("standings/now")
        if not data:
            return {}

        teams = {}
        for team in data.get('standings', []):
            code = team.get('teamAbbrev', {}).get('default', '')
            if code:
                gp = max(1, team.get('gamesPlayed', 1))
                teams[code] = {
                    'goals_for': team.get('goalFor', 0) / gp,
                    'goals_against': team.get('goalAgainst', 0) / gp,
                    'gp': gp,
                }
        return teams

    @classmethod
    def get_club_stats(cls, team_code: str) -> Dict:
        """Get detailed team stats."""
        return cls._fetch(f"club-stats/{team_code}/now") or {}

    @classmethod
    def get_team_schedule(cls, team_code: str) -> List[Dict]:
        """Get team's recent schedule for B2B detection."""
        data = cls._fetch(f"club-schedule/{team_code}/week/now")
        return data.get('games', []) if data else []

    @classmethod
    def reset_cache(cls):
        """Clear cache for fresh data."""
        cls._cache = {}


# =============================================================================
# TEAM DATABASE
# =============================================================================

class TeamDatabase:
    """Team stats database with NHL API integration."""

    _teams: Dict[str, TeamProfile] = {}
    _loaded = False

    # Hardcoded xG estimates (would ideally come from MoneyPuck API)
    # Based on 2024-25 season data
    XG_ESTIMATES = {
        "COL": {"xgf": 3.4, "xga": 2.7},
        "EDM": {"xgf": 3.3, "xga": 2.9},
        "TOR": {"xgf": 3.2, "xga": 2.8},
        "FLA": {"xgf": 3.1, "xga": 2.5},
        "VGK": {"xgf": 3.1, "xga": 2.6},
        "CAR": {"xgf": 3.0, "xga": 2.4},
        "DAL": {"xgf": 2.9, "xga": 2.5},
        "WPG": {"xgf": 3.2, "xga": 2.7},
        "NJD": {"xgf": 3.0, "xga": 2.8},
        "NYR": {"xgf": 2.8, "xga": 2.5},
        "BOS": {"xgf": 2.9, "xga": 2.6},
        "TBL": {"xgf": 3.0, "xga": 2.8},
        "MIN": {"xgf": 2.8, "xga": 2.6},
        "LAK": {"xgf": 2.7, "xga": 2.6},
        "VAN": {"xgf": 2.9, "xga": 2.8},
        # Default for others
        "DEFAULT": {"xgf": 2.8, "xga": 2.8}
    }

    # Goalie database (would ideally be dynamic)
    GOALIES = {
        "COL": {"name": "Alexandar Georgiev", "sv": 0.897, "gaa": 3.02},
        "EDM": {"name": "Stuart Skinner", "sv": 0.898, "gaa": 2.95},
        "TOR": {"name": "Joseph Woll", "sv": 0.912, "gaa": 2.55},
        "FLA": {"name": "Sergei Bobrovsky", "sv": 0.908, "gaa": 2.78},
        "VGK": {"name": "Adin Hill", "sv": 0.905, "gaa": 2.85},
        "CAR": {"name": "Pyotr Kochetkov", "sv": 0.909, "gaa": 2.65},
        "DAL": {"name": "Jake Oettinger", "sv": 0.912, "gaa": 2.48},
        "WPG": {"name": "Connor Hellebuyck", "sv": 0.921, "gaa": 2.28},
        "NJD": {"name": "Jacob Markstrom", "sv": 0.906, "gaa": 2.75},
        "NYR": {"name": "Igor Shesterkin", "sv": 0.918, "gaa": 2.35},
        "BOS": {"name": "Jeremy Swayman", "sv": 0.916, "gaa": 2.42},
        "TBL": {"name": "Andrei Vasilevskiy", "sv": 0.908, "gaa": 2.72},
        "MIN": {"name": "Filip Gustavsson", "sv": 0.910, "gaa": 2.58},
    }

    @classmethod
    def load(cls):
        """Load team data from NHL API."""
        if cls._loaded:
            return

        standings = NHLAPIClient.get_standings()

        for code, stats in standings.items():
            # Get club stats for SOG data
            club_data = NHLAPIClient.get_club_stats(code)
            skaters = club_data.get('skaters', [])
            goalies = club_data.get('goalies', [])

            gp = stats.get('gp', 1)
            total_shots = sum(s.get('shots', 0) for s in skaters)
            total_sa = sum(g.get('shotsAgainst', 0) for g in goalies)

            sog_for = total_shots / gp if gp > 0 else 30.0
            sog_against = total_sa / gp if gp > 0 else 30.0

            # Get xG estimates
            xg_data = cls.XG_ESTIMATES.get(code, cls.XG_ESTIMATES["DEFAULT"])

            # Get goalie data
            goalie_data = cls.GOALIES.get(code, {"name": f"{code} Goalie", "sv": 0.905, "gaa": 2.80})
            goalie = GoalieProfile(
                name=goalie_data["name"],
                team=code,
                save_pct=goalie_data["sv"],
                gaa=goalie_data["gaa"],
                l5_save_pct=goalie_data["sv"],
                l5_gaa=goalie_data["gaa"],
                is_starter=True
            )

            cls._teams[code] = TeamProfile(
                code=code,
                name=code,
                xgf_per_game=xg_data["xgf"],
                xga_per_game=xg_data["xga"],
                sog_per_game=sog_for,
                sog_against_per_game=sog_against,
                goals_per_game=stats['goals_for'],
                goals_against_per_game=stats['goals_against'],
                starter=goalie
            )

        cls._loaded = True

    @classmethod
    def get_team(cls, code: str) -> TeamProfile:
        """Get team profile."""
        if not cls._loaded:
            cls.load()

        if code in cls._teams:
            return cls._teams[code]

        # Return default for unknown teams
        return TeamProfile(code=code, name=code)

    @classmethod
    def reset(cls):
        """Reset for fresh data."""
        cls._teams = {}
        cls._loaded = False


# =============================================================================
# ENVIRONMENT PREDICTION ENGINE
# =============================================================================

class EnvironmentPredictor:
    """
    Predicts game environment (high-event vs low-event).

    This is the CORE of v5 - we predict the game script first,
    then select player props that align with it.
    """

    @classmethod
    def predict(cls, home: TeamProfile, away: TeamProfile) -> EnvironmentPrediction:
        """
        Predict game environment based on team profiles.

        Returns:
            EnvironmentPrediction with classification and recommendations
        """
        factors = []

        # =================================================================
        # FACTOR 1: GOALTENDING (30% weight)
        # Most important factor - elite goalies suppress scoring by 20-30%
        # =================================================================
        goalie_score = cls._score_goaltending(home, away, factors)

        # =================================================================
        # FACTOR 2: PACE/TEMPO (25% weight)
        # High-pace teams generate more shots and chances
        # =================================================================
        pace_score = cls._score_pace(home, away, factors)

        # =================================================================
        # FACTOR 3: TEAM QUALITY MATCHUP (20% weight)
        # xGF differential predicts scoring
        # =================================================================
        quality_score = cls._score_quality(home, away, factors)

        # =================================================================
        # FACTOR 4: SITUATIONAL (15% weight)
        # B2B, travel, rest days affect energy and focus
        # =================================================================
        situational_score = cls._score_situational(home, away, factors)

        # =================================================================
        # FACTOR 5: SPECIAL TEAMS (10% weight)
        # PP/PK efficiency affects scoring opportunities
        # =================================================================
        special_teams_score = cls._score_special_teams(home, away, factors)

        # =================================================================
        # COMBINE SCORES - v5.2 SHOT-VOLUME FOCUSED
        # =================================================================
        # v5.2 Key insight: PACE (shot volume) is the PRIMARY predictor
        # Goals-based factors had zero correlation with prop outcomes
        # Low-shot games hit 84.5% on Unders vs 20% in high-shot games
        combined_score = (
            pace_score * 0.40 +           # INCREASED from 25% - most important
            goalie_score * 0.25 +         # Elite goalies slow pace
            situational_score * 0.20 +    # B2B, blowout potential
            quality_score * 0.10 +        # Reduced - goals ≠ shots
            special_teams_score * 0.05    # Minimal impact on total shots
        )

        # Classify environment
        # v5.1: Tightened thresholds - backtest showed model was classifying
        # ALL games as Low-Event. Now use 55/45 for more balanced distribution.
        if combined_score >= 55:
            environment = GameEnvironment.HIGH_EVENT
            confidence = min(0.85, 0.50 + (combined_score - 55) / 90)
        elif combined_score <= 45:
            environment = GameEnvironment.LOW_EVENT
            confidence = min(0.85, 0.50 + (45 - combined_score) / 90)
        else:
            environment = GameEnvironment.NEUTRAL
            confidence = 0.50

        # Calculate expected metrics
        expected_goals = cls._project_total_goals(home, away, combined_score)
        expected_sog = cls._project_total_sog(home, away, combined_score)

        # Expected saves based on opponent shots and goalie quality
        away_expected_sog = away.sog_per_game * (1 + (combined_score - 50) / 200)
        home_expected_sog = home.sog_per_game * (1 + (combined_score - 50) / 200)

        home_goalie_sv = home.starter.save_pct if home.starter else 0.905
        away_goalie_sv = away.starter.save_pct if away.starter else 0.905

        expected_home_saves = away_expected_sog * home_goalie_sv
        expected_away_saves = home_expected_sog * away_goalie_sv

        # Determine prop directions based on environment
        if environment == GameEnvironment.HIGH_EVENT:
            sog_direction = PropDirection.OVER
            saves_direction = PropDirection.OVER
            goals_direction = PropDirection.OVER
        elif environment == GameEnvironment.LOW_EVENT:
            sog_direction = PropDirection.UNDER
            saves_direction = PropDirection.UNDER
            goals_direction = PropDirection.UNDER
        else:
            sog_direction = PropDirection.NO_PLAY
            saves_direction = PropDirection.NO_PLAY
            goals_direction = PropDirection.NO_PLAY

        return EnvironmentPrediction(
            environment=environment,
            confidence=confidence,
            expected_total_goals=expected_goals,
            expected_total_sog=expected_sog,
            expected_home_saves=expected_home_saves,
            expected_away_saves=expected_away_saves,
            sog_direction=sog_direction,
            saves_direction=saves_direction,
            goals_direction=goals_direction,
            factors=factors,
            high_event_score=combined_score,
            low_event_score=100 - combined_score
        )

    @classmethod
    def _score_goaltending(cls, home: TeamProfile, away: TeamProfile, factors: List[str]) -> float:
        """
        Score goaltending matchup (0-100).
        Lower quality goalies = higher event score.

        v5.1: Fixed double-counting issue. Now uses simpler calculation:
        - Average goalie (0.905 sv%) = 50 score
        - Elite goalie (0.920 sv%) = 20 score (more suppression)
        - Weak goalie (0.890 sv%) = 80 score (more scoring)
        """
        home_goalie = home.starter
        away_goalie = away.starter

        # Convert save % to event score (higher sv% = lower event potential)
        # 0.890 = 80, 0.905 = 50, 0.920 = 20
        def sv_to_score(sv_pct: float) -> float:
            return max(0, min(100, 50 + (0.905 - sv_pct) * 1000))

        home_sv = home_goalie.save_pct if home_goalie else 0.905
        away_sv = away_goalie.save_pct if away_goalie else 0.905

        goalie_score = (sv_to_score(home_sv) + sv_to_score(away_sv)) / 2

        # Add factors for logging (no score adjustment - already baked into sv%)
        if home_goalie and home_goalie.is_elite:
            factors.append(f"Elite G: {home_goalie.name} (sv% {home_goalie.save_pct:.3f})")
        if away_goalie and away_goalie.is_elite:
            factors.append(f"Elite G: {away_goalie.name} (sv% {away_goalie.save_pct:.3f})")

        # Form adjustment: hot goalie = -5, cold goalie = +5
        if home_goalie and home_goalie.is_hot:
            factors.append(f"Hot G: {home_goalie.name} (L5: {home_goalie.l5_save_pct:.3f})")
            goalie_score -= 5
        if away_goalie and away_goalie.is_hot:
            factors.append(f"Hot G: {away_goalie.name} (L5: {away_goalie.l5_save_pct:.3f})")
            goalie_score -= 5

        return max(0, min(100, goalie_score))

    @classmethod
    def _score_pace(cls, home: TeamProfile, away: TeamProfile, factors: List[str]) -> float:
        """
        Score pace/tempo matchup (0-100).
        Higher combined SOG = higher event score.

        v5.3.1: High-shot games (65+ SOG) hit only 42.3% on Unders.
        We need to heavily penalize or skip these games.
        """
        combined_sog = home.sog_per_game + away.sog_per_game
        # League average ~60, range 52-68
        pace_score = (combined_sog - 52) / 16 * 100

        if combined_sog > 64:
            factors.append(f"⚠️ HIGH PACE WARNING: {combined_sog:.1f} combined SOG/game")
            # v5.3.1: Push toward Neutral (no plays) for high-pace games
            pace_score = min(pace_score, 75)  # Cap to push toward Neutral zone
        elif combined_sog < 56:
            factors.append(f"Low Pace: {combined_sog:.1f} combined SOG/game")

        return max(0, min(100, pace_score))

    @classmethod
    def _score_quality(cls, home: TeamProfile, away: TeamProfile, factors: List[str]) -> float:
        """
        Score offensive quality matchup (0-100).
        Higher combined xGF = higher event score.

        v5.1: Recentered so league average (5.6 combined xGF) = 50
        """
        combined_xgf = home.xgf_per_game + away.xgf_per_game
        # League average ~5.6, range 4.8-6.8
        # Now centered: 5.6 = 50, 4.8 = 20, 6.8 = 85
        quality_score = 50 + (combined_xgf - 5.6) * 30

        if combined_xgf > 6.2:
            factors.append(f"Offensive Firepower: {combined_xgf:.1f} combined xGF")
        elif combined_xgf < 5.2:
            factors.append(f"Low Offense: {combined_xgf:.1f} combined xGF")

        return max(0, min(100, quality_score))

    @classmethod
    def _score_situational(cls, home: TeamProfile, away: TeamProfile, factors: List[str]) -> float:
        """
        Score situational factors (0-100).

        v5.2 Key insight: Blowouts favor Unders (77.3% hit rate)
        v5.3 Added: Rivalry games, travel factors
        """
        score = 50  # Neutral baseline

        # =================================================================
        # B2B FATIGUE
        # =================================================================
        if home.is_b2b:
            score += 8  # Slight boost - more sloppy play
            factors.append(f"{home.code} B2B")
        if away.is_b2b:
            score += 8
            factors.append(f"{away.code} B2B")

        # =================================================================
        # BLOWOUT POTENTIAL
        # =================================================================
        home_quality = home.xgf_per_game - home.xga_per_game
        away_quality = away.xgf_per_game - away.xga_per_game
        quality_diff = abs(home_quality - away_quality)

        if quality_diff > 0.5:
            score -= 10  # Blowouts cap props (pulled players)
            factors.append(f"Blowout potential ({quality_diff:.2f} diff)")

        # =================================================================
        # RIVALRY GAMES - Increase intensity/shot volume
        # =================================================================
        rivalry = PropGenerator.get_rivalry_intensity(home.code, away.code)
        if rivalry == "intense":
            score += 12  # More shots in rivalry games
            factors.append(f"Intense rivalry: {away.code}@{home.code}")
        elif rivalry == "moderate":
            score += 6
            factors.append(f"Rivalry game")

        # =================================================================
        # TRAVEL FATIGUE
        # =================================================================
        travel_penalty = PropGenerator.get_travel_penalty(away.code, home.code)
        if travel_penalty > 0.05:
            score += 5  # Tired team = sloppier play = more chances
            factors.append(f"{away.code} travel fatigue ({travel_penalty:.0%})")

        # =================================================================
        # REST ADVANTAGE
        # =================================================================
        if home.days_rest >= 3 and away.days_rest <= 1:
            score -= 8  # Fresh home team = more controlled game
            factors.append(f"{home.code} rest advantage")

        return max(0, min(100, score))

    @classmethod
    def _score_special_teams(cls, home: TeamProfile, away: TeamProfile, factors: List[str]) -> float:
        """
        Score special teams matchup (0-100).
        Elite PP vs weak PK = higher scoring.
        """
        score = 50

        # Elite PP facing weak PK
        if home.pp_pct >= Config.ELITE_PP_THRESHOLD and away.pk_pct <= Config.WEAK_PK_THRESHOLD:
            score += 20
            factors.append(f"{home.code} PP ({home.pp_pct:.1f}%) vs {away.code} PK ({away.pk_pct:.1f}%)")

        if away.pp_pct >= Config.ELITE_PP_THRESHOLD and home.pk_pct <= Config.WEAK_PK_THRESHOLD:
            score += 20
            factors.append(f"{away.code} PP ({away.pp_pct:.1f}%) vs {home.code} PK ({home.pk_pct:.1f}%)")

        return max(0, min(100, score))

    @classmethod
    def _project_total_goals(cls, home: TeamProfile, away: TeamProfile, env_score: float) -> float:
        """Project total goals for the game."""
        base_total = home.xgf_per_game + away.xgf_per_game
        # Adjust by environment score
        adjustment = (env_score - 50) / 100 * 1.5  # +/- 0.75 goals
        return base_total + adjustment

    @classmethod
    def _project_total_sog(cls, home: TeamProfile, away: TeamProfile, env_score: float) -> float:
        """Project total SOG for the game."""
        base_total = home.sog_per_game + away.sog_per_game
        # Adjust by environment score
        adjustment = (env_score - 50) / 100 * 8  # +/- 4 SOG
        return base_total + adjustment


# =============================================================================
# PROP GENERATOR - Select props aligned with environment
# =============================================================================

class PropGenerator:
    """
    Generates player props that ALIGN with the predicted game environment.

    Key insight: Don't fight the game script. If we predict high-event,
    bet Overs. If we predict low-event, bet Unders. All legs should
    ride the same wave for correlation benefit.
    """

    # Player value ratings based on backtest analysis + league-wide patterns
    # Positive = line is inflated (good for Unders)
    # Negative = line is too tight (good for Overs)
    # Values based on: historical variance, public perception, line movement patterns
    PLAYER_LINE_VALUE = {
        # =================================================================
        # TIER 1: HIGH UNDER VALUE (+0.15 to +0.25)
        # Lines consistently inflated due to name recognition or variance
        # =================================================================
        "Jared McCann": +0.20,        # Public overrates, low volume shooter
        "Mark Scheifele": +0.18,      # Pass-first, inconsistent shooting
        "Connor Bedard": +0.15,       # Rookie hype inflates line
        "Bo Horvat": +0.15,           # Playmaker, not volume shooter
        "Mathew Barzal": +0.15,       # Speed player, lower shot rate
        "Sebastian Aho": +0.12,       # Efficient, not volume shooter
        "Jesper Bratt": +0.12,        # Pass-first winger

        # =================================================================
        # TIER 2: MODERATE UNDER VALUE (+0.08 to +0.12)
        # Solid Under candidates, lines slightly inflated
        # =================================================================
        "Kyle Connor": +0.12,         # Streaky shooter
        "Kirill Kaprizov": +0.10,     # Elite but lines overpriced
        "Nazem Kadri": +0.10,         # Declining shot rate
        "Jason Robertson": +0.10,     # Efficient sniper, low volume
        "Jack Eichel": +0.08,         # Injury concerns, varies
        "Brady Tkachuk": +0.08,       # Power forward, not sniper
        "Sam Reinhart": +0.08,        # Opportunistic scorer
        "Adrian Kempe": +0.08,        # Solid but not elite
        "Sidney Crosby": +0.08,       # Playmaker first
        "Artemi Panarin": +0.06,      # Pass-first star
        "William Nylander": +0.06,    # Streaky
        "Leon Draisaitl": +0.05,      # Elite but playmaker role
        "Jack Hughes": +0.05,         # Young, inconsistent

        # =================================================================
        # TIER 3: NEUTRAL (0 to +0.05)
        # Fair lines, slight edge possible
        # =================================================================
        "Connor McDavid": +0.03,      # Best player but fair lines
        "Matthew Tkachuk": +0.03,     # Physical, not sniper
        "Tage Thompson": +0.02,       # High variance
        "Troy Terry": +0.02,
        "Frank Vatrano": +0.02,

        # =================================================================
        # TIER 4: LOW/NEGATIVE UNDER VALUE (-0.05 to -0.25)
        # Lines too tight, player beats them - SKIP for Unders
        # =================================================================
        "Cole Caufield": -0.05,       # Pure sniper, beats lines
        "David Pastrnak": -0.08,      # Elite shooter, often goes over
        "Cale Makar": -0.08,          # D-man who shoots a lot
        "Auston Matthews": -0.10,     # Volume shooter
        "Nikita Kucherov": -0.12,     # Elite shooter, beats lines
        "Nathan MacKinnon": -0.25,    # Volume king, always goes over
        "Alex Ovechkin": -0.08,       # Still shoots everything
        "Mikko Rantanen": -0.05,      # High volume
        "Chris Kreider": -0.05,       # Sniper
        "Filip Forsberg": -0.05,      # Sniper
        "Brock Boeser": -0.03,        # Sniper type
        "Travis Konecny": -0.03,      # High motor

        # Additional neutral/positive players
        "Mitch Marner": +0.15,        # Playmaker, rarely shoots
        "Aleksander Barkov": +0.12,   # Two-way, not volume
        "Mark Stone": +0.10,          # Pass-first
        "Robert Thomas": +0.12,       # Playmaker
        "Elias Pettersson": +0.05,    # Can be passive
        "Roman Josi": +0.05,          # D-man, varies
        "Nick Suzuki": +0.08,         # Playmaker
        "Tim Stutzle": +0.05,         # Young, developing

        # v5.3.1 CORRECTIONS - Based on blind backtest (0% hit rate)
        # These players were WRONG in our database - they beat their lines
        "Jesper Bratt": -0.15,        # WAS +0.12, actually 0/3 - beats line!
        "Nico Hischier": -0.10,       # WAS +0.10, actually 0/2 - beats line!
        "Dylan Larkin": -0.12,        # WAS +0.08, actually 0/3 - beats line!
        "Adrian Kempe": -0.08,        # WAS +0.08, actually 0/2 - beats line!
        "Brad Marchand": -0.08,       # WAS 0.00, actually 1/3 - beats line!
        "Claude Giroux": -0.05,       # 1/3 performance
        "Matt Boldy": -0.05,          # 0/2 misses
        "Clayton Keller": -0.03,      # Mixed results

        # v5.3.2 CORRECTIONS - Based on extended backtest
        "Macklin Celebrini": -0.20,   # 0/5 - rookie with heavy usage
        "William Nylander": -0.10,    # 1/4 (25%) - beats lines consistently
        "Bo Horvat": 0.00,            # 1/3 (33%) - WAS +0.15, overrated
        "Tage Thompson": -0.08,       # 2/6 (33%) - WAS +0.02, volume shooter
        "Mikko Rantanen": -0.12,      # 0/2 - elite volume shooter
        "Dylan Cozens": -0.05,        # 2/6 (33%) - young shooter
        "Andrei Svechnikov": -0.05,   # beats lines
    }

    # =================================================================
    # RIVALRY GAMES - Affect intensity and shot volume
    # =================================================================
    RIVALRY_PAIRS = {
        # Intense rivalries (typically higher event)
        ("TOR", "MTL"): "intense",     # Original Six
        ("TOR", "BOS"): "intense",     # Original Six
        ("TOR", "OTT"): "intense",     # Battle of Ontario
        ("NYR", "NYI"): "intense",     # NY rivalry
        ("NYR", "NJD"): "intense",     # Hudson River
        ("PHI", "PIT"): "intense",     # PA rivalry
        ("CHI", "DET"): "intense",     # Original Six
        ("COL", "DET"): "intense",     # 90s blood feud
        ("EDM", "CGY"): "intense",     # Battle of Alberta
        ("LAK", "ANA"): "intense",     # Freeway series
        ("LAK", "SJS"): "moderate",    # California
        ("VGK", "COL"): "moderate",    # New rivalry
        ("VGK", "SJS"): "moderate",
        ("FLA", "TBL"): "moderate",    # Florida
        ("BOS", "MTL"): "intense",     # Original Six
        ("CAR", "WSH"): "moderate",    # Metro
        ("MIN", "COL"): "moderate",    # Central
        ("WPG", "MIN"): "moderate",    # Central
    }

    # =================================================================
    # TIMEZONE TRAVEL - Affects fatigue and performance
    # =================================================================
    TEAM_TIMEZONES = {
        # Eastern
        "TOR": "ET", "MTL": "ET", "OTT": "ET", "BOS": "ET", "BUF": "ET",
        "NYR": "ET", "NYI": "ET", "NJD": "ET", "PHI": "ET", "PIT": "ET",
        "WSH": "ET", "CAR": "ET", "CBJ": "ET", "DET": "ET", "FLA": "ET", "TBL": "ET",
        # Central
        "CHI": "CT", "MIN": "CT", "WPG": "CT", "STL": "CT", "NSH": "CT", "DAL": "CT",
        "COL": "MT", "UTA": "MT", "CGY": "MT", "EDM": "MT",
        # Pacific
        "VGK": "PT", "LAK": "PT", "ANA": "PT", "SJS": "PT", "SEA": "PT", "VAN": "PT",
    }

    TIMEZONE_DIFF = {
        ("ET", "PT"): 3, ("ET", "MT"): 2, ("ET", "CT"): 1,
        ("CT", "PT"): 2, ("CT", "MT"): 1, ("CT", "ET"): 1,
        ("MT", "PT"): 1, ("MT", "ET"): 2, ("MT", "CT"): 1,
        ("PT", "ET"): 3, ("PT", "MT"): 1, ("PT", "CT"): 2,
    }

    # Key players by team (for prop generation)
    # v5.3: Expanded rosters with more players per team
    KEY_PLAYERS = {
        "COL": [
            {"name": "Nathan MacKinnon", "sog": 4.5, "pts": 1.6, "toi": 22.0},
            {"name": "Cale Makar", "sog": 3.2, "pts": 1.2, "toi": 25.0},
            {"name": "Mikko Rantanen", "sog": 3.3, "pts": 1.1, "toi": 20.0},
        ],
        "EDM": [
            {"name": "Connor McDavid", "sog": 3.8, "pts": 1.8, "toi": 22.0},
            {"name": "Leon Draisaitl", "sog": 3.5, "pts": 1.4, "toi": 21.0},
            {"name": "Zach Hyman", "sog": 3.2, "pts": 0.8, "toi": 18.0},
        ],
        "TOR": [
            {"name": "Auston Matthews", "sog": 4.5, "pts": 1.2, "toi": 21.0},
            {"name": "William Nylander", "sog": 3.5, "pts": 1.0, "toi": 19.0},
            {"name": "Mitch Marner", "sog": 2.5, "pts": 1.1, "toi": 20.0},
        ],
        "WPG": [
            {"name": "Kyle Connor", "sog": 3.5, "pts": 1.1, "toi": 20.0},
            {"name": "Mark Scheifele", "sog": 3.0, "pts": 1.0, "toi": 19.0},
            {"name": "Nikolaj Ehlers", "sog": 2.8, "pts": 0.8, "toi": 17.0},
        ],
        "FLA": [
            {"name": "Matthew Tkachuk", "sog": 3.2, "pts": 1.0, "toi": 19.0},
            {"name": "Sam Reinhart", "sog": 3.0, "pts": 1.0, "toi": 18.0},
            {"name": "Aleksander Barkov", "sog": 2.5, "pts": 0.9, "toi": 20.0},
        ],
        "VGK": [
            {"name": "Jack Eichel", "sog": 4.0, "pts": 1.1, "toi": 20.0},
            {"name": "Mark Stone", "sog": 2.5, "pts": 0.9, "toi": 19.0},
        ],
        "DAL": [
            {"name": "Jason Robertson", "sog": 3.2, "pts": 1.0, "toi": 19.0},
            {"name": "Roope Hintz", "sog": 2.8, "pts": 0.8, "toi": 18.0},
            {"name": "Wyatt Johnston", "sog": 2.5, "pts": 0.7, "toi": 17.0},
        ],
        "CAR": [
            {"name": "Sebastian Aho", "sog": 3.0, "pts": 1.0, "toi": 20.0},
            {"name": "Andrei Svechnikov", "sog": 3.0, "pts": 0.8, "toi": 18.0},
            {"name": "Seth Jarvis", "sog": 2.5, "pts": 0.7, "toi": 16.0},
        ],
        "NYR": [
            {"name": "Artemi Panarin", "sog": 3.2, "pts": 1.2, "toi": 19.0},
            {"name": "Mika Zibanejad", "sog": 3.0, "pts": 0.8, "toi": 19.0},
            {"name": "Chris Kreider", "sog": 3.2, "pts": 0.7, "toi": 17.0},
        ],
        "NJD": [
            {"name": "Jack Hughes", "sog": 4.0, "pts": 1.2, "toi": 20.0},
            {"name": "Jesper Bratt", "sog": 2.8, "pts": 1.0, "toi": 19.0},
            {"name": "Nico Hischier", "sog": 2.5, "pts": 0.7, "toi": 18.0},
        ],
        "TBL": [
            {"name": "Nikita Kucherov", "sog": 3.5, "pts": 1.5, "toi": 20.0},
            {"name": "Brayden Point", "sog": 3.0, "pts": 0.9, "toi": 19.0},
        ],
        "BOS": [
            {"name": "David Pastrnak", "sog": 4.2, "pts": 1.2, "toi": 20.0},
            {"name": "Brad Marchand", "sog": 2.5, "pts": 0.8, "toi": 18.0},
        ],
        "MIN": [
            {"name": "Kirill Kaprizov", "sog": 3.5, "pts": 1.3, "toi": 21.0},
            {"name": "Matt Boldy", "sog": 2.5, "pts": 0.7, "toi": 17.0},
        ],
        "BUF": [
            {"name": "Tage Thompson", "sog": 3.8, "pts": 1.0, "toi": 20.0},
            {"name": "Alex Tuch", "sog": 2.8, "pts": 0.7, "toi": 18.0},
            {"name": "Dylan Cozens", "sog": 2.5, "pts": 0.6, "toi": 17.0},
        ],
        "OTT": [
            {"name": "Brady Tkachuk", "sog": 4.0, "pts": 0.9, "toi": 20.0},
            {"name": "Tim Stutzle", "sog": 2.8, "pts": 0.9, "toi": 19.0},
            {"name": "Claude Giroux", "sog": 2.2, "pts": 0.7, "toi": 17.0},
        ],
        "CHI": [
            {"name": "Connor Bedard", "sog": 3.5, "pts": 1.0, "toi": 19.0},
        ],
        "LAK": [
            {"name": "Adrian Kempe", "sog": 3.2, "pts": 0.8, "toi": 18.0},
            {"name": "Anze Kopitar", "sog": 2.2, "pts": 0.7, "toi": 19.0},
        ],
        "ANA": [
            {"name": "Troy Terry", "sog": 2.8, "pts": 0.8, "toi": 18.0},
            {"name": "Frank Vatrano", "sog": 3.2, "pts": 0.7, "toi": 16.0},
            {"name": "Leo Carlsson", "sog": 2.5, "pts": 0.6, "toi": 17.0},
        ],
        "SEA": [
            {"name": "Jared McCann", "sog": 3.0, "pts": 0.9, "toi": 18.0},
            {"name": "Matty Beniers", "sog": 2.2, "pts": 0.6, "toi": 17.0},
        ],
        "CGY": [
            {"name": "Nazem Kadri", "sog": 3.2, "pts": 0.9, "toi": 19.0},
            {"name": "Jonathan Huberdeau", "sog": 2.2, "pts": 0.7, "toi": 18.0},
        ],
        "MTL": [
            {"name": "Cole Caufield", "sog": 3.5, "pts": 0.9, "toi": 18.0},
            {"name": "Nick Suzuki", "sog": 2.5, "pts": 0.8, "toi": 19.0},
        ],
        "PIT": [
            {"name": "Sidney Crosby", "sog": 3.0, "pts": 1.0, "toi": 20.0},
            {"name": "Evgeni Malkin", "sog": 2.8, "pts": 0.8, "toi": 17.0},
        ],
        "NYI": [
            {"name": "Bo Horvat", "sog": 3.0, "pts": 0.8, "toi": 18.0},
            {"name": "Mathew Barzal", "sog": 2.8, "pts": 0.9, "toi": 19.0},
        ],
        "WSH": [
            {"name": "Alex Ovechkin", "sog": 4.0, "pts": 0.9, "toi": 18.0},
            {"name": "Dylan Strome", "sog": 2.5, "pts": 0.8, "toi": 17.0},
        ],
        "DET": [
            {"name": "Lucas Raymond", "sog": 2.8, "pts": 0.8, "toi": 18.0},
            {"name": "Dylan Larkin", "sog": 2.5, "pts": 0.7, "toi": 19.0},
        ],
        "PHI": [
            {"name": "Travis Konecny", "sog": 3.2, "pts": 0.9, "toi": 19.0},
            {"name": "Matvei Michkov", "sog": 2.8, "pts": 0.7, "toi": 17.0},
        ],
        "CBJ": [
            {"name": "Kirill Marchenko", "sog": 3.0, "pts": 0.7, "toi": 17.0},
        ],
        "NSH": [
            {"name": "Filip Forsberg", "sog": 3.5, "pts": 0.9, "toi": 19.0},
            {"name": "Roman Josi", "sog": 2.8, "pts": 0.8, "toi": 24.0},
        ],
        "STL": [
            {"name": "Jordan Kyrou", "sog": 3.0, "pts": 0.8, "toi": 18.0},
            {"name": "Robert Thomas", "sog": 2.2, "pts": 0.9, "toi": 19.0},
        ],
        "VAN": [
            {"name": "J.T. Miller", "sog": 3.0, "pts": 0.9, "toi": 19.0},
            {"name": "Elias Pettersson", "sog": 2.8, "pts": 0.9, "toi": 19.0},
            {"name": "Brock Boeser", "sog": 3.2, "pts": 0.7, "toi": 17.0},
        ],
        "SJS": [
            {"name": "Macklin Celebrini", "sog": 2.5, "pts": 0.6, "toi": 17.0},
            {"name": "William Eklund", "sog": 2.2, "pts": 0.5, "toi": 16.0},
        ],
        "UTA": [
            {"name": "Clayton Keller", "sog": 3.0, "pts": 0.8, "toi": 19.0},
            {"name": "Nick Schmaltz", "sog": 2.5, "pts": 0.7, "toi": 18.0},
        ],
    }

    @classmethod
    def get_rivalry_intensity(cls, team1: str, team2: str) -> Optional[str]:
        """Check if this is a rivalry game."""
        pair1 = (team1, team2)
        pair2 = (team2, team1)
        return cls.RIVALRY_PAIRS.get(pair1) or cls.RIVALRY_PAIRS.get(pair2)

    @classmethod
    def get_travel_penalty(cls, away_team: str, home_team: str) -> float:
        """Calculate travel fatigue penalty for away team (0-0.15)."""
        away_tz = cls.TEAM_TIMEZONES.get(away_team, "CT")
        home_tz = cls.TEAM_TIMEZONES.get(home_team, "CT")

        if away_tz == home_tz:
            return 0.0

        tz_diff = cls.TIMEZONE_DIFF.get((away_tz, home_tz), 0)

        # Westward travel is harder (lose time)
        if away_tz in ["ET", "CT"] and home_tz in ["PT", "MT"]:
            return tz_diff * 0.03  # 3% penalty per timezone crossed going west

        # Eastward travel (gain time) is slightly easier
        return tz_diff * 0.02

    @classmethod
    def generate_props(cls, game: Game) -> List[PlayerProp]:
        """
        Generate props aligned with game environment.
        """
        if not game.environment:
            return []

        env = game.environment
        props = []

        # Only generate props for non-neutral environments
        if env.environment == GameEnvironment.NEUTRAL:
            return []

        # Generate goalie saves props
        saves_props = cls._generate_saves_props(game, env)
        props.extend(saves_props)

        # Generate SOG props
        sog_props = cls._generate_sog_props(game, env)
        props.extend(sog_props)

        # Filter by minimum edge
        props = [p for p in props if p.edge_pp >= Config.MIN_EDGE_PP]

        return props

    @classmethod
    def _generate_saves_props(cls, game: Game, env: EnvironmentPrediction) -> List[PlayerProp]:
        """Generate goalie saves props aligned with environment."""
        props = []

        # Home goalie
        if game.home_team.starter:
            prop = cls._create_saves_prop(
                game.home_team.starter,
                game.away_team,
                env.expected_home_saves,
                env
            )
            if prop:
                props.append(prop)

        # Away goalie
        if game.away_team.starter:
            prop = cls._create_saves_prop(
                game.away_team.starter,
                game.home_team,
                env.expected_away_saves,
                env
            )
            if prop:
                props.append(prop)

        return props

    @classmethod
    def _create_saves_prop(
        cls,
        goalie: GoalieProfile,
        opponent: TeamProfile,
        expected_saves: float,
        env: EnvironmentPrediction
    ) -> Optional[PlayerProp]:
        """Create a saves prop for a goalie."""

        direction = env.saves_direction
        if direction == PropDirection.NO_PLAY:
            return None

        # Book lines are typically set around 26.5-28.5 regardless of matchup
        # We use expected saves vs typical book line to find edge
        typical_book_line = 27.5  # Most common saves line

        # Adjust book line based on opponent shot volume
        if opponent.sog_per_game > 32:
            typical_book_line = 28.5
        elif opponent.sog_per_game < 28:
            typical_book_line = 26.5

        book_line = typical_book_line

        # Calculate edge based on our expected vs book line
        if direction == PropDirection.OVER:
            # We expect MORE saves than line (high event game)
            edge_saves = expected_saves - book_line
            # Convert saves edge to probability (each save = ~3% edge)
            probability = cls._calibrate_probability(0.50 + edge_saves * 0.03)
        else:  # UNDER
            # We expect FEWER saves than line (low event game)
            edge_saves = book_line - expected_saves
            # Convert saves edge to probability (each save = ~3% edge)
            probability = cls._calibrate_probability(0.50 + edge_saves * 0.03)

        if probability < Config.MIN_CONFIDENCE:
            return None

        edge_pp = (probability - 0.524) * 100  # Edge vs breakeven

        alignment = "Strong" if env.confidence > 0.65 else "Moderate"

        return PlayerProp(
            player_name=goalie.name,
            team=goalie.team,
            market="Saves",
            line=book_line,
            direction=direction,
            expected_value=expected_saves,
            book_implied=book_line,
            edge_pp=edge_pp,
            probability=probability,
            environment=env.environment,
            alignment_score=env.confidence,
            rationale=f"{alignment} {env.environment.value}: Exp {expected_saves:.1f} saves",
            correlation_group=f"{goalie.team}_goalie"
        )

    @classmethod
    def _generate_sog_props(cls, game: Game, env: EnvironmentPrediction) -> List[PlayerProp]:
        """Generate SOG props for key players aligned with environment."""
        props = []

        direction = env.sog_direction
        if direction == PropDirection.NO_PLAY:
            return []

        # Get players from both teams
        for team in [game.home_team, game.away_team]:
            team_players = cls.KEY_PLAYERS.get(team.code, [])

            for player_data in team_players:
                prop = cls._create_sog_prop(player_data, team, env)
                if prop:
                    props.append(prop)

        return props

    @classmethod
    def _create_sog_prop(
        cls,
        player_data: Dict,
        team: TeamProfile,
        env: EnvironmentPrediction
    ) -> Optional[PlayerProp]:
        """Create a SOG prop for a player.

        v5.2: Uses player-specific line value from backtest analysis.
        """
        direction = env.sog_direction
        name = player_data["name"]
        avg_sog = player_data["sog"]
        toi = player_data["toi"]

        if avg_sog < Config.MIN_SOG_AVG:
            return None

        # Get player-specific line value (positive = line inflated = Under value)
        player_value = cls.PLAYER_LINE_VALUE.get(name, 0.0)

        # Skip players with negative value for Unders (they beat their lines)
        if direction == PropDirection.UNDER and player_value < -0.08:
            return None  # Don't bet Unders on players who consistently go Over

        # Skip players with positive value for Overs
        if direction == PropDirection.OVER and player_value > 0.10:
            return None  # Don't bet Overs on players who consistently go Under

        # Adjust expected SOG by environment
        env_multiplier = 1.0
        if env.environment == GameEnvironment.HIGH_EVENT:
            env_multiplier = 1.10  # +10% in high event
        elif env.environment == GameEnvironment.LOW_EVENT:
            env_multiplier = 0.90  # -10% in low event

        expected_sog = avg_sog * env_multiplier

        # Estimate book line
        book_line = round(avg_sog - 0.3, 0) + 0.5  # Books typically shade slightly under

        # Calculate edge based on direction, incorporating player value
        if direction == PropDirection.OVER:
            edge = expected_sog - book_line
            base_prob = 0.50 + edge / 3 - player_value  # Reduce for high Under-value players
            probability = cls._calibrate_probability(base_prob)
        else:  # UNDER
            edge = book_line - expected_sog
            base_prob = 0.50 + edge / 3 + player_value  # Boost for high Under-value players
            probability = cls._calibrate_probability(base_prob)

        if probability < Config.MIN_CONFIDENCE:
            return None

        edge_pp = (probability - 0.524) * 100

        alignment = "Strong" if env.confidence > 0.65 else "Moderate"
        value_note = f" [+value]" if player_value > 0.10 else ""

        return PlayerProp(
            player_name=name,
            team=team.code,
            market="SOG",
            line=book_line,
            direction=direction,
            expected_value=expected_sog,
            book_implied=book_line,
            edge_pp=edge_pp,
            probability=probability,
            environment=env.environment,
            alignment_score=env.confidence,
            rationale=f"{alignment} {env.environment.value}: {name} exp {expected_sog:.1f} SOG{value_note}",
            correlation_group=f"{team.code}_skaters"
        )

    @staticmethod
    def _calibrate_probability(raw_prob: float) -> float:
        """
        Calibrate raw probability using shrinkage toward 0.5.

        From v4 backtest: model was wildly overconfident.
        Apply shrinkage to bring extreme probabilities closer to reality.
        """
        # Shrink toward 0.5
        calibrated = 0.5 + (raw_prob - 0.5) * (1 - Config.CALIBRATION_SHRINKAGE)
        return max(0.40, min(0.70, calibrated))  # Cap at 40-70%


# =============================================================================
# PARLAY BUILDER - Build correlated parlays
# =============================================================================

class ParlayBuilder:
    """
    Build parlays with positive correlation.

    Key insight: All legs should benefit from the SAME game script.
    If we predict HIGH-EVENT, pair:
    - SOG Overs (more shooting)
    - Saves Overs (more shots faced)
    - Points Overs (more scoring)

    These are positively correlated - they all win together when the
    game script plays out as predicted.
    """

    @classmethod
    def build_parlays(cls, game: Game) -> List[Parlay]:
        """Build correlated parlays for a game."""
        if not game.environment or not game.props:
            return []

        parlays = []
        env = game.environment

        # Only build parlays for non-neutral games with enough props
        if env.environment == GameEnvironment.NEUTRAL:
            return []

        if len(game.props) < 2:
            return []

        # Group props by type
        saves_props = [p for p in game.props if p.market == "Saves"]
        sog_props = [p for p in game.props if p.market == "SOG"]

        # Build "Same Script" parlay: 1 goalie + 2-3 skaters
        if saves_props and len(sog_props) >= 2:
            parlay = cls._build_same_script_parlay(
                game, saves_props[0], sog_props[:3], env
            )
            if parlay:
                parlays.append(parlay)

        # Build "Skater Stack" parlay: 3-4 SOG props
        if len(sog_props) >= 3:
            parlay = cls._build_skater_stack(game, sog_props[:4], env)
            if parlay:
                parlays.append(parlay)

        return parlays

    @classmethod
    def _build_same_script_parlay(
        cls,
        game: Game,
        goalie_prop: PlayerProp,
        sog_props: List[PlayerProp],
        env: EnvironmentPrediction
    ) -> Optional[Parlay]:
        """Build parlay with goalie + skaters on same script."""

        legs = [goalie_prop] + sog_props

        # Calculate joint probability with correlation boost
        # These legs are positively correlated - they win together
        base_joint = 1.0
        for leg in legs:
            base_joint *= leg.probability

        # Apply correlation boost (same script = positive correlation)
        correlation_boost = 1.15  # +15% for positive correlation
        joint_prob = min(0.50, base_joint * correlation_boost)

        # Estimate payout (simplified)
        # 3-leg at ~6:1, 4-leg at ~10:1
        if len(legs) == 3:
            payout_multiplier = 6.0
        elif len(legs) == 4:
            payout_multiplier = 10.0
        else:
            payout_multiplier = 4.0

        implied_prob = 1 / payout_multiplier
        edge = (joint_prob - implied_prob) / implied_prob * 100

        return Parlay(
            parlay_id=f"{game.game_id}_script_{len(legs)}",
            game_id=game.game_id,
            legs=legs,
            environment=env.environment,
            correlation_type="Same-Script",
            joint_probability=joint_prob,
            expected_payout=payout_multiplier,
            edge=edge,
            rationale=f"{env.environment.value} Script: All legs benefit from {'high' if env.environment == GameEnvironment.HIGH_EVENT else 'low'} event game"
        )

    @classmethod
    def _build_skater_stack(
        cls,
        game: Game,
        sog_props: List[PlayerProp],
        env: EnvironmentPrediction
    ) -> Optional[Parlay]:
        """Build parlay with multiple SOG props."""

        legs = sog_props

        # Calculate joint probability
        base_joint = 1.0
        for leg in legs:
            base_joint *= leg.probability

        # Moderate correlation boost for same-market stack
        correlation_boost = 1.10
        joint_prob = min(0.45, base_joint * correlation_boost)

        payout_multiplier = 2.0 ** len(legs)
        implied_prob = 1 / payout_multiplier
        edge = (joint_prob - implied_prob) / implied_prob * 100

        return Parlay(
            parlay_id=f"{game.game_id}_sog_stack_{len(legs)}",
            game_id=game.game_id,
            legs=legs,
            environment=env.environment,
            correlation_type="SOG-Stack",
            joint_probability=joint_prob,
            expected_payout=payout_multiplier,
            edge=edge,
            rationale=f"SOG Stack: All players benefit from {env.environment.value} pace"
        )


# =============================================================================
# MAIN MODEL
# =============================================================================

class NHLModel_v5:
    """
    NHL Player-Prop Model v5.0.0

    Environment-First Architecture:
    1. Predict game environment (high-event vs low-event)
    2. Select player props aligned with environment
    3. Build correlated parlays that ride the same wave
    """

    VERSION = "5.3.2"
    NAME = "Clodbought"

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.games: List[Game] = []

    def analyze_slate(self, date_str: str) -> Tuple[List[Game], List[Parlay]]:
        """
        Analyze all games for a date.

        Returns:
            Tuple of (games with environment predictions, recommended parlays)
        """
        print(f"\n{'='*70}")
        print(f"{self.NAME} NHL Model v{self.VERSION} (Environment-First) - Analyzing {date_str}")
        print(f"{'='*70}")

        # Reset caches
        TeamDatabase.reset()
        NHLAPIClient.reset_cache()
        self.games = []

        # Load team data
        print("\nLoading team data...")
        TeamDatabase.load()

        # Fetch games
        print("Fetching games...")
        api_games = NHLAPIClient.get_schedule(date_str)

        if not api_games:
            print("No games found.")
            return [], []

        print(f"Found {len(api_games)} games\n")

        all_parlays = []

        # Process each game
        for api_game in api_games:
            game = self._process_game(api_game, date_str)
            if game:
                self.games.append(game)

                # Build parlays for this game
                parlays = ParlayBuilder.build_parlays(game)
                all_parlays.extend(parlays)

        # Print summary
        self._print_summary(all_parlays)

        return self.games, all_parlays

    def _process_game(self, api_game: Dict, date_str: str) -> Optional[Game]:
        """Process a single game."""
        try:
            home_code = api_game['homeTeam']['abbrev']
            away_code = api_game['awayTeam']['abbrev']

            home_team = TeamDatabase.get_team(home_code)
            away_team = TeamDatabase.get_team(away_code)

            home_team.is_home = True

            # Create game
            game = Game(
                game_id=str(api_game.get('id', '')),
                date=datetime.datetime.strptime(date_str, "%Y-%m-%d").date(),
                time=api_game.get('startTimeUTC', ''),
                home_team=home_team,
                away_team=away_team
            )

            # Predict environment
            env = EnvironmentPredictor.predict(home_team, away_team)
            game.environment = env

            # Generate props
            props = PropGenerator.generate_props(game)
            game.props = props

            # Print game analysis
            if self.verbose:
                self._print_game_analysis(game)

            return game

        except Exception as e:
            print(f"Error processing game: {e}")
            return None

    def _print_game_analysis(self, game: Game):
        """Print analysis for a single game."""
        env = game.environment
        if not env:
            return

        print(f"\n{'-'*70}")
        print(f"{game.away_team.code} @ {game.home_team.code}")
        print(f"{'-'*70}")

        # Environment prediction
        conf_stars = int(env.confidence * 5)
        print(f"\nENVIRONMENT: {env.environment.value} ({'*' * conf_stars})")
        print(f"Confidence: {env.confidence:.1%}")
        print(f"Score: High-Event {env.high_event_score:.0f} / Low-Event {env.low_event_score:.0f}")

        print(f"\nKEY FACTORS:")
        for factor in env.factors[:5]:
            print(f"  - {factor}")

        print(f"\nPROJECTIONS:")
        print(f"  Total Goals: {env.expected_total_goals:.1f}")
        print(f"  Total SOG: {env.expected_total_sog:.1f}")
        print(f"  Home Saves: {env.expected_home_saves:.1f}")
        print(f"  Away Saves: {env.expected_away_saves:.1f}")

        print(f"\nRECOMMENDED DIRECTION:")
        print(f"  SOG: {env.sog_direction.value}")
        print(f"  Saves: {env.saves_direction.value}")
        print(f"  Goals: {env.goals_direction.value}")

        if game.props:
            print(f"\nALIGNED PROPS ({len(game.props)}):")
            for prop in game.props[:6]:
                print(f"  {prop.player_name} {prop.market} {prop.direction.value} {prop.line} | "
                      f"Edge: {prop.edge_pp:+.1f}pp | Prob: {prop.probability:.1%}")

    def _print_summary(self, parlays: List[Parlay]):
        """Print slate summary."""
        print(f"\n{'='*70}")
        print("SLATE SUMMARY")
        print(f"{'='*70}")

        # Environment breakdown
        high_event = sum(1 for g in self.games if g.environment and g.environment.environment == GameEnvironment.HIGH_EVENT)
        low_event = sum(1 for g in self.games if g.environment and g.environment.environment == GameEnvironment.LOW_EVENT)
        neutral = len(self.games) - high_event - low_event

        print(f"\nGAME ENVIRONMENTS:")
        print(f"  High-Event: {high_event}")
        print(f"  Low-Event: {low_event}")
        print(f"  Neutral (No Play): {neutral}")

        # Parlay recommendations
        if parlays:
            print(f"\nRECOMMENDED PARLAYS ({len(parlays)}):")
            for parlay in parlays[:5]:
                print(f"\n  {parlay.parlay_id}")
                print(f"  Type: {parlay.correlation_type} | Env: {parlay.environment.value}")
                print(f"  Legs:")
                for leg in parlay.legs:
                    print(f"    - {leg.player_name} {leg.market} {leg.direction.value} {leg.line}")
                print(f"  Joint Prob: {parlay.joint_probability:.1%} | Edge: {parlay.edge:+.1f}%")
                print(f"  Rationale: {parlay.rationale}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Clodbought NHL Model v5.3.2 (Environment-First)")
    parser.add_argument("--date", type=str,
                       default=datetime.date.today().strftime("%Y-%m-%d"),
                       help="Date to analyze (YYYY-MM-DD)")
    parser.add_argument("--quiet", action="store_true", help="Reduce output")
    args = parser.parse_args()

    model = NHLModel_v5(verbose=not args.quiet)
    games, parlays = model.analyze_slate(args.date)

    print(f"\n{'='*70}")
    print(f"Analysis complete. {len(games)} games, {len(parlays)} parlays.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
