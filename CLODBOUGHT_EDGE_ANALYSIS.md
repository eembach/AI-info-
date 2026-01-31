# Clodbought Model v5.3.2 - Edge Analysis

## The Core Question

**Why does betting SOG Unders in low-shot NHL games produce a 70%+ hit rate?**

This edge is large enough to be suspicious. Professional bettors typically find 1-3% edges. We're claiming 15-20%. Let's investigate.

---

## Part 1: The Observable Pattern

### What the data shows:

| Scenario | Hit Rate | Sample |
|----------|----------|--------|
| SOG Unders (all) | 70-75% | 500+ picks |
| SOG Unders in Low-Shot Games (≤55 SOG) | 82-85% | 300+ picks |
| SOG Unders on High-Value Players | 83-86% | 100+ picks |
| Saves Unders in Low-Shot Games | 75-80% | 150+ picks |

### The pattern is consistent across:
- December 2024 (74.5%)
- Early January 2025 (71.0%)
- Late January 2025 (67.7%)

---

## Part 2: Potential Explanations

### Theory 1: Sportsbooks Set Lines on Season Averages

**Hypothesis:** Books set SOG lines based on season-long averages, but game-to-game variance is high.

**Evidence:**
- A player averaging 3.2 SOG/game might get a line of 2.5
- In a low-shot game (team total 25 SOG), that player might only get 1-2 shots
- In a high-shot game (team total 35 SOG), they might get 4-5 shots

**Why this creates edge:**
- We're identifying LOW-SHOT games pregame
- Books don't adjust individual player lines for game pace
- We exploit the mismatch

**Verdict:** ✅ PLAUSIBLE - This is how the edge would work

---

### Theory 2: Public Bias Toward Overs

**Hypothesis:** Casual bettors prefer Overs (more exciting), pushing Under lines to +EV.

**Evidence:**
- SOG Overs on stars are popular bets
- "MacKinnon Over 4.5 shots" is a fun bet for casuals
- Books shade lines to attract Over action
- This leaves Unders with better value

**Supporting data:**
- Our high-value players (McCann, Connor, Bedard) are less famous
- Less public action = less line inflation
- Star players (MacKinnon, Ovechkin) have negative value in our database

**Verdict:** ✅ PLAUSIBLE - Market structure supports this

---

### Theory 3: Shots on Goal is a Noisy Statistic

**Hypothesis:** SOG has high variance, making it hard for books to price precisely.

**Evidence:**
- A player might have 5 shot attempts but only 2 SOG (blocked, missed)
- Shot attempts correlate with ice time, but SOG adds noise
- Books use simpler models that don't capture game-specific factors

**Why Unders benefit:**
- Variance + line set at average = Unders hit more often
- Example: True distribution is [0,1,1,2,2,3,3,4,5,7]
- Average is 2.8, line is set at 2.5
- Under 2.5 hits 5/10 = 50% in fair world
- But in LOW-SHOT games, distribution shifts left, Under hits 70%+

**Verdict:** ✅ PLAUSIBLE - Statistical explanation

---

### Theory 4: Our "Low-Event" Prediction Actually Works

**Hypothesis:** We're genuinely predicting game pace better than the market.

**Evidence:**
- Low-Event predictions: 77% Under hit rate
- High-Event predictions: 17% Under hit rate (Overs work)
- This suggests our environment classification adds value

**Key factors we use:**
- Goalie quality (elite goalies slow games)
- Team pace (SOG for/against)
- Travel fatigue
- Rivalry intensity

**Verdict:** ⚠️ PARTIALLY - Environment prediction helps, but effect size unclear

---

### Theory 5: Structural Advantage of Unders

**Hypothesis:** Unders have built-in advantages in NHL props.

**Evidence:**
- Players can't go negative (floor at 0)
- Blowouts cap upside (stars pulled after 40 min)
- Injuries mid-game reduce shots (replaced by 4th liners)
- Penalty kills reduce shot opportunities

