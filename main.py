#importing everything required
import logging
import feedparser
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import time
import os
from dotenv import load_dotenv
from database import get_future_weather, historic_results_exist_for_round, add_constructor_standings_to_db, add_driver_standings_to_db, add_future_weather, add_historic_information, add_historic_results, add_race_highlights, get_basic_results, get_constructor_standings, get_broad_statistics, get_driver_standings, init_db, get_races, add_schedule_to_db, schedule_exists_for_year, add_drivers_to_db, drivers_exist, clear_drivers, add_race_to_db, get_constructor_id, Stint, results_exist_for_round, add_constructor_to_db, constructors_exist, leader_up_to_date, update_driver_standings, update_constructor_standings, highlight_exists_for_round, get_historic_race, get_historic_results
import fastf1
from fastf1.ergast import Ergast
import pandas as pd
import requests
import threading
from fastapi.responses import JSONResponse
#setting up fastf1 cache to reduce api calls if calls are duplicates
fastf1.Cache.enable_cache('fastf1-cache')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Application starting up...")

#sets up results type to ensure it is in expected format and can be dealt with reliably
ergast = Ergast(
    result_type='pandas', 
    auto_cast=True,
    limit=None
)

#sets up structures for threading
race_jobs = {}
ladder_jobs = {}
past_race_jobs = {}

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

#set up main app
app = FastAPI(lifespan=lifespan)

#use of jinja2 templates set up
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

#the inital load of the leaderboard
def load_leaderboard():
    try:
        verification, round = leader_up_to_date()
        if not verification:
            standings = ergast.get_driver_standings(season='current')
            standings = standings.content[0]
            year = datetime.now().year
            #_ is an empty placeholder value as the first value returned from standings.iterrows() is not used, reducing memory usage
            for _, driver in standings.iterrows():
                add_driver_standings_to_db(
                    int(driver['driverNumber']), #accesses the driverNumber in that dataframe
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
        ladder_jobs[round] = "ready" #status of jobs are maintained for purpose of threading and keeping track of what is running
    except Exception:
        logging.exception("race load failed") #logging failures to be reviewed later
        ladder_jobs[round] = "error"

#updates leaderboard, difference to load_leaderboard are the functions called communicating with the database, here the database is updated rather than added to
def update_leaderboard():
    try:
        verification, round = leader_up_to_date()
        if not verification:
            standings = ergast.get_driver_standings(season='current')
            standings = standings.content[0]
            year = datetime.now().year
            for _, driver in standings.iterrows():
                #update not add
                update_driver_standings(
                    int(driver['driverNumber']),
                    year,
                    float(driver['points']),
                    round
                )
            standings = ergast.get_constructor_standings(season='current')
            standings = standings.content[0]
            for _, constructor in standings.iterrows():
                #update not add
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

#gets the correct lapping of each driver (if necessary)
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
    if not pd.isna(finish_pos) and int(finish_pos) == 1: #checks if finish_position is not a value (eg. NaN) and they finished first
        hours, rem = divmod(race_time.total_seconds(), 3600)
        mins, secs = divmod(rem, 60)
        return f"{int(hours)}:{int(mins):02d}:{secs:06.3f}"
    return f"+{race_time.total_seconds():.3f}s"

#loads race data
def load_race_data(round1: int, year: int):
    try:
        session = fastf1.get_session(year, int(str(round1)[4:]), 'Race')
        session.load(laps=True, telemetry=False, weather=False, messages=False) #only gets laps and results data
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

            time1 = format_race_time(driver_row, total_laps, leader_laps, status)

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
                time1,
                1 if driver_id == fast_lap_id else 0 #boolean for if driver got the fastest lap
            )
        race_jobs[round1] = "ready"
    except Exception:
        logging.exception("race load failed")
        race_jobs[round1] = "error"

#loading individual driver data by iterating through two data frames
def load_driver_data(round1: int, year: int):
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

