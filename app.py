from flask import Flask, render_template, request, url_for, jsonify, redirect,flash
from flask_sqlalchemy import SQLAlchemy
import os, secrets, requests, random
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from pytrends.request import TrendReq
import google.generativeai as genai
from dotenv import load_dotenv
from flask_migrate import Migrate


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


def generate_trip_suggestions(preferences):
    try:
        model = genai.GenerativeModel('models/gemini-pro-latest')  # Updated model name
        
        prompt = f"""As a travel expert, suggest 5 amazing travel destinations based on these preferences:
        
Budget: {preferences.get('budget', 'moderate')}
Travel Style: {preferences.get('style', 'adventure')}
Duration: {preferences.get('duration', '1 week')}
Interests: {preferences.get('interests', 'culture, food, nature')}

For each destination, provide:
1. Destination name
2. Why it's perfect for these preferences (2-3 sentences)
3. Best time to visit
4. Estimated daily budget in USD

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
- Estimated daily cost in USD
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
- Budget: ${trip_details.get('budget', 'N/A')}
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


@app.route('/api/generate-itinerary', methods=['POST'])
@login_required
def get_ai_itinerary():
    """Generate AI itinerary for a trip"""
    data = request.get_json()
    
    itinerary = generate_itinerary(
        data.get('destination'),
        data.get('duration', 3),
        data.get('interests', 'sightseeing, food')
    )
    
    if itinerary:
        return jsonify({'itinerary': itinerary})
    else:
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

def get_dynamic_budget_estimate(destination):
    """Calculate budget using weather-based estimation"""
    weather = get_weather(destination)
    
    if not weather:
        return None
    
    temp = weather['temp']
    
    # Climate-based estimation
    if temp > 25:
        base_cost = 70
    elif temp > 15:
        base_cost = 100
    elif temp > 5:
        base_cost = 120
    else:
        base_cost = 90
    
    cost_per_day = base_cost + random.randint(-20, 30)
    return max(50, cost_per_day)



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
        budget = get_dynamic_budget_estimate(city)
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
            'approx_cost_per_day': budget or 100,
            'season': 'Year-round',
            'why_now': f'Popular destination with {weather["description"]} weather'
        })
    return jsonify(results)

import pandas as pd

# Load cost of living CSV at startup
try:
    col_df = pd.read_csv('Cost_of_Living_Index_by_Country_2024.csv')
    cost_of_living_map = dict(zip(col_df['Country'].str.strip().str.lower(), col_df['Cost_of_Living_Index']))
except Exception as e:
    print(f"Error loading cost of living CSV: {e}")
    cost_of_living_map = {}


USD_TO_INR = 83  # example conversion rate

def calculate_trip_budget(origin_country, destination_country, days, number_of_people, budget_level, travel_cost=0):
    """
    Calculate total trip budget converted to INR
    """
    # Normalize country names to lowercase for comparison
    origin = origin_country.strip().lower()
    destination = destination_country.strip().lower()

    # Determine if trip is local (same country)
    is_local_trip = (origin == destination)

    # Cost of living factor mapping by country
    col_dest = cost_of_living_map.get(destination, 1.0)

    # Set base daily cost USD differently for local and non-local trips
    base_daily_cost_usd = 40 if is_local_trip else 100

    budget_multipliers = {
        'low': 0.7,
        'mid': 1.0,
        'high': 1.3
    }
    tier_multiplier = budget_multipliers.get(budget_level.lower(), 1.0)

    total_budget_usd = (base_daily_cost_usd * col_dest * days * number_of_people * tier_multiplier) + travel_cost
    total_budget_inr = total_budget_usd * USD_TO_INR

    return round(total_budget_inr, 2)


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
            budget = get_dynamic_budget_estimate(city_name) if city_name else None
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
                'approx_cost_per_day': budget or 100,
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

        origin_country = data.get('origin_country') or 'india'
        destination_country = data.get('destination_country') or 'india'
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

        budget_info = calculate_trip_budget(
            origin_country,
            destination_country,
            days,
            travelers_count,
            budget_level
        )

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


@app.route('/create-trip', methods=['GET', 'POST'])
@login_required
def create_trip():
    if request.method == 'POST':
        title = request.form['title']
        origin = request.form['origin']
        destination = request.form['destination']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        travelers_count = int(request.form['travelers_count'])
        budget_level = request.form.get('budget_level', 'mid')
        travel_cost = 0  # or get from form if applicable

        # Calculate days of trip
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            days = (end - start).days
            if days <= 0:
                flash('End date must be after start date.', 'danger')
                return render_template('create_trip.html', destination=destination)
        except ValueError:
            flash('Invalid date format.', 'danger')
            return render_template('create_trip.html', destination=destination)

        # Calculate trip budget in INR using your function
        budget = calculate_trip_budget(
            origin,
            destination,
            days,
            travelers_count,
            budget_level,
            travel_cost
        )

        new_trip = Trip(
            title=title,
            origin=origin,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            budget_level=budget_level,
            travelers_count=travelers_count,
            user_id=current_user.id
        )

        db.session.add(new_trip)
        db.session.commit()

        flash(f'Trip "{title}" created successfully with budget {budget} INR!', 'success')
        return redirect(url_for('view_trips'))

    destination = request.args.get('destination', '')
    return render_template('create_trip.html', destination=destination)

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

@app.route('/trip/<int:trip_id>')
@login_required
def trip_details(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    
    if trip.user_id != current_user.id:
        return "Unauthorized", 403
    
    destination_image = get_destination_image(trip.destination)
    
    return render_template("trip_details.html", trip=trip, destination_image=destination_image)

@app.route('/edit-trip/<int:trip_id>', methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if request.method == 'POST':
        destination = request.form.get('destination')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        travelers_count = int(request.form.get('travelers_count', 1))
        budget_level = request.form.get('budget_level', 'mid')

        origin_country = current_user.country if hasattr(current_user, 'country') else 'india'
        destination_country = get_country_from_destination(destination) or 'india'

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        days = (end - start).days
        if days <= 0:
            flash("End date must be after start date")
            return redirect(url_for('edit_trip', trip_id=trip_id))

        travel_cost = 0

        budget = calculate_trip_budget(origin_country, destination_country, days, travelers_count, budget_level, travel_cost)

        trip.destination = destination
        trip.start_date = start_date
        trip.end_date = end_date
        trip.travelers_count = travelers_count
        trip.budget = budget
        trip.budget_level = budget_level

        db.session.commit()
        flash("Trip updated successfully")
        return redirect(url_for('view_trips'))

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
    
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
