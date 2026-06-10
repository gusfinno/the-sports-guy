import logging
import feedparser
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import httpx
import os
from dotenv import load_dotenv
from database import init_db


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
SPORT_BASE_URL = "https://v3.football.api-sports.io"

# Sport-specific feeds (no keyword filtering needed)
RSS_FEEDS_TARGETED = {
    "https://feeds.bbci.co.uk/sport/football/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/formula1/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/cricket/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/rugby-union/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/rugby-league/rss.xml": "BBC Sport",
    "https://feeds.bbci.co.uk/sport/basketball/rss.xml": "BBC Sport",
    "https://www.skysports.com/rss/12120": "Sky Sports",
    "https://www.skysports.com/rss/12041": "Sky Sports",
    "https://www.skysports.com/rss/12039": "Sky Sports",
}

# General feeds — filtered by keyword
RSS_FEEDS_GENERAL = {
    "https://www.abc.net.au/news/feed/51120/rss.xml": "ABC Sport",
    "https://www.theage.com.au/rss/sport.xml": "The Age",
    "https://www.smh.com.au/rss/sport.xml": "SMH",
    "https://www.cbssports.com/rss/headlines/": "CBS Sports",
}

_SPORT_KEYWORDS = {
    "f1", "formula 1", "formula one", "grand prix",
    "nba", "basketball",
    "football", "soccer", "premier league", "champions league", "world cup",
    "nfl",
    "mlb", "baseball",
    "cricket",
    "rugby",
}

_BLOCKLIST = {"fantasy", "esports", "e-sports", "wrestling", "wwe", "ufc", "mma", "nascar", "odds", "bets", "betting"}

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Maps URL path fragments to a sport label
_FEED_URL_SPORT = {
    "football": "football",
    "formula1": "f1",
    "cricket": "cricket",
    "rugby-union": "rugby",
    "rugby-league": "rugby",
    "basketball": "basketball",
}

# Keyword sets for each sport (checked against title + summary)
_SPORT_KEYWORD_MAP: dict[str, set[str]] = {
    "football": {"football", "soccer", "premier league", "champions league", "world cup",
                 "fa cup", "serie a", "la liga", "bundesliga", "ligue 1", "epl", "transfer window"},
    "f1": {"f1", "formula 1", "formula one", "grand prix", "formula1"},
    "cricket": {"cricket", "test match", " odi ", "ipl", "ashes"},
    "rugby": {"rugby", "six nations", "super rugby", "rugby league", "rugby union"},
    "basketball": {"basketball", "nba"},
    "american football": {"nfl", "american football"},
    "baseball": {"mlb", "baseball"},
}

def _classify_sport(entry, feed_url: str) -> str:
    for fragment, sport in _FEED_URL_SPORT.items():
        if fragment in feed_url:
            return sport
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    for sport, keywords in _SPORT_KEYWORD_MAP.items():
        if any(kw in text for kw in keywords):
            return sport
    return "other"

def _extract_image(entry) -> str | None:
    if getattr(entry, "media_thumbnail", None):
        return entry.media_thumbnail[0].get("url")
    if getattr(entry, "media_content", None):
        return entry.media_content[0].get("url")
    if entry.get("enclosures"):
        enc = entry["enclosures"][0]
        return enc.get("href") or enc.get("url")
    return None

def _matches_sport(entry) -> bool:
    title = entry.get("title", "").lower()
    if any(b in title for b in _BLOCKLIST):
        return False
    text = title + " " + entry.get("summary", "").lower()
    return any(kw in text for kw in _SPORT_KEYWORDS)