def get_average_air_temp(weather_data):
    if weather_data is None or weather_data.empty:
        return None
    average = weather_data['AirTemp'].mean()
    if pd.isna(average):
        return None
    return int(round(float(average)))

def get_rainfall(weather_data):
    if weather_data is None or weather_data.empty:
        return None
    wet = weather_data['Rainfall'].mean()
    if pd.isna(wet):
        return None
    return int(round(float(wet) * 100))

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#gets longitude and latitude of race so its weather can be accessed
def find_location(race):
    circuits = ergast.get_circuits(season=race.year, round=int(str(race.round)[4:]))
    if circuits.empty:
        return None
    circuit = circuits.iloc[0]
    return {"latitude": float(circuit['lat']), "longitude": float(circuit['long'])}

WEATHER_HOURS = ("15:00", "16:00")

def load_race_weather(race):
    now = datetime.now()
    race_date = now.replace(month=race.month, day=race.day)
    if (race_date.date() - now.date()).days > 7: #only accepted forecast when 7 days or less out, too inaccurate otherwise
        return None
    date = race_date.strftime("%Y-%m-%d")
    try:
        location = find_location(race)
        if location is None:
            return None
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "hourly": "temperature_2m,precipitation_probability",
                "timezone": "auto",
                "start_date": date,
                "end_date": date
            },
            timeout=10
        )
        response.raise_for_status()
        hourly = response.json().get("hourly") or {}
        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        rain = hourly.get("precipitation_probability") or []

        window_temps = []
        window_rain = []
        for hour in WEATHER_HOURS:
            stamp = f"{date}T{hour}"
            if stamp not in times:
                continue
            index = times.index(stamp)
            if index < len(temps) and temps[index] is not None:
                window_temps.append(temps[index])
            if index < len(rain) and rain[index] is not None:
                window_rain.append(rain[index])
        if not window_temps and not window_rain:
            return None
        weather = {
            #gets average air temp and max chance of rain across typical race time period (3-5pm local time)
            "air_temp": int(round(sum(window_temps) / len(window_temps))) if window_temps else None,
            "chance_of_rain": int(round(max(window_rain))) if window_rain else None
        }
        add_future_weather(
            race.round,
            weather["chance_of_rain"],
            weather["air_temp"],
            int(now.strftime("%Y%m%d"))
        )
        return weather
    except Exception:
        logging.exception("weather lookup failed")
        return None

def load_past_race_data(race):
    try:
        session = fastf1.get_session(race.year-1, race.event, 'Race')
        if session.event.EventName != race.event:
                    return False
        session.load(laps=True, telemetry=False, weather=True, messages=False)
        #includes weather for past race, not just laps and results
        
        results = session.results
        laps = session.laps
        winner = results.loc[results['Position'] == 1, 'DriverNumber']
        if not winner.empty:
            leader_laps = len(laps.pick_drivers(winner.iloc[0]))
        else:
            leader_laps = int(laps.groupby('DriverNumber').size().max()) if not laps.empty else 0

        for _, driver_row in results.iterrows():
            driver_name = driver_row['FullName']
            driver_id = int(driver_row['DriverNumber'])
            constructor = driver_row['TeamName']

            grid_pos = driver_row['GridPosition']
            grid_position = str(int(grid_pos)) if not pd.isna(grid_pos) else 0

            finish_pos = driver_row['Position']
            position = str(int(finish_pos)) if not pd.isna(finish_pos) else 50

            driver_laps = int(driver_row['Laps'])
            status = str(driver_row['Status'])
            time1 = format_race_time(driver_row, driver_laps, leader_laps, status)

            add_historic_results(
                race.round,
                driver_name,
                driver_id,
                constructor,
                position,
                time1,
                grid_position
            )

        weather_data = session.weather_data
        average_air_temp = get_average_air_temp(weather_data)
        rainfall = get_rainfall(weather_data)
        add_historic_information(
            race.round,
            rainfall,
            average_air_temp
        )
        return True

    except Exception:
        logging.exception("race load failed")
        return False


