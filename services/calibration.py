"""
Calibration constants per sport. Tunable after backtesting.
"""

SPREAD_SIGMA = {
    'nfl': 13.0,
    'nba': 12.0,
    'mlb': 3.0,   # runs margin
    'nhl': 1.8,
    'cfb': 16.0,
    'soccer': 1.5,
    'golf': 5.0,
}

# Weight for market-implied vs model prior for ML probability
# p_model = w * p_implied + (1-w) * p_prior
ML_MARKET_WEIGHT = {
    'nfl': 0.85,
    'nba': 0.88,
    'mlb': 0.90,
    'nhl': 0.90,
    'cfb': 0.80,
    'soccer': 0.92,
    'golf': 0.95,
}

# Slope for converting team_strength delta to prior probability via logistic
ML_STRENGTH_SLOPE = {
    'nfl': 3.0,
    'nba': 2.5,
    'mlb': 1.5,
    'nhl': 1.5,
    'cfb': 3.0,
    'soccer': 1.2,
    'golf': 0.5,
}

