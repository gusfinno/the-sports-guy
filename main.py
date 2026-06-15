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
from database import init_db
import fastf1
import pandas as pd
import matplotlib.pyplot as plt
fastf1.Cache.enable_cache('cache')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Application starting up...")

app = FastAPI()
# init_db() # Initialize database at startup - This will be handled by tests or explicit startup event
logging.info("Database initialization will be handled by tests or explicit startup event.")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

load_dotenv()
api_key = os.getenv("SPORT_API")
API_BASE_URL = "https://v1.formula-1.api-sports.io/competitions"


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

            

@app.get("/")
async def home(request: Request):
    init_db()
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/f1")
async def nrl(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="f1.html"
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)