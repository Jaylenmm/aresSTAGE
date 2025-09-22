"""
Basic Rule-Based Prediction Engine for Sports Betting
Simple logic-based predictions with home field advantage and team analysis
"""

import random
from datetime import datetime
from typing import Dict, List, Tuple
from player_analyzer import PlayerAnalyzer

class PredictionEngine:
    """Simple rule-based prediction system"""
    
    def __init__(self):
        # Initialize player analyzer
        self.player_analyzer = PlayerAnalyzer()
        
        # Home field advantage factors by sport
        self.home_advantage = {
            'football': 3.0,    # ~3 points in NFL
            'basketball': 2.5,  # ~2.5 points in NBA
            'baseball': 0.5,    # ~0.5 runs in MLB
            'soccer': 0.3       # ~0.3 goals in soccer
        }
        
        # Team strength indicators (basic name-based assumptions)
        self.team_strength = {
            # NFL - Strong teams
            'kansas city chiefs': 0.8, 'buffalo bills': 0.7, 'dallas cowboys': 0.6,
            'philadelphia eagles': 0.6, 'miami dolphins': 0.5, 'tampa bay buccaneers': 0.5,
            'green bay packers': 0.6, 'san francisco 49ers': 0.7, 'baltimore ravens': 0.6,
            'cincinnati bengals': 0.5, 'los angeles rams': 0.5, 'denver broncos': 0.4,
            'las vegas raiders': 0.3, 'new york jets': 0.2, 'new york giants': 0.2,
            'chicago bears': 0.3, 'detroit lions': 0.4, 'minnesota vikings': 0.4,
            'atlanta falcons': 0.3, 'carolina panthers': 0.2, 'new orleans saints': 0.4,
            'houston texans': 0.3, 'indianapolis colts': 0.4, 'jacksonville jaguars': 0.3,
            'tennessee titans': 0.4, 'arizona cardinals': 0.2, 'seattle seahawks': 0.4,
            'los angeles chargers': 0.4, 'washington commanders': 0.2, 'pittsburgh steelers': 0.5,
            'cleveland browns': 0.3, 'new england patriots': 0.3,
            
            # NBA - Strong teams
            'los angeles lakers': 0.7, 'boston celtics': 0.8, 'golden state warriors': 0.6,
            'phoenix suns': 0.5, 'denver nuggets': 0.7, 'miami heat': 0.5,
            'milwaukee bucks': 0.6, 'philadelphia 76ers': 0.5, 'brooklyn nets': 0.4,
            'new york knicks': 0.4, 'chicago bulls': 0.3, 'cleveland cavaliers': 0.4,
            'detroit pistons': 0.2, 'indiana pacers': 0.3, 'atlanta hawks': 0.3,
            'charlotte hornets': 0.2, 'orlando magic': 0.3, 'washington wizards': 0.2,
            'dallas mavericks': 0.5, 'houston rockets': 0.2, 'memphis grizzlies': 0.4,
            'new orleans pelicans': 0.3, 'san antonio spurs': 0.2, 'oklahoma city thunder': 0.3,
            'portland trail blazers': 0.3, 'utah jazz': 0.3, 'minnesota timberwolves': 0.3,
            'sacramento kings': 0.3, 'los angeles clippers': 0.5,
            
            # MLB - Strong teams
            'new york yankees': 0.7, 'boston red sox': 0.5, 'tampa bay rays': 0.6,
            'toronto blue jays': 0.4, 'baltimore orioles': 0.3, 'houston astros': 0.6,
            'seattle mariners': 0.4, 'los angeles angels': 0.3, 'oakland athletics': 0.2,
            'texas rangers': 0.4, 'atlanta braves': 0.6, 'philadelphia phillies': 0.5,
            'new york mets': 0.4, 'miami marlins': 0.3, 'washington nationals': 0.2,
            'chicago cubs': 0.4, 'milwaukee brewers': 0.5, 'st. louis cardinals': 0.5,
            'pittsburgh pirates': 0.3, 'cincinnati reds': 0.3, 'los angeles dodgers': 0.7,
            'san diego padres': 0.4, 'san francisco giants': 0.3, 'colorado rockies': 0.2,
            'arizona diamondbacks': 0.3, 'cleveland guardians': 0.4, 'minnesota twins': 0.4,
            'detroit tigers': 0.2, 'kansas city royals': 0.2, 'chicago white sox': 0.2
        }
        
        # Typical totals by sport
        self.typical_totals = {
            'football': 45.0,
            'basketball': 220.0,
            'baseball': 8.5,
            'soccer': 2.5
        }
    
    def normalize_team_name(self, team_name: str) -> str:
        """Normalize team name for lookup"""
        return team_name.lower().strip()
    
    def get_team_strength(self, team_name: str) -> float:
        """Get team strength score (0.0 to 1.0)"""
        normalized = self.normalize_team_name(team_name)
        return self.team_strength.get(normalized, 0.5)  # Default to average if unknown
    
    def predict_spread(self, home_team: str, away_team: str, sport: str) -> Dict:
        """Predict the point spread for a game with player analysis"""
        # Get enhanced team analysis with player data
        home_analysis = self.player_analyzer.analyze_team_with_players(home_team, sport)
        away_analysis = self.player_analyzer.analyze_team_with_players(away_team, sport)
        
        home_strength = home_analysis['team_strength']
        away_strength = away_analysis['team_strength']
        
        # Calculate base spread (positive = home team favored)
        strength_diff = home_strength - away_strength
        base_spread = strength_diff * 14  # Scale to realistic spread range
        
        # Add home field advantage
        home_advantage = self.home_advantage.get(sport, 2.0)
        predicted_spread = base_spread + home_advantage
        
        # Round to nearest 0.5
        predicted_spread = round(predicted_spread * 2) / 2
        
        # Determine confidence based on strength difference and player analysis
        strength_gap = abs(home_strength - away_strength)
        base_confidence = min(85, 50 + (strength_gap * 70))  # 50-85% confidence
        
        # Adjust confidence based on key player availability
        confidence_adjustment = self._calculate_player_confidence_adjustment(home_analysis, away_analysis)
        confidence = min(90, max(40, base_confidence + confidence_adjustment))
        
        # Generate enhanced reasoning with player insights
        reasoning = self._generate_spread_reasoning(home_team, away_team, predicted_spread, home_advantage, 
                                                  strength_gap, home_analysis, away_analysis)
        
        return {
            'predicted_spread': predicted_spread,
            'confidence': round(confidence),
            'reasoning': reasoning,
            'home_strength': round(home_strength, 2),
            'away_strength': round(away_strength, 2),
            'player_analysis': {
                'home_team': home_analysis,
                'away_team': away_analysis
            }
        }
    
    def predict_total(self, home_team: str, away_team: str, sport: str) -> Dict:
        """Predict the total points/runs for a game"""
        home_strength = self.get_team_strength(home_team)
        away_strength = self.get_team_strength(away_team)
        
        # Base total from sport average
        base_total = self.typical_totals.get(sport, 10.0)
        
        # Adjust based on team offensive strength (simplified)
        avg_strength = (home_strength + away_strength) / 2
        strength_adjustment = (avg_strength - 0.5) * 10  # Adjust by up to ±5 points
        
        predicted_total = base_total + strength_adjustment
        
        # Round appropriately by sport
        if sport == 'football':
            predicted_total = round(predicted_total * 2) / 2  # 0.5 increments
        elif sport == 'basketball':
            predicted_total = round(predicted_total)  # Whole numbers
        elif sport == 'baseball':
            predicted_total = round(predicted_total * 2) / 2  # 0.5 increments
        else:
            predicted_total = round(predicted_total * 2) / 2
        
        # Confidence based on how close teams are in strength
        strength_gap = abs(home_strength - away_strength)
        confidence = min(80, 60 - (strength_gap * 40))  # 40-80% confidence
        
        # Generate reasoning
        reasoning = f"Based on typical {sport} scoring patterns. "
        
        if avg_strength > 0.6:
            reasoning += "Both teams have strong offensive capabilities, suggesting a higher-scoring game."
        elif avg_strength < 0.4:
            reasoning += "Both teams have weaker offensive capabilities, suggesting a lower-scoring game."
        else:
            reasoning += "Both teams have average offensive capabilities."
        
        if strength_gap < 0.1:
            reasoning += " The teams are evenly matched, which typically leads to more predictable totals."
        else:
            reasoning += " The strength difference between teams adds some uncertainty to the total."
        
        return {
            'predicted_total': predicted_total,
            'confidence': round(confidence),
            'reasoning': reasoning,
            'base_total': base_total,
            'strength_adjustment': round(strength_adjustment, 1)
        }
    
    def make_full_prediction(self, home_team: str, away_team: str, sport: str) -> Dict:
        """Make complete predictions for a game"""
        spread_pred = self.predict_spread(home_team, away_team, sport)
        total_pred = self.predict_total(home_team, away_team, sport)
        
        # Overall confidence (average of both predictions)
        overall_confidence = round((spread_pred['confidence'] + total_pred['confidence']) / 2)
        
        return {
            'game_info': {
                'home_team': home_team,
                'away_team': away_team,
                'sport': sport,
                'prediction_time': datetime.now().isoformat()
            },
            'spread_prediction': spread_pred,
            'total_prediction': total_pred,
            'overall_confidence': overall_confidence,
            'disclaimer': self.get_responsible_gambling_disclaimer()
        }
    
    def _calculate_player_confidence_adjustment(self, home_analysis: Dict, away_analysis: Dict) -> float:
        """Calculate confidence adjustment based on key player availability"""
        adjustment = 0.0
        
        # Check for key player injuries
        for player in home_analysis['key_players']:
            if player['injury_status']['status'] in ['Out', 'Doubtful']:
                adjustment -= 5  # Reduce confidence for key injuries
        
        for player in away_analysis['key_players']:
            if player['injury_status']['status'] in ['Out', 'Doubtful']:
                adjustment += 5  # Increase confidence when opponent has key injuries
        
        return adjustment
    
    def _generate_spread_reasoning(self, home_team: str, away_team: str, predicted_spread: float, 
                                 home_advantage: float, strength_gap: float, 
                                 home_analysis: Dict, away_analysis: Dict) -> str:
        """Generate enhanced reasoning with player insights"""
        reasoning_parts = []
        
        # Basic spread reasoning
        if predicted_spread > 0:
            reasoning_parts.append(f"{home_team} is favored by {abs(predicted_spread)} points.")
        else:
            reasoning_parts.append(f"{away_team} is favored by {abs(predicted_spread)} points.")
        
        reasoning_parts.append(f"Home field advantage adds {home_advantage} points.")
        
        # Add player insights
        key_injuries = []
        for player in home_analysis['key_players']:
            if player['injury_status']['status'] in ['Out', 'Doubtful']:
                key_injuries.append(f"{player['name']} ({player['injury_status']['status']})")
        
        for player in away_analysis['key_players']:
            if player['injury_status']['status'] in ['Out', 'Doubtful']:
                key_injuries.append(f"{player['name']} ({player['injury_status']['status']})")
        
        if key_injuries:
            reasoning_parts.append(f"Key injuries: {', '.join(key_injuries[:2])}.")
        
        # Add form insights
        home_form = [p['recent_form']['trend'] for p in home_analysis['key_players']]
        away_form = [p['recent_form']['trend'] for p in away_analysis['key_players']]
        
        if 'improving' in home_form:
            reasoning_parts.append(f"{home_team} key players showing improving form.")
        if 'declining' in away_form:
            reasoning_parts.append(f"{away_team} key players showing declining form.")
        
        # Strength assessment
        if strength_gap > 0.3:
            reasoning_parts.append("There's a significant strength difference between these teams.")
        elif strength_gap > 0.1:
            reasoning_parts.append("These teams are fairly evenly matched.")
        else:
            reasoning_parts.append("These teams appear to be very evenly matched.")
        
        return " ".join(reasoning_parts)
    
    def get_responsible_gambling_disclaimer(self) -> str:
        """Get responsible gambling disclaimer"""
        return (
            "⚠️ IMPORTANT DISCLAIMER: These predictions are for entertainment purposes only "
            "and should not be considered as professional betting advice. Sports betting involves "
            "risk and should only be done with money you can afford to lose. Please gamble responsibly. "
            "If you have a gambling problem, please seek help from professional resources."
        )