def load_schedule_data():
    current_year = datetime.now().year
    if not schedule_exists_for_year(current_year):
        clear_drivers()
        schedule = fastf1.get_event_schedule(current_year)
        for index, event in schedule.iterrows():
            if event.EventFormat == "conventional": #sets how reponse is formatted
                format = False
            else:
                format = True
            if event.RoundNumber!=0:
                add_schedule_to_db(int(str(event.year)+str(event.RoundNumber)), event.year, event.EventName, str(event.Location + ", " + event.Country), format, int(str(event.EventDate)[5:7]), int(str(event.EventDate)[8:10]))

#accesses the current playlist for Formula 1 highlights and retrieves its video corresponding to the highlight of the race
def update_highlights(round, title):
    url = "https://www.youtube.com/feeds/videos.xml?playlist_id=PLfoNZDHitwjU1j8PiNg17QGDN37d07Rex"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    feed = feedparser.parse(response.content)
    #looks for entry which has event in its title
    target_url = next((entry.yt_videoid for entry in feed.entries if title in entry.title), None)
    #if not found before, scope broadened by looking for just appropriate city/country in title
    if target_url == None:
        target_url = next((entry.yt_videoid for entry in feed.entries if title.split()[0] in entry.title), None)
    if target_url == None:
        logging.warning("no highlights video found for round %s (%s)", round, title)
        return
    add_race_highlights(target_url, round, title)

def ensure_race_loaded(race) -> bool:
    if race_jobs.get(race.round) in ("ready", "error"):
        return True
    if results_exist_for_round(race.round):
        return True
    if race_jobs.get(race.round) != "loading":
        race_jobs[race.round] = "loading"
        #opens a thread to load the race data to ensure not all stacked at once and there is order
        threading.Thread(target=load_race_data, args=(race.round, race.year), daemon=True, name="Loading Race Data").start()
    return False

def load_future_race_page_data(race):
    try:
        load_past_race_data(race)
        load_race_weather(race)
        past_race_jobs[race.round] = "ready"
    except Exception:
        logging.exception("future race load failed")
        past_race_jobs[race.round] = "error"

def weather_up_to_date(race) -> bool:
    now = datetime.now()
    if (now.replace(month=race.month, day=race.day).date() - now.date()).days > 7:
        return True
    weather = get_future_weather(race.round)
    return weather is not None and weather.last_updated == int(now.strftime("%Y%m%d"))

def ensure_past_race_loaded(race) -> bool:
    if past_race_jobs.get(race.round) in ("ready", "error"):
        return True
    if historic_results_exist_for_round(race.round) and weather_up_to_date(race):
        return True
    if past_race_jobs.get(race.round) != "loading":
        past_race_jobs[race.round] = "loading"
        threading.Thread(target=load_future_race_page_data, args=(race,), daemon=True, name="Loading Past Race Data").start()
    return False

def ensure_ladder_loaded() -> bool:
    validation, round = leader_up_to_date()
    if validation:
        return True
    if ladder_jobs.get(round) != "loading":
        ladder_jobs[round] = "loading"
        threading.Thread(target=update_leaderboard, daemon=True, name="Loading Leaderboard Data").start()
    return False

#a continual function which runs through the app in the background,
# once a day it makes sure all the races have been loaded to lower chance user is forced to wait for results when a page is loaded
def maintain_consistency():
    while True:
        try:
            #only searches past races so future races is not needed
            past_races, _ = get_races(datetime.now())
            #prioritises most recent races
            for race in reversed(past_races):
                if not highlight_exists_for_round(race.round):
                    update_highlights(race.round, race.event)
                if not results_exist_for_round(race.round):
                    load_race_data(race.round, race.year)
                    time.sleep(2)
            ensure_ladder_loaded()
        except Exception:
            logging.exception("sweep failed")
        time.sleep(60 * 60 * 24)


