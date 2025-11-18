from flask import Flask, render_template, request, url_for, jsonify, redirect,flash
from flask_sqlalchemy import SQLAlchemy
import os, secrets, requests
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_mail import Mail, Message
import google.generativeai as genai
from dotenv import load_dotenv
from flask_migrate import Migrate
import pandas as pd
import math


load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trips.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = os.getenv('MAIL_PORT')
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# API Keys
UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')    
genai.configure(api_key=GEMINI_API_KEY)

# Global cache
image_cache = {}

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False) 
    password = db.Column(db.String(200), nullable=False)
    reset_token = db.Column(db.String(100), index=True, unique=True, nullable=True)
    reset_token_expiration = db.Column(db.DateTime, nullable=True)

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    origin = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.String(20), nullable=False)
    end_date = db.Column(db.String(20), nullable=False)
    budget_level = db.Column(db.String(20), nullable=False)
    budget = db.Column(db.Float)
    travelers_count = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('trips', lazy=True))

    # ✅ NEW FIELDS - ADD THESE:
    hotel_usd = db.Column(db.Float, default=0)           # Hotel cost in USD
    food_usd = db.Column(db.Float, default=0)            # Food cost in USD
    transport_usd = db.Column(db.Float, default=0)       # Local transport in USD
    travel_cost_usd = db.Column(db.Float, default=0)     # Flight/Train cost in USD
    distance_km = db.Column(db.Float, default=0)         # Distance between origin-destination
    is_local = db.Column(db.Boolean, default=False)      # Domestic (True) or International (False)
    itinerary = db.Column(db.Text, nullable=True)  # To store AI-generated itinerary JSON or text

    def calculate_duration(self):
        try:
            start = datetime.strptime(self.start_date, '%Y-%m-%d')
            end = datetime.strptime(self.end_date, '%Y-%m-%d')
            return (end - start).days
        except:
            return 0

    def calculate_cost_per_day(self):
        try:
            duration = self.calculate_duration()
            if duration > 0 and self.budget:
                return round(self.budget / duration, 2)
            return 0
        except:
            return 0
        


from datetime import datetime

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1 to 5 stars
    comment = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('feedbacks', lazy=True))
    trip = db.relationship('Trip', backref=db.backref('feedbacks', lazy=True))




def generate_trip_suggestions(preferences):
    try:
        model = genai.GenerativeModel('models/gemini-pro-latest')  # Updated model name
        
        prompt = f"""As a travel expert, suggest 5 amazing travel destinations based on these preferences:
        
Budget: ₹{preferences.get('budget', 'moderate')}
Travel Style: {preferences.get('style', 'adventure')}
Duration: {preferences.get('duration', '1 week')}
Interests: {preferences.get('interests', 'culture, food, nature')}

For each destination, provide:
1. Destination name
2. Why it's perfect for these preferences (2-3 sentences)
3. Best time to visit
4. Estimated daily budget in ₹

Format as JSON array with keys: name, reason, best_time, daily_budget"""

        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        print(f"Gemini API error: {e}")
        return None


def generate_itinerary(destination, duration, interests):
    try:
        model = genai.GenerativeModel('models/gemini-pro-latest')
        
        prompt = f"""Create a detailed {duration}-day itinerary for {destination}.

Traveler interests: {interests}

For each day:
- Day number
- Morning, afternoon, and evening activities
- Recommended restaurants
- Estimated daily cost in ₹
- Travel tips specific to that day

Format as structured day-by-day plan."""

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"Gemini API error: {e}")
        return None


def generate_travel_tips(destination, trip_details):
    try:
        model = genai.GenerativeModel('models/gemini-pro-latest')

        prompt = f"""Provide comprehensive travel tips for visiting {destination}.

Trip details:
- Duration: {trip_details.get('duration', 'N/A')} days
- Budget: ₹{trip_details.get('budget', 'N/A')}
- Travelers: {trip_details.get('travelers', 1)} people

Include:
1. Best areas to stay
2. Transportation tips
3. Must-try local foods
4. Cultural etiquette and customs
5. Safety tips
6. Money-saving advice
7. Hidden gems
8. Things to avoid

Keep it practical and specific."""

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"Gemini API error: {e}")
        return None

@app.route('/api/ai-suggestions', methods=['POST'])
@login_required
def get_ai_suggestions():
    """Get AI-powered destination suggestions"""
    data = request.get_json()
    
    suggestions = generate_trip_suggestions({
        'budget': data.get('budget', 'moderate'),
        'style': data.get('style', 'adventure'),
        'duration': data.get('duration', '1 week'),
        'interests': data.get('interests', 'culture, food')
    })
    
    if suggestions:
        return jsonify({'suggestions': suggestions})
    else:
        return jsonify({'error': 'Could not generate suggestions'}), 500


