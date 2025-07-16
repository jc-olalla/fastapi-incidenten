from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from typing import List

app = FastAPI()

# CORS for browser-based maps or QGIS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Settings
P2000_URL = "https://service.p2000.page/api-9XlDZFBmbByUdXp0NHh1cktrUjTkgvUV"
POLL_INTERVAL = 10  # seconds
MAX_INCIDENTS = 500  # how many to keep in memory

# In-memory buffer of recent alerts
incident_buffer: List[dict] = []

# Background fetcher
async def fetch_p2000_data():
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(P2000_URL)
                response.raise_for_status()
                data = response.json()

                # Filter only entries with lat/lon and deduplicate
                new_incidents = []
                seen_ids = set((inc.get("tijd"), inc.get("melding")) for inc in incident_buffer)

                for inc in data:
                    if "lat" in inc and "lon" in inc:
                        incident_id = (inc.get("tijd"), inc.get("melding"))
                        if incident_id not in seen_ids:
                            new_incidents.append(inc)

                # Add new, trim old
                incident_buffer[:0] = new_incidents
                if len(incident_buffer) > MAX_INCIDENTS:
                    del incident_buffer[MAX_INCIDENTS:]

        except Exception as e:
            print(f"Error fetching P2000: {e}")

        await asyncio.sleep(POLL_INTERVAL)

# GeoJSON endpoint
@app.get("/geojson")
def get_geojson():
    features = []
    for inc in incident_buffer:
        try:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(inc["lon"]), float(inc["lat"])]
                },
                "properties": {k: v for k, v in inc.items() if k not in ("lat", "lon")}
            })
        except Exception as e:
            continue  # Skip invalid entry

    return {
        "type": "FeatureCollection",
        "features": features
    }

# Start background task
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_p2000_data())

