import logging
import feedparser
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import time
import httpx
import os
from dotenv import load_dotenv
from database import init_db, get_races, add_schedule_to_db, schedule_exists_for_year, add_drivers_to_db, drivers_exist, clear_drivers, get_driver_image
import fastf1
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import requests
fastf1.Cache.enable_cache('fastf1-cache')  # Enable caching for faster data retrieval

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Application starting up...")

app = FastAPI()
# init_db() # Initialize database at startup - This will be handled by tests or explicit startup event
logging.info("Database initialization will be handled by tests or explicit startup event.")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

def load_driver_data():
    if drivers_exist():
        return
    response = requests.get("https://api.openf1.org/v1/drivers?session_key=latest")
    if response.status_code == 200:
        data = response.json()
        for driver in data:
            add_drivers_to_db(driver['driver_number'], driver['broadcast_name'], driver['first_name'], driver['last_name'], driver['headshot_url'])
    else:
        print("Error fetching driver data")

load_dotenv()
api_key = os.getenv("SPORT_API")
API_BASE_URL = "https://v1.formula-1.api-sports.io/competitions"

@app.get("/")
async def home(request: Request):
    init_db()
    load_driver_data()
    current_year = datetime.now().year
    if not schedule_exists_for_year(current_year):
        clear_drivers()
        schedule = fastf1.get_event_schedule(current_year)
        for index, event in schedule.iterrows():
            if event.EventFormat == "conventional":
                format = False
            else:
                format = True
            if event.RoundNumber!=0:
                add_schedule_to_db(int(str(event.year)+str(event.RoundNumber)), event.year, (event.Country + ": "+ event.Location), format, int(str(event.EventDate)[5:7]), int(str(event.EventDate)[8:10]))
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/f1")
async def f1(request: Request):
    races=get_races(datetime.now())
    results={}
    session = fastf1.get_session(races[0].year, races[0].location.split(": ")[1], 'Race')
    session.load()
    results=session.results.head(3)
    top3=str(results[['Position', 'BroadcastName', 'TeamName']]).split("\n")
    top3.pop(0)
    for i in range(len(top3)):
        top3[i]=top3[i].split()
        top3[i].append(get_driver_image(int(top3[i][0])))
    

    return templates.TemplateResponse(
        request=request,
        name="f1.html",
        context={"races": races,
                 "top3": top3},
        
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)






RSS_FEEDS = {
    "https://feeds.bbci.co.uk/sport/football/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/formula1/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/cricket/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/rugby-union/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/rugby-league/rss.xml": "BBC Sport",
    "https://www.abc.net.au/news/feed/51120/rss.xml": "ABC Sport",
}

SPORT_KEYWORDS = {
    "f1", "formula 1", "formula one", "grand prix",
    "nba", "basketball",
    "football", "soccer", "premier league", "champions league", "world cup",
    "nfl",
    "mlb", "baseball",
    "cricket",
    "rugby",
}

BLOCKLIST = {"fantasy", "esports", "e-sports", "wrestling", "wwe", "ufc", "mma", "nascar", "odds", "bets", "betting"}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

SPORT_KEYWORDS: dict[str, set[str]] = {
    "football": {"football", "soccer", "premier league", "champions league", "world cup",
                 "fa cup", "serie a", "la liga", "bundesliga", "ligue 1", "epl"},
    "f1": {"f1", "formula 1", "formula one", "grand prix", "formula1"},
    "cricket": {"cricket", "test match", " odi ", "ipl", "ashes"},
    "rugby league": {"rugby league", "nrl", "super league", "state of origin"},
    "rugby union": {"six nations", "super rugby", "rugby union", "wallabies"},
    "basketball": {"basketball", "nba"},
    "american football": {"nfl", "american football"},
    "baseball": {"mlb", "baseball"},
}