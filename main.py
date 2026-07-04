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
from database import get_basic_results, init_db, get_races, add_schedule_to_db, schedule_exists_for_year, add_drivers_to_db, drivers_exist, clear_drivers, get_driver_image, add_race_to_db, get_constructor_id, get_driver, Stint, results_exist_for_round, clear_results_for_round
import fastf1
from fastf1.ergast import Ergast
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import requests
fastf1.Cache.enable_cache('fastf1-cache')  # Enable caching for faster data retrieval

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Application starting up...")

ergast = Ergast(
    result_type='pandas',  # or 'raw'
    auto_cast=True,
    limit=None
)

app = FastAPI()
# init_db() # Initialize database at startup - This will be handled by tests or explicit startup event

logging.info("Database initialization will be handled by tests or explicit startup event.")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

def load_race_data(round1: int, year: int, location: str):
    session = fastf1.get_session(year, location, 'Race')
    session.load()
    results = session.results
    laps = session.laps

    for _, driver_row in results.iterrows():
        driver_id = int(driver_row['DriverNumber'])
        constructor_id = get_constructor_id(driver_id)

        grid_pos = driver_row['GridPosition']
        grid_position = str(int(grid_pos)) if not pd.isna(grid_pos) else 0

        finish_pos = driver_row['Position']
        position = str(int(finish_pos)) if not pd.isna(finish_pos) else 23

        status = str(driver_row['Status'])

        driver_laps = laps.pick_drivers(driver_row['DriverNumber'])

        stints = driver_laps[["Driver", "Stint", "Compound", "LapNumber"]]
        stints = stints.groupby(["Driver", "Stint", "Compound"])
        stints = stints.count().reset_index()
        stints = [Stint(tire=row['Compound'], laps=row['LapNumber']) for _, row in stints.iterrows()]

        lap_positions = driver_laps['Position'].dropna()
        overtakes = int((lap_positions.diff() < 0).sum())

        total_laps = len(driver_laps)

        add_race_to_db(
            round1,
            driver_id,
            constructor_id,
            grid_position,
            position,
            stints,
            overtakes,
            total_laps,
            status,
        )

def load_driver_data(round1: int, year: int, location: str):
    if drivers_exist():
        return
    session = fastf1.get_session(year, location, 'Race')
    session.load()
    results = session.results
    standings = ergast.get_driver_standings(season='current')
    standings = standings.content[0]

    for _, driver_row in results.iterrows():
        add_drivers_to_db(
            int(driver_row['DriverNumber']), 
            driver_row['BroadcastName'], 
            driver_row['FirstName'], 
            driver_row['LastName'], 
            driver_row['TeamName'], 
            driver_row['HeadshotUrl'], 
            float(standings.loc[standings['driverNumber'] == int(driver_row['DriverNumber']), 'points'].iloc[0])
            )

load_dotenv()
api_key = os.getenv("SPORT_API")
API_BASE_URL = "https://v1.formula-1.api-sports.io/competitions"





init_db()
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






@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/f1")
async def f1(request: Request):
    races=get_races(datetime.now())
    load_driver_data(races[-2].round, races[-2].year, races[-2].location.split(": ")[0])
    if not results_exist_for_round(races[-2].round):
        load_race_data(races[-2].round, races[-2].year, races[-2].location.split(": ")[0])
    results = get_basic_results(races[-2].round)

    return templates.TemplateResponse(
        request=request,
        name="f1.html",
        context={"races": races,
                 "results": results},
        
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