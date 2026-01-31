#!/usr/bin/env python3
"""
CLODBOUGHT MODEL v5.3.2 - TRUE OUT-OF-SAMPLE VALIDATION

Protocol:
1. Model is FROZEN - no changes allowed after seeing results
2. Test period: Jan 5-14, 2025 (BEFORE our tuning period of Jan 15-28)
3. Report EVERY day, including bad ones
4. No cherry-picking or excuses
5. Calculate honest statistics with confidence intervals
"""

import subprocess
import sys
import re
from datetime import datetime, timedelta
import statistics
import math

# Out-of-sample period - dates we NEVER used for tuning
TEST_START = "2025-01-05"
TEST_END = "2025-01-14"

def run_backtest(start, end):
    """Run the blind backtest and capture output."""
    cmd = f"python3 /home/paul/Downloads/nhl_blind_backtest.py --start {start} --end {end}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    return result.stdout + result.stderr

def parse_daily_results(output):
    """Parse daily results from backtest output."""
    daily = []
    
    # Find all "RESULTS: X/Y" patterns
    pattern = r"DATE: (\d{4}-\d{2}-\d{2}).*?RESULTS: (\d+)/(\d+) \((\d+\.?\d*)%\)"
    matches = re.findall(pattern, output, re.DOTALL)
    
    for match in matches:
        date, hits, total, pct = match
        daily.append({
            'date': date,
            'hits': int(hits),
            'total': int(total),
            'pct': float(pct)
        })
    
    return daily

def parse_overall(output):
    """Parse overall results."""
    pattern = r"OVERALL: (\d+)/(\d+) \((\d+\.?\d*)%\)"
    match = re.search(pattern, output)
    if match:
        return int(match.group(1)), int(match.group(2)), float(match.group(3))
    return 0, 0, 0

def parse_pattern_results(output):
    """Parse pattern analysis results."""
    patterns = {}
    
    # SOG Under
    match = re.search(r"SOG Under\s*:\s*(\d+)/(\d+)\s*\((\d+\.?\d*)%\)", output)
    if match:
        patterns['sog_under'] = (int(match.group(1)), int(match.group(2)), float(match.group(3)))
    
    # Saves Under
    match = re.search(r"Saves Under\s*:\s*(\d+)/(\d+)\s*\((\d+\.?\d*)%\)", output)
    if match:
        patterns['saves_under'] = (int(match.group(1)), int(match.group(2)), float(match.group(3)))
    
    # High value players
    match = re.search(r"High Under Value.*?:\s*(\d+)/(\d+)\s*\((\d+\.?\d*)%\)", output)
    if match:
        patterns['high_value'] = (int(match.group(1)), int(match.group(2)), float(match.group(3)))
    
    # Low shot games
    match = re.search(r"Low-Shot.*?:\s*(\d+)/(\d+)\s*\((\d+\.?\d*)%\)", output)
    if match:
        patterns['low_shot'] = (int(match.group(1)), int(match.group(2)), float(match.group(3)))
    
    return patterns

def wilson_confidence_interval(hits, total, confidence=0.95):
    """Calculate Wilson score confidence interval."""
    if total == 0:
        return 0, 0, 0
    
    z = 1.96  # 95% confidence
    p = hits / total
    
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    spread = z * math.sqrt((p * (1-p) + z**2 / (4 * total)) / total) / denominator
    
    lower = max(0, center - spread)
    upper = min(1, center + spread)
    
    return p, lower, upper

def calculate_roi(hits, total, odds=-110):
    """Calculate ROI at given odds."""
    if total == 0:
        return 0
    
    win_payout = 100 / abs(odds) if odds < 0 else odds / 100
    losses = total - hits
    
    profit = hits * win_payout - losses
    roi = profit / total * 100
    return roi

print("=" * 80)
print("CLODBOUGHT v5.3.2 - TRUE OUT-OF-SAMPLE VALIDATION")
print("=" * 80)
print(f"""
PROTOCOL:
  • Model FROZEN at v5.3.2 (no changes after seeing results)
  • Test Period: {TEST_START} to {TEST_END}
  • This period was NEVER used for tuning or validation
  • ALL results reported (no cherry-picking)
  • Statistical confidence intervals calculated
""")
print("=" * 80)
print("\nRunning blind backtest on frozen model...")
print("(This will take a minute...)\n")

# Run the backtest
output = run_backtest(TEST_START, TEST_END)

# Parse results
daily_results = parse_daily_results(output)
overall_hits, overall_total, overall_pct = parse_overall(output)
patterns = parse_pattern_results(output)

print("=" * 80)
print("DAILY RESULTS (NO CHERRY-PICKING)")
print("=" * 80)
print(f"\n{'Date':<12} {'Result':<10} {'Hit Rate':<10} {'Grade'}")
print("-" * 50)

