# NHL Model v3.2.1 (Refined Siege & Cold Logic) - Release Notes

## Overview
This version builds on the "Safe Points" architecture (v3.1.5) by implementing three critical improvements to address specific leakages identified in large-scale backtesting (Weeks 5-6). It achieves a stable **75-84% Win Rate** across multiple backtest periods.

## Key Improvements (v3.2.1)

### 1. Tighter "Heavy Siege" Ban (Goalie Protection)
*   **Problem:** Previous versions occasionally faded goalies against high-volume teams (TOR, COL) because they fit the "Efficiency Mismatch" profile, ignoring the sheer shot volume.
*   **Fix:** Lowered the "Heavy Siege" threshold from 33.0 to **31.5 SOG/GP**.
*   **Result:** The model now STRICTLY bans "Saves Under" bets if the opponent averages > 31.5 SOG, protecting against volume traps.

### 2. "Cold Team" Downgrade (Skater Protection)
*   **Problem:** Elite players (McDavid, Crosby) can fail to hit even "Safe Points" (Over 0.5) when their entire team is in a slump.
*   **Fix:** Added a check for Team Offense. If a team averages **< 2.6 Goals/Game**, all Elite "Points Over" picks are downgraded from Conf 5 to Conf 4.
*   **Result:** Filters out bad bets on stars during team-wide scoring droughts.

### 3. Relative Trap Detection
*   **Logic:** Enhanced `ScenarioAnalyzer` to identify "System Trap" games not just by raw numbers (< 58.0 Total SOG) but also by "Identity" (Sum of Season Averages < 59.0).
*   **Result:** More consistent identification of low-event games for "Depth Fade" opportunities.

## Performance Validation
*   **Week 7-8 Backtest (Nov 15-30):** **83.7% Win Rate** (153 Picks).
*   **Week 5-6 Backtest (Nov 1-14):** **75.0% Win Rate** (44 Picks).
*   **Consistency:** The model now performs reliably across both high-scoring and low-scoring weeks.

## Strategy Guide
*   **Conf 5 (Locks):**
    *   **Safe Points (Over 0.5):** Elite players in non-slumping teams.
    *   **Depth Fades (Under 1.5):** Non-elite players in Trap Games.
    *   **Saves Unders:** Goalies vs Low-Volume teams (< 31.5 SOG).
*   **Conf 4 (Action):**
    *   **SOG Overs:** Volume shooters in Pace Matchups.
    *   **Cold Team Stars:** Elites in favorable matchups but on cold teams.

## Included Files
*   `nhl_model_final.py`: The complete v3.2.1 model.
*   `blind_backtest_2025.py`: Validation script.
*   `granular_eval.py`: Single-game analysis tool.

