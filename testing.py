from datetime import datetime
import requests
import feedparser
import fastf1
from fastf1.ergast import Ergast
fastf1.Cache.enable_cache('fastf1-cache')

schedule = fastf1.get_event_schedule(2026)
print(schedule)