def fetch_news(limit: int = 5, sport: str | None = None) -> list[dict]:
    articles = []
    seen_titles: set[str] = set()
    all_feeds = {**RSS_FEEDS_TARGETED, **RSS_FEEDS_GENERAL}

    for url, source in all_feeds.items():
        filtered = url in RSS_FEEDS_GENERAL
        try:
            r = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=10)
            feed = feedparser.parse(r.text)
        except Exception as e:
            logging.warning(f"Failed to fetch feed {url}: {e}")
            continue

        for entry in feed.entries:
            if filtered and not _matches_sport(entry):
                continue
            title = entry.get("title", "")
            key = title.lower().strip()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            articles.append({
                "title": title,
                "link": entry.get("link", "#"),
                "image": _extract_image(entry),
                "published": entry.get("published_parsed"),
                "source": source,
                "sport": _classify_sport(entry, url),
            })

    articles.sort(key=lambda a: a["published"] or 0, reverse=True)
    if sport:
        articles = [a for a in articles if a["sport"] == sport]
    return articles[:limit]

@app.get("/")
async def home(request: Request):
    init_db()
    news = fetch_news()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"news": news}
    )
    
@app.get("/football")
async def football(request: Request):
    news = fetch_news(limit=3, sport="football")
    return templates.TemplateResponse(
        request=request,
        name="football.html",
        context={"news": news},
    )
# #queries for a specific movie based on its id returning the movie and the ai's reccomendations to the html
# @app.get("/movie/{movie_id}")
# async def movie_page(request: Request, movie_id: int):
#     movie = get_movie(movie_id)
#     return templates.TemplateResponse(
#         "movie.html", {"request": request, 
#                        "movie": movie}
#     )



#search page which calls the tmdb api and then passes the results onto the html as a list of Movies
# @app.get("/search")
# async def search(request: Request, query: str):
#     try:
#         async with httpx.AsyncClient() as client:
#             response = await client.get(
#                 f"{TMDB_BASE_URL}/search/movie",
#                 params={
#                     "api_key": TMDB_API_KEY,
#                     "query": query,
#                     "include_adult": "false",
#                     "language": "en-US",
#                     "page": 1,
#                 },
#             )
#             response.raise_for_status()  # Raise HTTPStatusError for bad responses (4xx or 5xx)

#             response_data = response.json()
#             if "results" not in response_data or not isinstance(response_data["results"], list):
#                 logging.error(f"Unexpected response format from TMDb for query '{query}': 'results' key missing or not a list.")
#                 raise HTTPException(status_code=500, detail="Unexpected response format from TMDb.")

#             results = response_data["results"]
            
            
#             movies = [
#                 Movie(
#                     id=movie["id"],
#                 title=movie["title"],
#                 year=movie["release_date"][:4] if movie.get("release_date") else None,
#                 poster_path=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
#                 if movie.get("poster_path")
#                 else None,
#                 overview=movie["overview"],
#                 votes=movie["vote_average"],
#             )
#             for movie in results[:5]  # Limit to 5 results
#         ]

#         return templates.TemplateResponse(
#             "search_results.html",
#             {"request": request, "movies": movies, "query": query},
#         )
#     except httpx.RequestError as e:
#         logging.error(f"TMDb API request error for query '{query}': {e}")
#         raise HTTPException(status_code=503, detail="Could not connect to the movie service.")
#     except httpx.HTTPStatusError as e:
#         logging.error(f"TMDb API error for query '{query}': Status {e.response.status_code}")
#         raise HTTPException(status_code=e.response.status_code, detail="Failed to fetch movies from TMDb.")


# #deletes the movie by calling sql function
# @app.post("/delete-movie/{movie_id}")
# async def delete_item(movie_id: int) -> dict[str, Movie | list[Movie]]:
#     movies=get_all_movies()
#     total_ids=[]
#     for movie in movies:
#         total_ids.append(movie.id)
#     if movie_id not in total_ids:
#         raise HTTPException (
#             status_code=404, detail=f"Item with {movie_id=} does not exist"
#         )
    
    
#     delete_movie_from_db(movie_id)
#     return RedirectResponse(url="/", status_code=303)
#updates the movies rating based on id and using sql function
# @app.post("/update-movie")
# async def add_movie(
#     movie_id: int = Form(...),
#     rating: int = Form(...),
# ):
#     if rating < 1 or rating > 5:
#         raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

#     update_movie_in_db(movie_id, rating)
#     logging.info(f"Movie (ID: {movie_id}) changed rating to: {rating}.")

#     return RedirectResponse(url="/", status_code=303)
#main loop
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