grades = []
for day in daily_results:
    pct = day['pct']
    if pct >= 70:
        grade = "🟢 GREAT"
    elif pct >= 60:
        grade = "🟡 GOOD"
    elif pct >= 52.4:
        grade = "🟠 PROFIT"
    else:
        grade = "🔴 LOSS"
    
    grades.append(pct)
    print(f"{day['date']:<12} {day['hits']}/{day['total']:<7} {pct:>5.1f}%     {grade}")

print("-" * 50)

# Calculate statistics
if grades:
    mean_pct = statistics.mean(grades)
    if len(grades) > 1:
        std_pct = statistics.stdev(grades)
    else:
        std_pct = 0
    min_pct = min(grades)
    max_pct = max(grades)
    
    # Winning days (>52.4%)
    winning_days = sum(1 for g in grades if g > 52.4)
    
    print(f"\nDaily Statistics:")
    print(f"  Mean:     {mean_pct:.1f}%")
    print(f"  Std Dev:  {std_pct:.1f}%")
    print(f"  Range:    {min_pct:.1f}% - {max_pct:.1f}%")
    print(f"  Winning Days: {winning_days}/{len(grades)}")

print("\n" + "=" * 80)
print("OVERALL RESULTS")
print("=" * 80)

# Wilson confidence interval
p, lower, upper = wilson_confidence_interval(overall_hits, overall_total)
roi = calculate_roi(overall_hits, overall_total)

print(f"""
┌─────────────────────────────────────────────────────────────┐
│  PICKS: {overall_hits}/{overall_total}                                            
│  HIT RATE: {overall_pct:.1f}%                                        
│                                                             
│  95% CONFIDENCE INTERVAL: {lower*100:.1f}% - {upper*100:.1f}%              
│  ROI AT -110: {roi:+.1f}%                                       
└─────────────────────────────────────────────────────────────┘
""")

# Breakeven comparison
breakeven = 52.4
print(f"Breakeven at -110: {breakeven}%")
print(f"Model Performance: {overall_pct:.1f}%")
print(f"Edge vs Breakeven: {overall_pct - breakeven:+.1f}pp")

if lower > breakeven:
    print("\n✅ STATISTICALLY SIGNIFICANT: Lower bound exceeds breakeven")
elif p > breakeven:
    print("\n⚠️ PROFITABLE BUT NOT SIGNIFICANT: Point estimate beats breakeven, but CI includes breakeven")
else:
    print("\n❌ NOT PROFITABLE: Does not beat breakeven")

print("\n" + "=" * 80)
print("PATTERN VALIDATION")
print("=" * 80)

print("\nKey Claims vs Out-of-Sample Reality:")
print("-" * 60)

claims = [
    ("SOG Unders", "sog_under", "70.5%"),
    ("Saves Unders", "saves_under", "63.2%"),
    ("High Value Players", "high_value", "86.4%"),
    ("Low-Shot Games", "low_shot", "83.7%"),
]

for name, key, claimed in claims:
    if key in patterns:
        hits, total, pct = patterns[key]
        p, lower, upper = wilson_confidence_interval(hits, total)
        diff = pct - float(claimed.strip('%'))
        
        if diff >= 0:
            status = "✅"
        elif diff > -10:
            status = "⚠️"
        else:
            status = "❌"
        
        print(f"  {name}:")
        print(f"    Claimed: {claimed}")
        print(f"    Actual:  {pct:.1f}% ({hits}/{total}) {status}")
        print(f"    95% CI:  {lower*100:.1f}% - {upper*100:.1f}%")
        print()

print("=" * 80)
print("HONEST ASSESSMENT")
print("=" * 80)

# Final verdict
if overall_pct >= 65 and lower > 55:
    verdict = "MODEL VALIDATED - Performance holds out-of-sample"
    grade = "A"
elif overall_pct >= 58 and lower > 50:
    verdict = "MODEL PARTIALLY VALIDATED - Edge exists but smaller than claimed"
    grade = "B"
elif overall_pct > 52.4:
    verdict = "MARGINAL - Slight edge, results inflated in-sample"
    grade = "C"
else:
    verdict = "MODEL FAILED - No edge detected out-of-sample"
    grade = "F"

print(f"""
FINAL VERDICT: {verdict}

GRADE: {grade}

Comparison to In-Sample Claims:
  • Claimed overall: 67.7%
  • Out-of-sample:   {overall_pct:.1f}%
  • Difference:      {overall_pct - 67.7:+.1f}pp

If out-of-sample is significantly lower than in-sample,
this confirms overfitting to the training period.
""")

print("=" * 80)
print("RAW OUTPUT (for verification)")
print("=" * 80)
# Print last part of output for transparency
lines = output.strip().split('\n')
for line in lines[-50:]:
    print(line)

