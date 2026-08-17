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
from database import add_constructor_standings_to_db, add_driver_standings_to_db, delete_most_recent_round_for_testing, get_basic_results, get_constructor_standings, get_broad_statistics, get_driver_standings, init_db, get_races, add_schedule_to_db, schedule_exists_for_year, add_drivers_to_db, drivers_exist, clear_drivers, add_race_to_db, get_constructor_id, Stint, results_exist_for_round, clear_results_for_round, add_constructor_to_db, constructors_exist, leader_up_to_date, update_driver_standings, update_constructor_standings
import fastf1
from fastf1.ergast import Ergast
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import requests
import threading
from fastapi.responses import JSONResponse
fastf1.Cache.enable_cache('fastf1-cache')  # Enable caching for faster data retrieval

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Application starting up...")

ergast = Ergast(
    result_type='pandas',  # or 'raw'
    auto_cast=True,
    limit=None
)

race_jobs = {}
ladder_jobs = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup work: initialise the database and load this season's schedule.
    # Kept out of module import so importing `main` (e.g. in tests) has no side effects.
    init_db()
    load_schedule_data()
    load_constructor_data()
    load_leaderboard()
    threading.Thread(target=maintain_consistency, daemon=True, name="consistency").start()
    yield

app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

def load_leaderboard():
    try:
        verification, round = leader_up_to_date()
        if not verification:
            standings = ergast.get_driver_standings(season='current')
            standings = standings.content[0]
            year = datetime.now().year
            for _, driver in standings.iterrows():
                add_driver_standings_to_db(
                    int(driver['driverNumber']),
                    year,
                    float(driver['points']),
                    round
                )
            standings = ergast.get_constructor_standings(season='current')
            standings = standings.content[0]
            for _, constructor in standings.iterrows():
                add_constructor_standings_to_db(
                    constructor['constructorName'],
                    year,
                    float(constructor['points']),
                    round
                )
        ladder_jobs[round] = "ready"
    except Exception:
        logging.exception("race load failed")
        ladder_jobs[round] = "error"

def update_leaderboard():
    try:
        verification, round = leader_up_to_date()
        print(round)
        if not verification:
            standings = ergast.get_driver_standings(season='current')
            standings = standings.content[0]
            year = datetime.now().year
            for _, driver in standings.iterrows():
                update_driver_standings(
                    int(driver['driverNumber']),
                    year,
                    float(driver['points']),
                    round
                )
            standings = ergast.get_constructor_standings(season='current')
            standings = standings.content[0]
            for _, constructor in standings.iterrows():
                update_constructor_standings(
                    constructor['constructorName'],
                    year,
                    float(constructor['points']),
                    round
                )
        ladder_jobs[round] = "ready"
    except Exception:
        logging.exception("race load failed")
        ladder_jobs[round] = "error"

def format_race_time(driver_row, laps_completed, leader_laps, status):

    if status.startswith("+") and "Lap" in status:
        return status

    classified = str(driver_row['ClassifiedPosition']).isdigit()
    laps_down = leader_laps - laps_completed
    if classified and laps_down > 0:
        if laps_down == 1:
            return f"+{laps_down} Lap"
        else:
            return f"+{laps_down} Laps"

    race_time = driver_row['Time']
    if pd.isna(race_time):
        return status

    finish_pos = driver_row['Position']
    if not pd.isna(finish_pos) and int(finish_pos) == 1:
        hours, rem = divmod(race_time.total_seconds(), 3600)
        mins, secs = divmod(rem, 60)
        return f"{int(hours)}:{int(mins):02d}:{secs:06.3f}"
    return f"+{race_time.total_seconds():.3f}s"


def load_race_data(round1: int, year: int):
    try:
        session = fastf1.get_session(year, int(str(round1)[4:]), 'Race')
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        results = session.results
        laps = session.laps
        fastest_lap = session.laps.pick_fastest()
        fast_lap_id = int(fastest_lap["DriverNumber"]) if fastest_lap is not None else None

        winner = results.loc[results['Position'] == 1, 'DriverNumber']
        if not winner.empty:
            leader_laps = len(laps.pick_drivers(winner.iloc[0]))
        else:
            leader_laps = int(laps.groupby('DriverNumber').size().max()) if not laps.empty else 0

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

            time2 = format_race_time(driver_row, total_laps, leader_laps, status)

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
                time2,
                1 if driver_id == fast_lap_id else 0
            )
        race_jobs[round1] = "ready"
    except Exception:
        logging.exception("race load failed")
        race_jobs[round1] = "error"