#connects response to each template

#home page
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

#main f1 home page, has ladder, results for the most recent race, past races and recent races
@app.get("/f1")
async def f1(request: Request):
    past_races, future_races = get_races(datetime.now())
    loadingRace1 = False
    loadingRace2 = False
    loadingLeaderboard = False
    results = []
    results2 = None
    #starts background thread if something isn't loaded to ensure page can load quickly for user
    #when it is loaded it sends a response to webpage that it can reload the appropriate section
    if not ensure_ladder_loaded():
        loadingLeaderboard = True
    if not drivers_exist():
        load_driver_data(past_races[-1].round, past_races[-1].year)
    if not results_exist_for_round(past_races[-1].round):
        loadingRace1 = True
        ensure_race_loaded(past_races[-1])
    else:
        results = get_basic_results(past_races[-1].round)
    results2 = None
    #if there are no more races in the season, insstead of future races, the most recent 2 races have their podiums loaded 
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

    #jinja2 template reponse with template and the information i want to pass into it with the name i will refer to it by in the template and what it is refered to in the function
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

#specific overview for a past race
@app.get("/f1/past_race/{round1}")
async def f1_past_race(round1: int, request: Request):
    loadingRace = False
    results = []
    past_races, future_races = get_races(datetime.now())
    index = next((i for i, r in enumerate(past_races) if r.round == round1), None)
    race = past_races.pop(index) if index is not None else None
    if race != None:
        if not results_exist_for_round(race.round):
            loadingRace = True
            ensure_race_loaded(race)
        else:
            results = get_basic_results(race.round)
    else:
        #if the race entered in is not actually a finished race, it provides a 404 error code
        return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"error_code": 404},
                status_code=404
            )
    return templates.TemplateResponse(
            request=request,
            name="past_races.html",
            context={"past_races": past_races,
                     "future_races": future_races,
                     "race": race,
                     "results": results,
                     "loading": loadingRace},
        )

#specific overview for a future race
@app.get("/f1/future_race/{round1}")
async def f1_future_race(round1: int, request: Request):
    loadingRace = False
    information = []
    driver_information = []
    weather = None
    past_races, future_races = get_races(datetime.now())
    index = next((i for i, r in enumerate(future_races) if r.round == round1), None)
    race = future_races.pop(index) if index is not None else None
    if race != None:
        if ensure_past_race_loaded(race):
            information = get_historic_race(round1)
            driver_information = get_historic_results(round1)
            weather = get_future_weather(round1)
        else:
            loadingRace = True
    else:
        #if the race entered in is not actually a future race, it provides a 404 error code
        return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"error_code": 404},
                status_code=404
            )
        
    return templates.TemplateResponse(
            request=request,
            name="upcoming_races.html",
            context={"past_races": past_races,
                     "future_races": future_races,
                     "race": race,
                     "information": information,
                     "driver_information": driver_information,
                     "weather": weather,
                     "loading": loadingRace},

        )
#these functions provide the status for the loading of data if it was not already stored when the user was accessing the page
@app.get("/f1/status/{round1}")
async def f1_status(round1: int):
    placeholder = results_exist_for_round(round1)
    return JSONResponse({"ready": placeholder,
                         "error": race_jobs.get(round1) == "error"})

@app.get("/f1/future_status/{round1}")
async def f1_future_status(round1: int):
    state = past_race_jobs.get(round1)
    return JSONResponse({"ready": state in ("ready", "error"),
                         "error": state == "error"})

@app.get("/f1/status_ladder/{round1}")
async def f1_status_ladder(round1: int):
    placeholder = leader_up_to_date()[0]
    return JSONResponse({"ready": placeholder,
                         "error": ladder_jobs.get(round1) == "error"})

#main start
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)