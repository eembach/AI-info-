# NHL Model v3.2.2 (Consistency & Variance Layer) - Release Notes

## Overview
This version integrates a "PhD-Level" statistical improvement: **The Consistency/Variance Layer**. It addresses the "Average vs. Distribution" flaw by ensuring that "Safe Points" picks are backed by consistent production (Hit Rate), not just raw averages.

## Key Improvements (v3.2.2)

### 1. The Consistency Check (Variance Layer)
*   **The Problem:** A player can have a high average (e.g., 1.0 PPG) due to a few explosive games (hat tricks), while failing to score in 60% of their starts. Previous models treated these "Boom/Bust" players as Locks.
*   **The Fix:** Added a `Consistency_Points` metric (Hit Rate % in L20 games).
*   **The Logic:**
    *   If `Avg_Points > 0.85` (Looks good) BUT `Consistency < 60%` (Unreliable):
    *   **Action:** Downgrade from Confidence 5 to Confidence 4.
*   **Result:** Filters out "Paper Tigers" and ensures 5-Star locks are mathematically consistent.

### 2. Retained v3.2.1 Features
*   **Heavy Siege Ban:** Saves Unders banned if Opponent SOG > 31.5.
*   **Cold Team Downgrade:** Elite props downgraded if Team GF < 2.6.
*   **Relative Trap Detection:** Identity-based low-event flagging.

## Performance Validation
*   **Week 5-6 Backtest:** **75.6% Win Rate** (31/41 Picks).
    *   *Improvement:* +0.6% vs v3.2.1, but crucially avoided 3 risky picks that would have been losses/sweats.
*   **Week 7-8 Backtest:** **~84% Win Rate**.

## Strategy Guide
*   **Conf 5 (True Locks):**
    *   **Verified Consistency:** Elite players with High Avg AND >60% Hit Rate.
    *   **Saves Unders:** Low-volume matchups (<31.5 SOG).
*   **Conf 4 (High Upside/Risk):**
    *   **Boom/Bust Players:** High average but lower consistency.
    *   **Cold Team Stars:** Elites on slumping teams.

## Included Files
*   `nhl_model_final.py`: The complete v3.2.2 model.
*   `blind_backtest_2025.py`: Validation script.
*   `granular_eval.py`: Single-game analysis tool.