def load_driver_data(round1: int, year: int, location: str):
    session = fastf1.get_session(year, int(str(round1)[4:]), 'Race')
    session.load(laps=True, telemetry=False, weather=False, messages=False)
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


def ensure_race_loaded(race) -> bool:
    if results_exist_for_round(race.round):
        return True
    if race_jobs.get(race.round) != "loading":
        race_jobs[race.round] = "loading"
        threading.Thread(target=load_race_data, args=(race.round, race.year), daemon=True, name="Loading Race Data").start()
    return False

def ensure_ladder_loaded(race) -> bool:
    validation, round = leader_up_to_date()
    if validation:
        return True
    if ladder_jobs.get(round) != "loading":
        ladder_jobs[round] = "loading"
        threading.Thread(target=update_leaderboard, daemon=True, name="Loading Leaderboard Data").start()
    return False

def maintain_consistency():
    while True:
        try:
            past_races, _ = get_races(datetime.now())
            for race in reversed(past_races):
                if not results_exist_for_round(race.round):
                    load_race_data(race.round, race.year)
                    time.sleep(2)
            update_leaderboard()
        except Exception:
            logging.exception("sweep failed")
        time.sleep(60 * 60 * 24)



@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/f1")
async def f1(request: Request):
    past_races, future_races = get_races(datetime.now())
    loadingRace1 = False
    loadingRace2 = False
    loadingLeaderboard = False
    results = []
    results2 = None
    if not drivers_exist():
        load_driver_data(past_races[-1].round, past_races[-1].year, past_races[-1].location.split(": ")[0])
    if not results_exist_for_round(past_races[-1].round):
        loadingRace1 = True
        ensure_race_loaded(past_races[-1])
    else:
        results = get_basic_results(past_races[-1].round)
    results2 = None
    if not future_races:
        results2 = results
        if not results_exist_for_round(past_races[-2].round):
            loadingRace2 = loadingRace1
            ensure_race_loaded(past_races[-2])
        else:
            results = get_basic_results(past_races[-2].round)
    driver_standings = get_driver_standings(datetime.now().year)
    constructor_standings = get_constructor_standings(datetime.now().year)
    statistics = get_broad_statistics(datetime.now().year)

    return templates.TemplateResponse(
        request=request,
        name="f1.html",
        context={"past_races": past_races,
                 "future_races": future_races,
                 "results": results,
                 "results2": results2,
                 "driver_standings": driver_standings,
                 "constructor_standings": constructor_standings,
                 "loading": loadingRace1,
                 "loading2": loadingRace2,
                 "loadingLeaderboard": loadingLeaderboard,
                 "statistics": statistics},
        
    )

@app.get("/f1/race/{round1}")
async def f1_round(round1: int, request: Request):
    loadingRace = False
    results = []
    past_races, future_races = get_races(datetime.now())
    index = next((i for i, r in enumerate(past_races) if r.round == round1), None)
    race = past_races.pop(index) if index is not None else None
    if not results_exist_for_round(race.round):
        loadingRace = True
        ensure_race_loaded(race)
    else:
        results = get_basic_results(race.round)
    return templates.TemplateResponse(
            request=request,
            name="f1_round.html",
            context={"past_races": past_races,
                     "future_races": future_races,
                     "race": race,
                     "results": results,
                     "loading": loadingRace},

        )


@app.get("/f1/status/{round1}")
async def f1_status(round1: int):
    placeholder = results_exist_for_round(round1)
    return JSONResponse({"ready": placeholder,
                         "error": race_jobs.get(round1) == "error"})

@app.get("/f1/status_ladder/{round1}")
async def f1_status_ladder(round1: int):
    placeholder = leader_up_to_date()[0]
    return JSONResponse({"ready": placeholder,
                         "error": ladder_jobs.get(round1) == "error"})

@app.post("/f1/delete")
async def f1_status_ladder():
    delete_most_recent_round_for_testing()
    print("Deleted most recent round for testing.")
    return {"message": f"Done"}


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