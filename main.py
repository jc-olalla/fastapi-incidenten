from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from typing import List

app = FastAPI()

# Enable CORS so you can connect from browsers or QGIS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Set specific domains for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
P2000_URL = "https://service.p2000.page/api-9XlDZFBmbByUdXp0NHh1cktrUjTkgvUV"
POLL_INTERVAL = 10  # Seconds between polling
MAX_INCIDENTS = 500  # Max incidents stored in memory

# Storage for incident data
incident_buffer: List[dict] = []

# Async fetch and parse loop
async def fetch_p2000_data():
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(P2000_URL)
                response.raise_for_status()
                data = response.json() if isinstance(response.json(), list) else [response.json()]

                seen_ids = set(inc["uid"] for inc in incident_buffer)
                new_incidents = []

                for inc in data:
                    uid = inc.get("uid")
                    latlong = inc.get("latlong")

                    if uid in seen_ids or not latlong:
                        continue

                    try:
                        lat_str, lon_str = latlong.strip().split(",")
                        lat = float(lat_str)
                        lon = float(lon_str)
                    except Exception:
                        continue  # Skip malformed latlong

                    inc["lat"] = lat
                    inc["lon"] = lon
                    new_incidents.append(inc)

                # Add new incidents to the front, trim to max
                incident_buffer[:0] = new_incidents
                if len(incident_buffer) > MAX_INCIDENTS:
                    del incident_buffer[MAX_INCIDENTS:]

        except Exception as e:
            print(f"[ERROR] Failed to fetch or parse data: {e}")

        await asyncio.sleep(POLL_INTERVAL)

# API Endpoint
@app.get("/geojson")
def get_geojson():
    features = []

    for inc in incident_buffer:
        try:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [inc["lon"], inc["lat"]]
                },
                "properties": {k: v for k, v in inc.items() if k not in ("lat", "lon")}
            })
        except Exception:
            continue  # Skip broken entry

    return {
        "type": "FeatureCollection",
        "features": features
    }

# Start fetching in background when app starts
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_p2000_data())