import logging

@app.route('/api/generate-itinerary', methods=['POST'])
@login_required
def get_ai_itinerary():
    """Generate AI itinerary for a trip and save it persistently with better error handling"""
    data = request.get_json()
    logging.info(f"Received generate-itinerary request data: {data}")

    destination = data.get('destination')
    duration = data.get('duration', 3)
    interests = data.get('interests', 'sightseeing, food')
    trip_id = data.get('trip_id')  # Must be provided by frontend

    if not destination or not trip_id:
        logging.error("Missing required fields: destination or trip_id")
        return jsonify({'error': 'Missing required fields: destination or trip_id'}), 400

    try:
        itinerary = generate_itinerary(destination, duration, interests)
        logging.info(f"Received itinerary from generate_itinerary: {itinerary}")
    except Exception as e:
        logging.error(f"Error generating itinerary: {e}")
        return jsonify({'error': 'Failed to generate itinerary due to internal error'}), 500

    if itinerary:
        trip = Trip.query.get(trip_id)
        if trip and trip.user_id == current_user.id:
            trip.itinerary = itinerary
            try:
                db.session.commit()
                return jsonify({'itinerary': itinerary})
            except Exception as e:
                logging.error(f"DB commit failed: {e}")
                return jsonify({'error': 'Failed to save itinerary'}), 500
        else:
            logging.warning(f"Unauthorized access attempt or trip not found: trip_id={trip_id}, user_id={current_user.id}")
            return jsonify({'error': 'Trip not found or unauthorized'}), 404
    else:
        logging.warning("Empty itinerary received from generate_itinerary function")
        return jsonify({'error': 'Could not generate itinerary'}), 500

@app.route('/api/travel-tips/<destination>', methods=['GET'])
@login_required
def get_travel_tips(destination):
    """Get AI-powered travel tips"""
    
    # Get trip details from query params
    trip_details = {
        'duration': request.args.get('duration', 3),
        'budget': request.args.get('budget', 1000),
        'travelers': request.args.get('travelers', 1)
    }
    
    tips = generate_travel_tips(destination, trip_details)
    
    if tips:
        return jsonify({'tips': tips})
    else:
        return jsonify({'error': 'Could not generate tips'}), 500


# Helper Functions
def get_weather(city):
    """Fetch current weather for a city"""
    try:
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            'q': city,
            'appid': OPENWEATHER_API_KEY,
            'units': 'metric'
        }
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            temp = round(data['main']['temp'])
            
            if temp >= 25:
                weather_desc = "Warm"
            elif temp >= 15:
                weather_desc = "Mild"
            elif temp >= 5:
                weather_desc = "Cool"
            else:
                weather_desc = "Cold"
            
            return {
                'temp': temp,
                'description': data['weather'][0]['description'].title(),
                'icon': data['weather'][0]['icon'],
                'weather_type': weather_desc,
                'humidity': data['main']['humidity']
            }
        return None
    except Exception as e:
        print(f"Weather API error for {city}: {e}")
        return None

def get_destination_image(destination):
    """Fetch image URL for a destination from Unsplash with caching"""
    
    # Check cache first
    if destination in image_cache:
        return image_cache[destination]
    
    try:
        url = "https://api.unsplash.com/search/photos"
        params = {
            'query': f'{destination} travel landmark',
            'client_id': UNSPLASH_ACCESS_KEY,
            'per_page': 1,
            'orientation': 'landscape'
        }
        response = requests.get(url, params=params, timeout=3)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('results') and len(data['results']) > 0:
                image_url = data['results'][0]['urls']['regular']
                image_cache[destination] = image_url
                return image_url
        
        return None
        
    except Exception as e:
        print(f"Unsplash API error for {destination}: {e}")
        return None



@app.route('/api/trending', methods=['GET'])
def get_trending_places():
    trending_places = [
        {'name': 'Paris', 'country': 'France'},
        {'name': 'Tokyo', 'country': 'Japan'},
        {'name': 'Dubai', 'country': 'UAE'},
        {'name': 'Goa', 'country': 'India'},
        {'name': 'Shimla', 'country': 'India'},
        {'name': 'Jaipur', 'country': 'India'}
    ]

    results = []
    for place in trending_places:
        city = place['name']
        weather = get_weather(city)
        if not weather:
            continue
        image_url = get_destination_image(city)
        if not image_url:
            image_url = f'https://via.placeholder.com/800x600/4A90E2/FFFFFF?text={city}'
        results.append({
            'name': city,
            'country': place['country'],
            'current_temp': weather['temp'],
            'weather_desc': weather['description'],
            'weather_type': weather['weather_type'],
            'weather_icon': f"http://openweathermap.org/img/wn/{weather['icon']}@2x.png",
            'image': image_url,
            'season': 'Year-round',
            'why_now': f'Popular destination with {weather["description"]} weather'
        })
    return jsonify(results)