# Example usage and testing
if __name__ == '__main__':
    engine = PredictionEngine()
    
    # Test predictions
    test_games = [
        ('Kansas City Chiefs', 'Buffalo Bills', 'football'),
        ('Los Angeles Lakers', 'Boston Celtics', 'basketball'),
        ('New York Yankees', 'Boston Red Sox', 'baseball')
    ]
    
    print("🎯 Ares AI Prediction Engine - Test Results")
    print("=" * 60)
    
    for home, away, sport in test_games:
        prediction = engine.make_full_prediction(home, away, sport)
        
        print(f"\n🏆 {sport.title()}: {home} vs {away}")
        print(f"📊 Predicted Spread: {prediction['spread_prediction']['predicted_spread']} "
              f"({prediction['spread_prediction']['confidence']}% confidence)")
        print(f"📈 Predicted Total: {prediction['total_prediction']['predicted_total']} "
              f"({prediction['total_prediction']['confidence']}% confidence)")
        print(f"🎯 Overall Confidence: {prediction['overall_confidence']}%")
        print(f"💭 Spread Reasoning: {prediction['spread_prediction']['reasoning']}")
        print(f"💭 Total Reasoning: {prediction['total_prediction']['reasoning']}")
        print("-" * 60)
    
    print(f"\n{prediction['disclaimer']}")
