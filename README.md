# TripPlanner

A **Python Flask** web application for planning, managing, and tracking trips with **AI-powered features** via Google Gemini. Provides budget estimation, itinerary generation, travel tips, live weather, destination imagery, and an interactive map view.

---

## Features

- **Trip Management** — Create, edit, view, and delete trips with origin, destination, dates, and budget level
- **AI Itinerary Generation** — Google Gemini generates detailed day-by-day itineraries based on destination and interests
- **AI Travel Tips** — Personalized tips on accommodation, transportation, food, culture, safety, and hidden gems
- **Budget Estimation** — Calculates hotel, food, transport, and travel costs in USD/INR using haversine distance and cost-of-living data
- **Live Weather** — Real-time weather data from OpenWeatherMap API
- **Destination Discovery** — Trending destinations with images, search with autocomplete via OpenStreetMap
- **Interactive Map** — View all saved trips as markers on an interactive map
- **User Authentication** — Registration, login/logout, password reset via email
- **Feedback & Ratings** — Rate trips 1–5 stars with comments, view average ratings

---

## Tech Stack

| Layer            | Technology                                   |
|------------------|----------------------------------------------|
| Framework        | Flask 2.2.5                                  |
| Language         | Python 3                                     |
| Database         | SQLite + Flask-SQLAlchemy + Flask-Migrate    |
| AI               | Google Gemini (`google-generativeai`)        |
| Authentication   | Flask-Login + Werkzeug password hashing      |
| Email            | Flask-Mail (password reset)                  |
| External APIs    | Unsplash (images), OpenWeatherMap, OpenStreetMap Nominatim |
| Data             | Pandas (cost-of-living CSV), Geopy           |
| Frontend         | Jinja2, Bootstrap 5.3, Font Awesome 6        |
| Config           | python-dotenv                                |

---

## Getting Started

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
# 1. Clone
git clone <repo-url>
cd TripPlanner

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
# Create a .env file with the following:
#   SECRET_KEY=your-secret-key
#   GEMINI_API_KEY=your-google-gemini-api-key
#   UNSPLASH_ACCESS_KEY=your-unsplash-api-key
#   OPENWEATHERMAP_API_KEY=your-openweathermap-api-key
#   MAIL_USERNAME=your-email@gmail.com
#   MAIL_PASSWORD=your-email-app-password

# 5. Initialize database
flask db upgrade

# 6. Run
python app.py
```

The application starts on `http://localhost:5000`.

---

## Project Structure

```
TripPlanner/
  app.py                                    -- Main Flask application (routes, models, logic)
  requirements.txt                          -- Python dependencies
  Cost_of_Living_Index_by_Country_2024.csv  -- Cost-of-living dataset
  geocode_update.py                         -- Script to backfill coordinates for existing trips
  .env                                      -- Environment variables (not committed)
  templates/
    base.html, home.html, login.html, register.html
    forgot_password.html, reset_password.html
    create_trip.html, edit_trip.html
    view_trips.html, trip_details.html
    map.html, search_results.html
    _feedback_dropdown.html
  migrations/
    alembic.ini, env.py, script.py.mako
    versions/                               -- 6 Alembic migration scripts
```

---

## API Keys Required

| Service          | Environment Variable         | Get It At                              |
|------------------|------------------------------|----------------------------------------|
| Google Gemini    | `GEMINI_API_KEY`             | https://makersuite.google.com/app/apikey |
| Unsplash         | `UNSPLASH_ACCESS_KEY`        | https://unsplash.com/developers        |
| OpenWeatherMap   | `OPENWEATHERMAP_API_KEY`     | https://openweathermap.org/api         |
| Gmail (SMTP)     | `MAIL_USERNAME` / `MAIL_PASSWORD` | Gmail App Passwords               |

---

## Database Models

- **User** — id, username, email, password (hashed), reset_token, reset_token_expiry
- **Trip** — id, user_id, origin, destination, start_date, end_date, travelers, budget_level, latitude, longitude, hotel_cost, food_cost, transport_cost, travel_cost, total_cost_usd, total_cost_inr, itinerary, travel_tips, image_url
- **Feedback** — id, trip_id, user_id, rating (1–5), comment, timestamp

---

## License

MIT
