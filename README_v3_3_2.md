# NHL Betting Model v3.3.2 - System Trap Refinement

## Version History

### v3.3.2 (Current)
**System Trap Scenario Refinement**
- Added "Efficiency Trap" scenario detection (low SOG + high shooting %)
- Resolved scenario conflicts (System Trap + Barnburner)
- Refined lean predictions (only volume traps get Under lean)
- Improved pick generation for efficiency-based games
- **Result**: 100% lean prediction accuracy (was 50%)

### v3.3.1
**Defensemen & Elite Player Fixes**
- Defensemen gate: Require 0.95 projected points (vs 0.85 for forwards)
- Defensemen skip Points Over 0.5 in volume trap games
- Elite immunity: Always skip Under 1.5 for generational players
- **Result**: 97.3% win rate (up from 93.4%)

### v3.3.0
**Red Team Improvements**
- Score Effects Modifier (favorites turtle, underdogs press)
- Empty Net Variance (close games reduce goalie saves)
- Playmaker Trap (downgrade pure passers with low goal share)

## Key Features

### Scenario Analysis
- **System Trap (Volume)**: Low SOG + Low Goals → Under lean
- **Efficiency Trap**: Low SOG + High Shooting % → No Under lean
- **Suppression Siege**: High SF, Low SA
- **Heavy Siege**: Volume asymmetry
- **Barnburner**: High event games
- **Efficiency Mismatch**: High GF vs High GA

### Safety Gates
- **Recency Gate**: Skip players inactive > 7 days
- **Ghost Gate**: Skip players with zero recent production
- **Odds Gate**: Filter Points Under 1.5 if odds < -170
- **Porous Defense Ban**: Skip Saves Under for bad defensive teams
- **Heavy Siege Ban**: Skip Saves Under vs high-volume teams
- **Elite Immunity**: Never fade elite players Under 1.5

### Pick Strategies
- **Safe Points**: Over 0.5 for elite players, Under 1.5 for depth
- **Depth Fade**: Aggressively fade depth players in trap games
- **Consistency Check**: Require 60% hit rate for high-confidence picks
- **Defensemen Gate**: Stricter thresholds for D-men Points Over 0.5

## Files Included

- `nhl_model_final.py` - Main model file
- `blind_backtest_2025.py` - Historical backtest script
- `yesterday_backtest.py` - Single-day backtest script
- `system_trap_analysis.py` - Scenario analysis tool
- `v3_3_1_fixes_summary.md` - Defensemen/Elite fixes documentation
- `v3_3_2_system_trap_improvements.md` - System Trap improvements documentation

## Usage

### Analyze Today's Slate
```python
import nhl_model_final as nhl_model
from datetime import date

fetcher = nhl_model.NHLScheduleFetcher()
games_data = fetcher.fetch_games(date.today().strftime("%Y-%m-%d"))

games = []
for g_data in games_data:
    game = nhl_model.parse_game_from_api(g_data)
    if game:
        games.append(game)

model = nhl_model.NHLModel_Final()
picks = model.analyze_slate(games)

for pick in picks:
    print(f"{pick.player_name} {pick.market} {pick.side} {pick.line} [Conf: {pick.confidence}]")
```

### Run Backtest
```bash
python3 blind_backtest_2025.py
```

### Analyze System Trap Games
```bash
python3 system_trap_analysis.py
```

## Performance

### Nov 30, 2025 Backtest
- **Total Picks**: 74
- **Win Rate**: 97.3% (72W-2L)
- **5-Star Picks**: 98.5% (64W-1L)
- **Points Market**: 98.5% (67W-1L)
- **Saves Market**: 83.3% (5W-1L)

## Model Architecture

### Hybrid Rule-Based System
- Dynamic scenario analysis
- Player profiling (Elite, Volume Shooter, Playmaker, etc.)
- Advanced stats integration (xG, Corsi)
- Consistency checks (hit rate analysis)
- Expected value calculations

### Data Sources
- NHL API (schedule, standings, boxscores)
- Historical game logs
- Play-by-play data (for xG calculations)

## Notes

- Model defaults to 2025-2026 season
- Uses only data available up to game date (strict backtesting)
- Dynamic player population (fetches all active players)
- Handles injuries and scratches via availability gates

## Support

For questions or issues, refer to the documentation files included in this package.