# Load Cost of Living CSV
try:
    col_df = pd.read_csv('Cost_of_Living_Index_by_Country_2024.csv')
    cost_of_living_raw = dict(zip(col_df['Country'].str.strip().str.lower(), 
                                  col_df['Cost_of_Living_Index']))
except:
    cost_of_living_raw = {}

USD_TO_INR = 83

def normalize_coli(col_index):
    if col_index <= 0:
        return 1.0
    return col_index / 50  # approximate normalization

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_lat_lon(place):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": place, "format": "json", "limit": 1}
        headers = {"User-Agent": "TripPlannerApp/1.0"}
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        results = response.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"Error getting lat/lon for {place}: {e}")
    return None, None

def calculate_trip_budget(origin_lat, origin_lon, destination_lat, destination_lon,
                         days, people, budget_level, destination_country,origin_country):
    
    # DEBUG: Log all input parameters
    print('=== CALCULATE_TRIP_BUDGET DEBUG ===')
    print(f'INPUT PARAMETERS:')
    print(f'  origin_lat: {origin_lat} (type: {type(origin_lat)})')
    print(f'  origin_lon: {origin_lon} (type: {type(origin_lon)})')
    print(f'  destination_lat: {destination_lat} (type: {type(destination_lat)})')
    print(f'  destination_lon: {destination_lon} (type: {type(destination_lon)})')
    print(f'  days: {days}')
    print(f'  people: {people}')
    print(f'  budget_level: {budget_level}')
    print(f'  destination_country: {destination_country}')
    
    # Calculate distance
    if origin_lat is not None and destination_lat is not None:
        distance = haversine_distance(origin_lat, origin_lon, destination_lat, destination_lon)
        print(f'\nDISTANCE CALCULATION:')
        print(f'  distance_km: {distance}')
    else:
        distance = 0
        print(f'\nDISTANCE CALCULATION:')
        print(f'  ❌ ERROR: Lat/Lon values are None! Distance set to 0')
        print(f'  origin_lat={origin_lat}, destination_lat={destination_lat}')

    
    
    # Cost of living calculation
    raw_coli = cost_of_living_raw.get(destination_country.lower(), 50)
    coli_factor = normalize_coli(raw_coli)
    print(f'\nCOST OF LIVING:')
    print(f'  destination_country: {destination_country}')
    print(f'  raw_coli value: {raw_coli}')
    print(f'  coli_factor: {coli_factor}')

    # Budget level multiplier
    is_local = False
    if origin_country and destination_country:
        # Normalize country names for comparison (lowercase, strip whitespace)
        origin_country_normalized = origin_country.strip().lower()
        destination_country_normalized = destination_country.strip().lower()
        
        # Check if same country
        is_local = (origin_country_normalized == destination_country_normalized)
        print(f'\nLOCAL vs INTERNATIONAL:')
        print(f'  origin_country (normalized): {origin_country_normalized}')
        print(f'  destination_country (normalized): {destination_country_normalized}')
        print(f'  is_local: {is_local}')
    else:
        print(f'\nLOCAL vs INTERNATIONAL:')
        print(f'  ⚠️  WARNING: origin_country or destination_country not provided')
        print(f'  Defaulting to international rates (is_local = False)')

    if is_local:
        base_hotel = 8
        base_food = 5
        base_transport = 3
    else:
        base_hotel = 25
        base_food = 15
        base_transport = 8

    # Travel cost calculation
    if is_local:
        per_km_inr = 5  # ₹5 per km domestic
    else:
        per_km_inr = 8  # ₹8 per km international
        

    travel_cost_usd = (distance * per_km_inr) / USD_TO_INR
    print(f'\nTRAVEL COST:')
    print(f'  per_km_inr: {per_km_inr}')
    print(f'  USD_TO_INR rate: {USD_TO_INR}')
    print(f'  travel_cost_usd: {travel_cost_usd}')

    
    style_mul = {'low': 0.3, 'mid': 0.8, 'high': 1.6}.get(budget_level.lower(), 0.8)
    print(f'\nBUDGET LEVEL:')
    print(f'  is_local: {is_local}')
    print(f'  base_hotel: {base_hotel}')
    print(f'  base_food: {base_food}')
    print(f'  base_transport: {base_transport}')
    print(f'  budget_level: {budget_level}')
    print(f'  style_mul: {style_mul}')

    # Cost calculations
    hotel_cost = base_hotel * coli_factor * style_mul * days * people
    food_cost = base_food * coli_factor * style_mul * days * people
    transport_cost = base_transport * coli_factor * style_mul * days * people

    print(f'\nCOST BREAKDOWN (USD):')
    print(f'  hotel_cost: {base_hotel} * {coli_factor} * {style_mul} * {days} * {people} = {hotel_cost}')
    print(f'  food_cost: {base_food} * {coli_factor} * {style_mul} * {days} * {people} = {food_cost}')
    print(f'  transport_cost: {base_transport} * {coli_factor} * {style_mul} * {days} * {people} = {transport_cost}')
    print(f'  travel_cost_usd: {travel_cost_usd}')

    # Total calculation
    total_usd = hotel_cost + food_cost + transport_cost + travel_cost_usd
    total_inr = total_usd * USD_TO_INR

    print(f'\nFINAL TOTALS:')
    print(f'  total_usd: {total_usd}')
    print(f'  total_inr: {total_inr}')
    print(f'  total_inr (rounded): {round(total_inr, 2)}')
    print('===================================\n')

    breakdown = {
        "hotel_usd": round(hotel_cost, 2),
        "food_usd": round(food_cost, 2),
        "transport_usd": round(transport_cost, 2),
        "travel_cost_usd": round(travel_cost_usd, 2),
        "total_usd": round(total_usd, 2),
        "total_inr": round(total_inr, 2),
        "distance_km": round(distance, 2),
    }

    return breakdown