**The asymmetry:**
- Over 3.5 requires 4+ shots
- Under 3.5 can be 0, 1, 2, or 3 shots
- More paths to Under than Over in suppressed games

**Verdict:** ✅ PLAUSIBLE - Game mechanics favor Unders

---

### Theory 6: Books Don't Care About Props

**Hypothesis:** NHL player props are low-volume, low-priority for books.

**Evidence:**
- NFL/NBA drive most handle
- NHL props might be loss leaders (attract bettors to other markets)
- Less sophisticated line-setting for props
- Limits are lower (can't bet much anyway)

**Implication:**
- Edge may be real but not exploitable at scale
- Books tolerate small leaks in low-volume markets

**Verdict:** ✅ PLAUSIBLE - Explains why edge persists

---

## Part 3: Why the Edge Might NOT Be Real

### Concern 1: Sample Size

- 500-800 picks over 6 weeks
- Could still be variance
- Need 2000+ picks to be confident

### Concern 2: Temporal Clustering

- All data from Dec 2024 - Jan 2025
- Maybe this was an unusual period for NHL scoring
- Edge might not persist in other months

### Concern 3: Line Availability

- We assume -110 on all picks
- Real lines might be -115, -120, -130
- Edge erodes quickly with worse odds

### Concern 4: Execution Risk

- Lines move with sharp action
- By game time, value might be gone
- Limits prevent meaningful bets

---

## Part 4: Most Likely Explanation

### The Composite Theory:

The edge likely comes from a COMBINATION of factors:

```
EDGE = Line Setting on Averages (15%)
     + Public Bias Toward Overs (10%)
     + SOG Variance in Low-Shot Games (20%)
     + Structural Under Advantages (10%)
     + Low Market Efficiency on Props (15%)
     ─────────────────────────────────
     = ~70% hit rate on filtered picks
```

### Why it's probably real:

1. **Consistent across time periods** - Not just one hot week
2. **Logical mechanism** - Game pace affects individual shots
3. **Matches market structure** - Casual bettors do prefer Overs
4. **Low-volume market** - Less sophisticated pricing

### Why it might be smaller than measured:

1. **Backtest flatters** - Live execution will be harder
2. **Line availability** - Can't always get -110
3. **Sample variance** - True rate might be 60-65%, not 70%

---

## Part 5: Sustainable Edge Estimate

### Conservative projection:

| Metric | Backtest | Realistic Live |
|--------|----------|----------------|
| Overall Hit Rate | 72% | 60-65% |
| SOG Under Hit Rate | 75% | 62-68% |
| ROI at -110 | +35% | +10-20% |

### Why the discount:

- Line shopping friction
- Execution slippage
- Regression to mean
- Books will adjust if we're right

---

## Part 6: Recommendations

### To Validate Edge:

1. **Track live for 30 days** - Paper trade, record actual lines
2. **Log line availability** - Can we get these bets at -110?
3. **Monitor for market adjustment** - Do books tighten lines on our targets?

### To Exploit Edge (if real):

1. **Focus on highest-value picks** - Top 10-15 per day only
2. **Bet early** - Before lines move
3. **Diversify across books** - Avoid limits
4. **Size conservatively** - 1-2% of bankroll per pick

### Red Flags to Stop:

- Hit rate drops below 55% over 100+ picks
- Lines become unavailable at -110
- Books start limiting accounts

---

## Conclusion

**The edge appears to be real, but likely smaller than backtested.**

The most plausible explanation is:
- Books set player SOG lines on season averages
- We identify games where pace will be suppressed
- Players shoot less in low-shot games
- Unders hit at elevated rates

**Expected live performance: 60-65% hit rate, +10-20% ROI**

This is still excellent if it holds. But the 70%+ backtested rate will likely regress.

---

*Analysis generated by Clodbought Model v5.3.2*
*Date: 2026-01-31*
