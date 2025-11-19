import time
from geopy.geocoders import Nominatim
from app import app, db, Trip  # Import your Flask app instance along with db and model

def update_trip_coordinates():
    geolocator = Nominatim(user_agent="TripPlannerApp/1.0 (manukumarhnm@gmail.com)")

    with app.app_context():  # <-- Add this to push the app context
        trips = Trip.query.filter(
            (Trip.latitude == None) | (Trip.longitude == None)
        ).all()

        for i, trip in enumerate(trips):
            try:
                location = geolocator.geocode(trip.destination)
                if location:
                    trip.latitude = location.latitude
                    trip.longitude = location.longitude
                    print(f"Updated {trip.title}: {trip.latitude}, {trip.longitude}")
                else:
                    print(f"Location not found for {trip.title}")
            except Exception as e:
                print(f"Error geocoding {trip.title}: {e}")
            time.sleep(1)  # Respect rate limits

            if i % 10 == 0:
                db.session.commit()

        db.session.commit()  # Final commit

if __name__ == "__main__":
    update_trip_coordinates()
