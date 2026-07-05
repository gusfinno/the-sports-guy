import logging
import feedparser
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import time
import httpx
import os
from dotenv import load_dotenv
from database import add_constructor_standings_to_db, add_driver_standings_to_db, get_basic_results, get_constructor_standings, get_driver_standings, init_db, get_races, add_schedule_to_db, schedule_exists_for_year, add_drivers_to_db, drivers_exist, clear_drivers, add_race_to_db, get_constructor_id, Stint, results_exist_for_round, clear_results_for_round, add_constructor_to_db, constructors_exist
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup work: initialise the database and load this season's schedule.
    # Kept out of module import so importing `main` (e.g. in tests) has no side effects.
    init_db()
    load_schedule_data()
    yield

app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

def load_leaderboard():
    standings = ergast.get_driver_standings(season='current')
    standings = standings.content[0]
    year = datetime.now().year
    for _, driver in standings.iterrows():
        add_driver_standings_to_db(
            int(driver['driverNumber']),
            year,
            float(driver['points'])
        )
    standings = ergast.get_constructor_standings(season='current')
    standings = standings.content[0]
    for _, constructor in standings.iterrows():
        add_constructor_standings_to_db(
            constructor['constructorName'],
            year,
            float(constructor['points'])
        )

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
            standings.loc[standings['driverNumber'] == int(driver_row['DriverNumber']), 'constructorNames'].values[0][0],
            driver_row['HeadshotUrl'], 
            standings.loc[standings['driverNumber'] == int(driver_row['DriverNumber']), 'driverNationality'].values[0]
            )

def load_constructor_data():
    if constructors_exist():
        return
    constructors = ergast.get_constructor_info(season='current')
    for _, constructor_row in constructors.iterrows():
        add_constructor_to_db(
            constructor_row['constructorName'],
            constructor_row['constructorNationality']
        )

load_dotenv()
api_key = os.getenv("SPORT_API")
API_BASE_URL = "https://v1.formula-1.api-sports.io/competitions"


def load_schedule_data():
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
    past_races, future_races = get_races(datetime.now())
    load_constructor_data()
    load_leaderboard()
    load_driver_data(past_races[-1].round, past_races[-1].year, past_races[-1].location.split(": ")[0])
    if not results_exist_for_round(past_races[-1].round):
        load_race_data(past_races[-1].round, past_races[-1].year, past_races[-1].location.split(": ")[0])
    
    results = get_basic_results(past_races[-1].round)
    results2 = None
    if not future_races:
        results2 = get_basic_results(past_races[-1].round)
        if not results_exist_for_round(past_races[-2].round):
            load_race_data(past_races[-2].round, past_races[-2].year, past_races[-2].location.split(": ")[0])
        results = get_basic_results(past_races[-2].round)
    driver_standings = get_driver_standings(datetime.now().year)
    constructor_standings = get_constructor_standings(datetime.now().year)

    return templates.TemplateResponse(
        request=request,
        name="f1.html",
        context={"past_races": past_races,
                 "future_races": future_races,
                 "results": results,
                 "results2": results2,
                 "driver_standings": driver_standings,
                 "constructor_standings": constructor_standings},
        
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