def get_country_from_destination(destination):
    """
    Returns the country name of a destination using OpenStreetMap Nominatim API with User-Agent header.
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': destination,
            'format': 'json',
            'addressdetails': 1,
            'limit': 1
        }
        headers = {
            'User-Agent': 'TripPlannerPro/1.0 (manukumarhnm@gmail.com)'  # Use your app name and contact info
        }
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        results = response.json()
        if results and 'address' in results[0]:
            address = results[0]['address']
            country = address.get('country')
            if country:
                return country.lower()
        return None
    except Exception as e:
        print(f"Error fetching country for destination '{destination}': {e}")
        return None 




# Routes
@app.route('/')
def home():
    is_authenticated = current_user.is_authenticated
    return render_template('home.html', is_authenticated=is_authenticated)


def get_place_details(place_name):
    """
    Given a place_name (city or location), perform a Nominatim search and return
    a dict with keys like display_name, city, state, country, lat, lon normalized from API response.
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': place_name,
            'format': 'json',
            'addressdetails': 1,
            'limit': 1
        }
        headers = {'User-Agent': 'TripPlannerApp/1.0 manukumarhnm@gmail.com'}
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        results = response.json()
        if results:
            result = results[0]
            address = result.get('address', {})
            return {
                'display_name': result.get('display_name', ''),
                'city': address.get('city') or address.get('town') or address.get('village') or '',
                'state': address.get('state', ''),
                'country': address.get('country', ''),
                'lat': float(result.get('lat', 0)),
                'lon': float(result.get('lon', 0))
            }
        else:
            return None
    except Exception as e:
        print(f"Error fetching place details for {place_name}: {e}")
        return None


def get_cost_of_living(place_details, cost_of_living_map):
    """
    Given place_details dict with key 'country', return cost of living index from dictionary cost_of_living_map.
    Returns 1.0 if country not found or place_details is missing.
    """
    if not place_details or 'country' not in place_details:
        return 1.0
    country_name = place_details['country'].strip().lower()
    return cost_of_living_map.get(country_name, 1.0)
  

