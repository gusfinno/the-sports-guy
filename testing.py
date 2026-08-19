from datetime import datetime
import requests
import feedparser
import fastf1
from fastf1.ergast import Ergast
fastf1.Cache.enable_cache('fastf1-cache')

session = fastf1.get_session(2025, "Barcelona Grand Prix", 'Race')
session.load(laps=True, telemetry=False, weather=True, messages=False)
results = session.results
print(session.event.Location)
