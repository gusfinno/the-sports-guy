from datetime import datetime
import requests
import feedparser
import fastf1
from fastf1.ergast import Ergast


url = "https://www.youtube.com/feeds/videos.xml?playlist_id=PLfoNZDHitwjU1j8PiNg17QGDN37d07Rex"

response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
feed = feedparser.parse(response.content)

target_url = next((entry.link for entry in feed.entries if "Australian Grand Prix" in entry.title), None)
print(target_url)