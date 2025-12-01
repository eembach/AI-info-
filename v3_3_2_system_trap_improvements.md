# v3.3.2 System Trap Scenario Refinement

## Overview
Based on analysis of System Trap games from Nov 30, 2025 backtest, identified key issues:
1. **3 out of 4 System Trap games had high scoring** (5, 8, 7 goals) despite low SOG volume
2. **Scenario conflicts**: Games tagged as both "System Trap" and "Barnburner (Goals)"
3. **Misclassification**: True low-event games vs efficiency-based games not distinguished

## Key Findings

### Outcome Patterns
- **True Low Event**: 1 game (CGY@CAR: 32 SOG, 1 goal) ✅
- **Low SOG, High Goals**: 3 games (Efficiency Trap pattern)
  - WSH@NYI: 49 SOG, 5 Goals
  - ANA@CHI: 44 SOG, 8 Goals  
  - OTT@DAL: 42 SOG, 7 Goals

### Problem
Games with low SOG volume but high shooting percentage were being classified as "System Trap" (implying Under), but actually produced high scoring (Over). This created scenario conflicts and incorrect lean predictions.

## Improvements Implemented

### 1. Efficiency Trap Scenario (NEW)
**Detection Criteria:**
- Low SOG volume (< 28 SOG/game)
- High shooting percentage (> 11%)
- Low goals against (< 2.8 GA/game) - implied

**Key Difference from System Trap:**
- **System Trap (Volume)**: Low SOG + Low Goals = True low-event game → Under lean
- **Efficiency Trap**: Low SOG + High Shooting % = Can still score goals → No Under lean

**Code:**
```python
# Calculate shooting percentages
home_shooting_pct = (game.home_team.goals_for_per_game / game.home_team.avg_sog_for * 100)
away_shooting_pct = (game.away_team.goals_for_per_game / game.away_team.avg_sog_for * 100)

# Check if it's an Efficiency Trap
if home_shooting_pct > 11.0 and game.home_team.avg_sog_for < 28.0:
    scenarios.append("Efficiency Trap (Home)")  # Low volume, high efficiency
else:
    scenarios.append("System Trap (Home)")  # True low-event team
```

### 2. Scenario Conflict Resolution
**Problem:** Games could be both "System Trap" and "Barnburner (Goals)"

**Solution:**
- Volume traps cannot be Barnburner (Volume) - conflict resolved
- Efficiency traps CAN be Barnburner (Goals) - high shooting % can produce high scoring
- Only true volume traps get "Under" lean

**Code:**
```python
# Conflict Resolution
is_efficiency_trap = "Efficiency Trap" in str(scenarios)
is_volume_trap = "System Trap" in str(scenarios) and not is_efficiency_trap

if proj_total_goals > 6.6: 
    scenarios.append("Barnburner (Goals)")
    if not is_volume_trap:  # Only set Over lean if not a volume trap
        lean["total"] = "Over"
```

### 3. Refined Trap Game Logic
**Before:** All trap games got "Under" lean
**After:** Only volume traps get "Under" lean; efficiency traps can go either way

**Code:**
```python
if is_volume_trap:
    is_trap_game = True
    lean["total"] = "Under"  # Volume traps = Under
elif is_efficiency_trap_only:
    is_trap_game = True
    # Efficiency traps can go Over (high shooting %), so don't set Under lean
```

### 4. Pick Generation Refinements

#### Defensemen Gate
- **Before:** Skip defensemen Points Over 0.5 in ALL trap games
- **After:** Only skip in volume traps, not efficiency traps (efficiency traps have high shooting % = good for points)

#### Points Under 1.5 Logic
- **Before:** All trap games considered "tough matchup"
- **After:** Only volume traps are "tough matchup"; efficiency traps are NOT (high shooting % = more goals)

**Code:**
```python
# Only volume traps are tough for Under 1.5
is_volume_trap = "System Trap" in str(scenarios) and "Efficiency Trap" not in str(scenarios)
is_tough_matchup = opponent.goals_against_per_game < 2.9 or is_volume_trap
```

## Expected Impact

### Scenario Accuracy
- **Before:** 2/4 games had wrong lean (Under predicted, Over actual)
- **After:** Efficiency Trap games won't get Under lean, improving accuracy

### Pick Quality
- **Defensemen:** Can now get Points Over 0.5 in efficiency traps (high shooting % = good for points)
- **Points Under 1.5:** Only boosted confidence in true volume traps, not efficiency traps

### Scenario Clarity
- Clear distinction between volume-based low-event games vs efficiency-based games
- Eliminates scenario conflicts (System Trap + Barnburner)

## Testing Recommendations

1. **Re-run Nov 30 backtest** to verify:
   - Efficiency Trap games correctly identified
   - Lean predictions improved
   - No scenario conflicts

2. **Large-scale backtest** to verify:
   - Efficiency Trap detection accuracy
   - Pick quality improvements
   - Overall win rate maintained/improved

3. **Monitor shooting percentage** data to ensure thresholds are accurate

## Version
**v3.3.2** - System Trap Scenario Refinement

## Files Modified
- `nhl_model_final.py`: Added Efficiency Trap detection, conflict resolution, refined trap logic

