# Ares AI - Sports Betting Analysis Platform

A production-ready sports betting advisor with live schedules, odds, player props, and actionable pick metrics (Edge, EV, Kelly) presented in a familiar, simple UI.

## 🚀 Quick Deploy to Railway

1. **Fork this repository** to your GitHub account
2. **Connect to Railway**:
   - Go to [Railway](https://railway.app) 
   - Click "Deploy from GitHub repo"
   - Select your forked repository
3. **Set Environment Variables** in Railway dashboard:
   ```
   SPORT_ENABLED=nfl,mlb
   USE_THREAD_SCHEDULER=true
   COLLECT_INTERVAL_SECONDS=600
   PREFER_ESPN_SCHEDULE=true
   ESPN_DAYS_LOOKAHEAD=7
   SECRET_KEY=your-secret-key-here
   ```
4. **Deploy** - Railway will automatically build and deploy
5. **Test** - Visit your app URL and check `/api/health`

## 🏈 Features

- **Autonomous Data Collection**: Schedules from ESPN, odds from The Odds API, player props from SportsGameOdds
- **Live Updates**: Data refreshes every 10 minutes automatically  
- **Best-Line Logic**: Find optimal prices across sportsbooks
- **Pick Evaluation**: Calculate Edge, EV, and Kelly stake percentages
- **User Management**: Save picks, track parlays, view metrics
- **Mobile-First**: Clean, responsive design

## 📊 Core Behavior

### Data Sources (Final Stack)
- **Schedules/Results**: ESPN (scoreboard) for NFL and MLB
- **Game Odds**: The Odds API for moneylines, spreads, totals
- **Player Props**: SportsGameOdds (SGO) API

### Autonomous Collection
- **On Boot**: Collect schedules and enrich with odds
- **Every 10 Minutes**: Refresh schedules + odds automatically
- **Health Monitoring**: `/api/health` shows last collection timestamp

### Best-Line Logic
- **Moneylines**: Best price by book (live comparison)
- **Spreads/Totals**: Best price at posted line across books

### Pick Evaluation
- **Metrics**: Implied probability, Edge = model_p - book_p, EV per $1/$100, Kelly (capped)
- **Player Props**: Over/Under quick-add with neutral model probabilities
- **User Parlays**: "What you're cookin'" shows saved picks with snapshot metrics

## 🛠 Environment Variables

### Essential (Required)
```bash
DATABASE_URL=postgresql://user:pass@host:port/dbname  # Auto-provided by Railway
SECRET_KEY=stable_secret_value
SPORT_ENABLED=nfl,mlb
USE_THREAD_SCHEDULER=true
COLLECT_INTERVAL_SECONDS=600
PREFER_ESPN_SCHEDULE=true
ESPN_DAYS_LOOKAHEAD=7
```

### Optional (Enhanced Features)
```bash
# Betting Odds
ODDS_API_KEY=your_the_odds_api_key
ODDS_REGIONS=us,us2

# Player Props  
SGO_API_KEY=your_sgo_api_key
ODDS_PROPS_PROVIDER=sgo
PROPS_CACHE_TTL_SECONDS=300

# SportsDataIO (alternative schedule source)
SPORTSDATAIO_API_KEY=your_sportsdata_api_key
```

## 🔧 API Endpoints

### Public App Endpoints
- `GET /api/health` - Status, counts, stale ratio, last_collect_ts
- `GET /api/games/upcoming` - Upcoming/live games list
- `POST /api/picks/evaluate` - Returns p_model, implied_prob, edge, ev, kelly
- `GET /api/picks/suggest?sport=nfl&game_id=123` - Suggested picks with metrics
- `GET /api/player_search?q=mahomes` - Player autosuggest  
- `GET /api/player_props?name=mahomes` - List of props by market
- `POST /api/bets/save` - Save pick/prop to user's parlay (requires login)
- `GET /api/parlays` - List current user's active parlays with metrics
- `POST /api/bets/delete` - Delete a saved bet (owner-only)

### Admin/Debug Endpoints  
- `POST /collect-data` - One-time forced collection
- `POST /api/admin/reseed` - Purge and reseed upcoming/live via ESPN
- `GET /api/debug/data-collection` - Step-by-step collection diagnostics

## 🏃‍♂️ Testing Your Deployment

Once deployed to Railway:

1. **Health Check**: `GET https://your-app.railway.app/api/health`
   - Should show `last_collect_ts` populated and `total_games > 0`

2. **Games List**: `GET https://your-app.railway.app/api/games/upcoming` 
   - Should list NFL/MLB games

3. **Player Search**: `GET https://your-app.railway.app/api/player_search?q=mahomes`
   - Should return player suggestions

4. **Debug**: `GET https://your-app.railway.app/api/debug/data-collection`
   - Shows step-by-step collection diagnostics

5. **Force Collection**: `POST https://your-app.railway.app/collect-data`
   - Manually trigger data refresh

## 🏗 Architecture

```
├── app.py                 # Main Flask app with routes and models
├── sports_collector.py    # Data collection orchestrator  
├── providers/            # External API clients
│   ├── espn_client.py    # ESPN scoreboards (primary schedules)
│   ├── odds_client.py    # The Odds API (betting lines)
│   ├── sgo_client.py     # SportsGameOdds (player props)
│   └── registry.py       # Sport configuration and enablement
├── services/             # Business logic
│   ├── probabilities.py  # Model probability calculations
│   └── home_service.py   # Featured content curation
├── utils/                # Utilities
│   ├── pricing.py        # Odds conversion and Kelly calculations
│   └── time_utils.py     # Timezone handling
├── templates/            # Jinja2 HTML templates
├── static/              # CSS, JavaScript, images
├── railway.toml         # Railway deployment config
├── Procfile            # Process definitions
└── requirements.txt    # Python dependencies
```

## 🚨 Troubleshooting

### No NFL Data Showing
1. Check `/api/debug/data-collection` for specific errors
2. Verify environment variables are set in Railway
3. Try `POST /api/admin/reseed` to force refresh
4. Check `/api/health` for `last_collect_ts`

### Scheduler Not Running
- Ensure `USE_THREAD_SCHEDULER=true` in Railway environment
- Check Railway logs for scheduler startup messages
- Health endpoint shows collection timestamp if working

### Database Issues
- Railway provides PostgreSQL automatically
- Schema auto-creates on first run
- Use `/api/admin/reseed` to rebuild game data

## 📈 Scalability

### To Add a Sport
1. Add sport config to `providers/registry.py` 
2. Update ESPN client if supported
3. Set `SPORT_ENABLED=nfl,mlb,nba` (add new sport)
4. Odds integration works automatically via The Odds API

### Performance
- Built-in request timeouts and retries
- Intelligent caching with TTL
- Graceful degradation when providers are down
- Single worker recommended for Railway (scheduler compatibility)

## 📝 License

MIT License - see LICENSE file for details.

---

**Ready to launch?** Just fork, connect to Railway, set your environment variables, and deploy! 🚀