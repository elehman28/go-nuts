"""Finder: turns a location into nearby restaurants and their website URLs. No model calls."""
from .. import config, osm
from ..team import Agent


class Finder(Agent):
    name = "finder"
    title = "Finder"
    description = "Turns a location into nearby restaurants and their website URLs (OpenStreetMap)."
    skills = {
        "find_restaurants": "payload {location, radius_km} or {lat, lon, radius_km}. Nearby restaurants, saved to the database.",
        "known_restaurants": "payload {city}. Restaurants already in the database for a city (free, no web lookup).",
        "restaurant_info": "payload {name}. Look up one restaurant already in the database by name.",
    }

    def find_restaurants(self, location: str = config.DEFAULT_CITY, radius_km: float = 1.5, limit: int = 30,
                         lat: float | None = None, lon: float | None = None):
        if lat is not None and lon is not None:  # "Near me": the browser's location, used only for this search
            where = "your location"
            lat, lon = float(lat), float(lon)
        else:
            lat, lon, where = osm.geocode(location)
        found = osm.nearby_restaurants(lat, lon, int(radius_km * 1000), limit=limit)
        city = config.DEFAULT_CITY if "new haven" in where.lower() or osm.distance_km(
            lat, lon, *config.DEFAULT_CENTER) < 6 else None
        for r in found:
            r["key"] = self.db.upsert_restaurant({**r, "city": city})
        return {"where": where, "center": [lat, lon], "restaurants": found}

    def known_restaurants(self, city: str = config.DEFAULT_CITY):
        return self.db.restaurants(city)

    def restaurant_info(self, name: str):
        from ..db import restaurant_key
        key = restaurant_key(name)
        return next((r for r in self.db.restaurants() if r["key"] == key), {"error": f"'{name}' not found"})