@app.route('/api/search', methods=['GET'])
def search_places():
    query = request.args.get('q', '').strip()
    if len(query) < 3:
        return jsonify([])

    nominatim_url = 'https://nominatim.openstreetmap.org/search'
    params = {
        'q': query,
        'format': 'json',
        'addressdetails': 1,
        'limit': 5
    }
    headers = {
        'User-Agent': 'TripPlannerPro/1.0 (manukumarhnml@gmail.com)'
    }
    try:
        response = requests.get(nominatim_url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data:
            name = item.get('display_name')
            lat = item.get('lat')
            lon = item.get('lon')
            place_type = item.get('type')

            address = item.get('address', {})
            city_name = address.get('city') or address.get('town') or address.get('village')

            weather = get_weather(city_name) if city_name else None
            image_url = get_destination_image(city_name) if city_name else None
            if not image_url:
                image_url = f'https://via.placeholder.com/800x600/4A90E2/FFFFFF?text={name[:20]}'

            results.append({
                'name': name,
                'lat': lat,
                'lon': lon,
                'type': place_type,
                'current_temp': weather['temp'] if weather else None,
                'weather_desc': weather['description'] if weather else None,
                'weather_icon': f"http://openweathermap.org/img/wn/{weather['icon']}@2x.png" if weather else None,
                'image': image_url,
                'season': 'Year-round',
                'why_now': f'Current: {weather["description"]}' if weather else None
            })
        return jsonify(results)
    except requests.RequestException as e:
        print(f"OpenStreetMap Nominatim API error: {e}")
        return jsonify([]), 500


@app.route('/api/weather/<city>', methods=['GET'])
def get_city_weather(city):
    weather = get_weather(city)
    if weather:
        return jsonify(weather)
    else:
        return jsonify({'error': 'Could not fetch weather'}), 404


@app.route('/api/calculate-budget', methods=['POST'])
def api_calculate_budget():
    try:
        data = request.get_json()

        origin = data.get('origin') or 'india'
        destination = data.get('destination') or 'india'
        budget_level = data.get('budget_level', 'mid')

        start_date = data.get('start_date')
        end_date = data.get('end_date')
        if not start_date or not end_date:
            return jsonify({'error': 'Missing start_date or end_date'}), 400
        try:
            days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days
            if days <= 0:
                return jsonify({'error': 'Invalid date range'}), 400
        except Exception:
            return jsonify({'error': 'Invalid date format'}), 400

        try:
            travelers_count = int(data.get('travelers_count', 1))
            if travelers_count <= 0:
                return jsonify({'error': 'Travelers count must be positive integer'}), 400
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid travelers_count parameter'}), 400

        # Get lat/lon for origin and destination
        origin_details = get_place_details(origin)
        destination_details = get_place_details(destination)

        if not origin_details or not destination_details:
            return jsonify({'error': 'Invalid origin or destination'}), 400

        origin_lat = origin_details.get('lat')
        origin_lon = origin_details.get('lon')
        destination_lat = destination_details.get('lat')
        destination_lon = destination_details.get('lon')

        # ✅ NEW: Get both origin and destination country
        origin_country = get_country_from_destination(origin)
        destination_country = get_country_from_destination(destination)

        print('=== API CALCULATE BUDGET ===')
        print(f'Origin: {origin} → Country: {origin_country}')
        print(f'Destination: {destination} → Country: {destination_country}')
        print(f'Days: {days}, Travelers: {travelers_count}, Budget: {budget_level}')
        print('=============================')

        budget_info = calculate_trip_budget(
            origin_lat, origin_lon, destination_lat, destination_lon,
            days, travelers_count, budget_level, destination_country,origin_country
        )

         # IMPORTANT: Add coordinates to the response
        budget_info['origin_lat'] = origin_details.get('lat')
        budget_info['origin_lon'] = origin_details.get('lon')
        budget_info['destination_lat'] = destination_details.get('lat')
        budget_info['destination_lon'] = destination_details.get('lon')
        

        return jsonify(budget_info)

    except Exception as e:
        return jsonify({'error': 'Internal server error: ' + str(e)}), 500

# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password_value = request.form.get('password')

        if not username or not email or not password_value:
            flash('Please fill out all fields.', 'warning')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already in use. Please use a different email.', 'danger')
            return render_template('register.html')

        password = generate_password_hash(password_value)
        user = User(username=username, email=email, password=password)

        db.session.add(user)
        db.session.commit()

        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Welcome back! Login successful.', 'success')
            return redirect(url_for('home'))
        flash('Invalid username or password. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def is_valid_place(place_details):
    if not place_details:
        return False
    # Check if place details are meaningful, for example have a country and display name
    required_fields = ['display_name', 'country', 'lat', 'lon']
    for field in required_fields:
        if field not in place_details or not place_details[field]:
            return False
    return True

    
@app.route('/create-trip', methods=['GET', 'POST'])
@login_required
def create_trip():
    if request.method == 'POST':

        # DEBUG: Log all form data received
        print('=== BACKEND FORM SUBMISSION ===')
        print('Title:', request.form.get('title'))
        print('Origin:', request.form.get('origin'))
        print('Destination:', request.form.get('destination'))
        print('Start Date:', request.form.get('start_date'))
        print('End Date:', request.form.get('end_date'))
        print('Travelers Count:', request.form.get('travelers_count'))
        print('Budget Level:', request.form.get('budget_level'))
        print('API Budget (if passed):', request.form.get('api_budget'))
        print('==============================')
        origin = request.form.get('origin')
        destination = request.form.get('destination')
        title = request.form.get('title')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        travelers_count = int(request.form.get('travelers_count', 1))
        budget_level = request.form.get('budget_level', 'mid')

        # Validate required inputs
        if not origin:
            flash('Please enter an origin location.', 'danger')
            return render_template('create_trip.html', origin=origin, destination=destination, title=title)
        if not destination:
            flash('Please enter a destination location.', 'danger')
            return render_template('create_trip.html', origin=origin, destination=destination, title=title)

        # Get place details with debug output
        origin_details = get_place_details(origin)
        print("DEBUG: Origin details received:", origin_details)
        destination_details = get_place_details(destination)
        print("DEBUG: Destination details received:", destination_details)

        # Validate place details
        if not is_valid_place(origin_details):
            flash('Invalid origin location entered. Please enter a valid location.', 'danger')
            return render_template('create_trip.html', origin=origin, destination=destination, title=title)

        if not is_valid_place(destination_details):
            flash('Invalid destination location entered. Please enter a valid location.', 'danger')
            return render_template('create_trip.html', origin=origin, destination=destination, title=title)

        # Validate and calculate trip days
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            days = (end - start).days
            if days <= 0:
                flash('End date must be after start date.', 'danger')
                return render_template('create_trip.html', origin=origin, destination=destination, title=title)
        except ValueError:
            flash('Invalid date format.', 'danger')
            return render_template('create_trip.html', origin=origin, destination=destination, title=title)

       # Extract coordinates from form
        origin_lat = float(request.form.get('origin_lat', 0))
        origin_lon = float(request.form.get('origin_lon', 0))
        destination_lat = float(request.form.get('destination_lat', 0))
        destination_lon = float(request.form.get('destination_lon', 0))


        # ✅ NEW: Get both countries using the function
        origin_country = get_country_from_destination(origin)
        # Get destination country for cost of living lookup
        destination_country = get_country_from_destination(destination)

        print('=== CREATE TRIP DEBUG ===')
        print(f'Origin: {origin} → Country: {origin_country}')
        print(f'Destination: {destination} → Country: {destination_country}')
        print(f'Days: {days}, Travelers: {travelers_count}')
        print('=======================')


       # Pass coordinates to budget calculation
        budget = calculate_trip_budget(
            origin_lat,
            origin_lon,
            destination_lat,
            destination_lon,
            days,
            travelers_count,
            budget_level,
            destination_country,
            origin_country
        )

        new_trip = Trip(
            title=title,
            origin=origin,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            budget=budget['total_inr'],
            budget_level=budget_level,
            travelers_count=travelers_count,
            user_id=current_user.id,
            # ✅ ADD THESE NEW FIELDS:
            hotel_usd=budget.get('hotel_usd', 0),
            food_usd=budget.get('food_usd', 0),
            transport_usd=budget.get('transport_usd', 0),
            travel_cost_usd=budget.get('travel_cost_usd', 0),
            distance_km=budget.get('distance_km', 0),
            is_local=origin_country and destination_country and origin_country.lower() == destination_country.lower()
        )

        db.session.add(new_trip)
        db.session.commit()

        flash(f'Trip "{title}" created successfully with budget {budget["total_inr"]} INR!', 'success')
        return redirect(url_for('view_trips'))

    # Handle GET request
    destination = request.args.get('destination', '')
    return render_template('create_trip.html', destination=destination)


@app.route('/get_best_month/<destination>')
def get_best_month(destination):
    try:
        model = genai.GenerativeModel('models/gemini-flash-latest')  # Replace with your chosen model
        prompt = f"What is the best month to visit {destination}? Answer in 1 sentence only."
        response = model.generate_content(prompt)
        best_month = response.text if response else "Unavailable"
        return {'best_month': best_month}
    except Exception as e:
        print(f"Error generating best month: {e}")
        return {'best_month': 'Unable to determine best month at the moment.'}

@app.route('/trips')
@login_required
def view_trips():
    trips = Trip.query.filter_by(user_id=current_user.id).all()
    
    # Calculate totals
    total_days = sum(trip.calculate_duration() for trip in trips)
    total_budget = sum(trip.budget for trip in trips)
    
    return render_template("view_trips.html", 
                         trips=trips, 
                         total_days=total_days,
                         total_budget=total_budget)

def calculate_breakdown(trip):
    """Calculate breakdown percentages and amounts for a trip"""
    usd_to_inr = 83
    total_budget_inr = trip.budget or 0
    
    # Convert USD breakdown to INR
    hotel_inr = trip.hotel_usd * usd_to_inr if trip.hotel_usd else 0
    food_inr = trip.food_usd * usd_to_inr if trip.food_usd else 0
    transport_inr = trip.transport_usd * usd_to_inr if trip.transport_usd else 0
    travel_inr = trip.travel_cost_usd * usd_to_inr if trip.travel_cost_usd else 0
    
    # Calculate percentages
    if total_budget_inr > 0:
        hotel_pct = round((hotel_inr / total_budget_inr) * 100, 1)
        food_pct = round((food_inr / total_budget_inr) * 100, 1)
        transport_pct = round((transport_inr / total_budget_inr) * 100, 1)
        travel_pct = round((travel_inr / total_budget_inr) * 100, 1)
    else:
        hotel_pct = food_pct = transport_pct = travel_pct = 0
    
    return {
        'hotel_inr': round(hotel_inr, 2),
        'hotel_pct': hotel_pct,
        'food_inr': round(food_inr, 2),
        'food_pct': food_pct,
        'transport_inr': round(transport_inr, 2),
        'transport_pct': transport_pct,
        'travel_inr': round(travel_inr, 2),
        'travel_pct': travel_pct,
        'trip_type': 'Domestic' if trip.is_local else 'International'
    }


@app.route('/trip/<int:trip_id>')
@login_required
def trip_details(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    
    if trip.user_id != current_user.id:
        return "Unauthorized", 403
    
    destination_image = get_destination_image(trip.destination)
    
    # ✅ ADD THIS LINE:
    breakdown = calculate_breakdown(trip)
    
    # ✅ PASS breakdown to template:
    return render_template("trip_details.html", trip=trip, destination_image=destination_image, breakdown=breakdown)

@app.route('/edit-trip/<int:trip_id>', methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    
    if request.method == 'POST':
        # DEBUG: Log all form data received
        print('=== BACKEND EDIT FORM SUBMISSION ===')
        print('Trip ID:', trip_id)
        print('Title:', request.form.get('title'))
        print('Origin:', request.form.get('origin'))
        print('Destination:', request.form.get('destination'))
        print('Start Date:', request.form.get('start_date'))
        print('End Date:', request.form.get('end_date'))
        print('Travelers Count:', request.form.get('travelers_count'))
        print('Budget Level:', request.form.get('budget_level'))
        print('API Budget (if passed):', request.form.get('api_budget'))
        print('==============================')
        
        origin = request.form.get('origin')
        destination = request.form.get('destination')
        title = request.form.get('title')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        travelers_count = int(request.form.get('travelers_count', 1))
        budget_level = request.form.get('budget_level', 'mid')

        # Validate required inputs
        if not origin:
            flash('Please enter an origin location.', 'danger')
            return render_template('edit_trip.html', trip=trip)
        if not destination:
            flash('Please enter a destination location.', 'danger')
            return render_template('edit_trip.html', trip=trip)

        # Get place details
        origin_details = get_place_details(origin)
        destination_details = get_place_details(destination)
        
        # Validate place details
        if not is_valid_place(origin_details):
            flash('Invalid origin location.', 'danger')
            return render_template('edit_trip.html', trip=trip)
        if not is_valid_place(destination_details):
            flash('Invalid destination location.', 'danger')
            return render_template('edit_trip.html', trip=trip)

        # Validate and calculate days
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            days = (end - start).days
            if days <= 0:
                flash('End date must be after start date.', 'danger')
                return render_template('edit_trip.html', trip=trip)
        except ValueError:
            flash('Invalid date format.', 'danger')
            return render_template('edit_trip.html', trip=trip)

        # Extract coordinates from form (passed by frontend)
        origin_lat = float(request.form.get('origin_lat', 0))
        origin_lon = float(request.form.get('origin_lon', 0))
        destination_lat = float(request.form.get('destination_lat', 0))
        destination_lon = float(request.form.get('destination_lon', 0))

        # ✅ NEW: Get both countries
        origin_country = get_country_from_destination(origin)
        # Get destination country
        destination_country = get_country_from_destination(destination)

        print('=== CREATE TRIP DEBUG ===')
        print(f'Origin: {origin} → Country: {origin_country}')
        print(f'Destination: {destination} → Country: {destination_country}')
        print(f'Days: {days}, Travelers: {travelers_count}')
        print('=======================')

        # Pass coordinates to budget calculation
        budget = calculate_trip_budget(
            origin_lat,
            origin_lon,
            destination_lat,
            destination_lon,
            days,
            travelers_count,
            budget_level,
            destination_country,
            origin_country
        )

        # Update trip
        trip.title = title
        trip.origin = origin
        trip.destination = destination
        trip.start_date = start_date
        trip.end_date = end_date
        trip.budget = budget['total_inr']
        trip.budget_level = budget_level
        trip.travelers_count = travelers_count,
        # ✅ ADD THESE NEW FIELDS:
        trip.hotel_usd = budget.get('hotel_usd', 0)
        trip.food_usd = budget.get('food_usd', 0)
        trip.transport_usd = budget.get('transport_usd', 0)
        trip.travel_cost_usd = budget.get('travel_cost_usd', 0)
        trip.distance_km = budget.get('distance_km', 0)
        trip.is_local = origin_country and destination_country and origin_country.lower() == destination_country.lower()

        db.session.commit()

        flash(f'Trip "{title}" updated successfully with budget {budget["total_inr"]} INR!', 'success')
        return redirect(url_for('view_trips'))

    # GET request - render edit form
    return render_template('edit_trip.html', trip=trip)

# Delete trip route
@app.route('/delete-trip/<int:trip_id>', methods=['POST'])
@login_required
def delete_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    
    if trip.user_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('view_trips'))
    
    trip_title = trip.title
    db.session.delete(trip)
    db.session.commit()
    
    flash(f'Trip "{trip_title}" deleted successfully.', 'info')
    return redirect(url_for('view_trips'))


# Password Reset Routes
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No account found with that email.', 'warning')
            return render_template('forgot_password.html')
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expiration = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        reset_link = url_for('reset_password', token=token, _external=True)
        msg = Message('Password Reset Request',
                      sender=app.config['MAIL_DEFAULT_SENDER'],
                      recipients=[email])
        msg.body = f"Click the link to reset your password: {reset_link}\n\nIf you didn't request it, please ignore this email."
        try:
            mail.send(msg)
            flash('A reset link has been sent to your email.', 'info')
        except Exception as e:
            print(f"Mail send error: {e}")
            flash('Failed to send reset link email. Please try again later.', 'danger')
        return render_template('forgot_password.html')
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or datetime.utcnow() > user.reset_token_expiration:
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        new_password = request.form['password']
        user.password = generate_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expiration = None
        db.session.commit()
        flash('Password updated! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)
    

@app.route('/api/feedback', methods=['POST'])
@login_required
def submit_feedback():
    data = request.get_json()
    trip_id = data.get('trip_id')
    rating = data.get('rating')
    comment = data.get('comment', '')

    if not trip_id or not rating:
        return jsonify({'error': 'Missing trip_id or rating'}), 400

    trip = Trip.query.get(trip_id)
    if not trip or trip.user_id != current_user.id:
        return jsonify({'error': 'Trip not found or unauthorized'}), 404

    feedback = Feedback(user_id=current_user.id, trip_id=trip_id, rating=rating, comment=comment)
    db.session.add(feedback)
    db.session.commit()
    return jsonify({'message': 'Feedback submitted successfully'})


from flask_login import current_user  # Add this import at top if not already present

@app.route('/api/feedback/<int:trip_id>', methods=['GET'])
def get_feedback(trip_id):
    feedbacks = Feedback.query.filter_by(trip_id=trip_id).order_by(Feedback.timestamp.desc()).all()
    results = [{
        'id': f.id,  # Important to include feedback ID for deletion
        'user': f"{f.user.username}",
        'rating': f.rating,
        'comment': f.comment,
        'timestamp': f.timestamp.isoformat(),
        'is_current_user': current_user.is_authenticated and f.user_id == current_user.id
    } for f in feedbacks]

    avg_rating = db.session.query(db.func.avg(Feedback.rating)).filter_by(trip_id=trip_id).scalar()
    return jsonify({'feedbacks': results, 'average_rating': round(avg_rating, 2) if avg_rating else None})


@app.route('/api/feedback/<int:feedback_id>', methods=['DELETE'])
@login_required
def delete_feedback(feedback_id):
    feedback = Feedback.query.get(feedback_id)
    if not feedback:
        return jsonify({'error': 'Feedback not found'}), 404
    if feedback.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(feedback)
    db.session.commit()
    return jsonify({'message': 'Feedback deleted successfully'})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
