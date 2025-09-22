"""
Test script for the prediction system
"""

import requests
import json

def test_prediction_api():
    """Test the prediction API endpoint"""
    
    # Test data
    test_cases = [
        {
            'home_team': 'Kansas City Chiefs',
            'away_team': 'Buffalo Bills',
            'sport': 'football'
        },
        {
            'home_team': 'Los Angeles Lakers',
            'away_team': 'Boston Celtics',
            'sport': 'basketball'
        },
        {
            'home_team': 'New York Yankees',
            'away_team': 'Boston Red Sox',
            'sport': 'baseball'
        }
    ]
    
    print("🎯 Testing Ares AI Prediction API")
    print("=" * 50)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📊 Test {i}: {test_case['home_team']} vs {test_case['away_team']} ({test_case['sport']})")
        
        try:
            response = requests.post(
                'http://localhost:5000/predict',
                json=test_case,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['success']:
                    prediction = data['prediction']
                    
                    print(f"✅ Success!")
                    print(f"   Spread: {prediction['spread_prediction']['predicted_spread']} ({prediction['spread_prediction']['confidence']}%)")
                    print(f"   Total: {prediction['total_prediction']['predicted_total']} ({prediction['total_prediction']['confidence']}%)")
                    print(f"   Overall: {prediction['overall_confidence']}%")
                else:
                    print(f"❌ API Error: {data['message']}")
            else:
                print(f"❌ HTTP Error: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("❌ Connection Error: Make sure the Flask app is running on localhost:5000")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print(f"\n{prediction['disclaimer']}")

if __name__ == '__main__':
    test_prediction_api()
