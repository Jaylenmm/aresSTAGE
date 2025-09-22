# Ares AI - Sports Betting Advisor

A simple AI-powered sports betting advisor web application built with Flask and SQLite.

## Features

- **Dashboard**: Overview of games, predictions, and statistics
- **Games Management**: View all upcoming and completed games
- **Predictions**: AI-generated betting predictions with confidence scores
- **Clean UI**: Modern, responsive design with Tailwind CSS
- **SQLite Database**: Lightweight database for storing game and prediction data

## Project Structure

```
Ares-AI/
├── app.py                 # Main Flask application with models and routes
├── requirements.txt       # Python dependencies
├── seed_data.py          # Script to populate database with sample data
├── README.md             # This file
├── templates/            # HTML templates
│   ├── base.html         # Base template
│   ├── dashboard.html    # Dashboard page
│   ├── games.html        # Games listing page
│   └── predictions.html  # Predictions page
└── static/               # Static files
    └── css/
        └── style.css     # Custom CSS styles
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

### 3. Seed the Database (Optional)

To add sample data for testing:

```bash
python seed_data.py
```

## Usage

1. **Dashboard**: Visit the home page to see an overview of games and predictions
2. **Games**: View all games with their status, scores, and details
3. **Predictions**: See AI-generated predictions with confidence scores
4. **API Endpoints**: Access data via REST API at `/api/games` and `/api/predictions`

## Database Models

### Game
- `id`: Primary key
- `home_team`: Home team name
- `away_team`: Away team name
- `date`: Game date and time
- `sport`: Sport type (football, basketball, etc.)
- `status`: Game status (upcoming, live, completed)
- `home_score` / `away_score`: Final scores
- `created_at`: Record creation timestamp

### Prediction
- `id`: Primary key
- `game_id`: Foreign key to Game
- `predicted_winner`: Predicted winning team
- `confidence`: Confidence score (0.0 to 1.0)
- `prediction_type`: Type of prediction (winner, spread, total)
- `odds`: Betting odds
- `created_at`: Prediction creation timestamp

## Future Enhancements

- User authentication and profiles
- Real-time game updates
- Advanced AI prediction algorithms
- Betting history tracking
- Mobile app integration
- Live odds integration
- Social features and sharing

## Development

This is an MVP (Minimum Viable Product) designed to be beginner-friendly with:
- Clear file structure
- Simple naming conventions
- Comprehensive comments
- Easy-to-understand code

## License

This project is for educational purposes. Please ensure compliance with local gambling laws and regulations.
