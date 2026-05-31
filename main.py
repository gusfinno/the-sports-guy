import logging
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import httpx
import os
from dotenv import load_dotenv
from database import init_db, get_all_movies, add_movie_to_db, Movie, delete_movie_from_db, update_movie_in_db, ranked_movies, recent_movies, popular_movies, popular_actors, popular_directors, get_all_movies_titles, get_all_movies_titles_rating, get_movie
from openai import AsyncOpenAI


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Application starting up...")

app = FastAPI()
# init_db() # Initialize database at startup - This will be handled by tests or explicit startup event
logging.info("Database initialization will be handled by tests or explicit startup event.")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

load_dotenv()

TMDB_API_KEY = "ba96d8323c5e259ff89d125dc697c94c"
if not TMDB_API_KEY:
    raise ValueError(
        "TMDB_API_KEY not found in environment variables. Please set it in your .env file or environment."
    )
TMDB_BASE_URL = "https://api.themoviedb.org/3"

CHAT_API_KEY = "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"
async_client = AsyncOpenAI(api_key=CHAT_API_KEY)
init_db()

#AI calls to get movie reccomendations

async def ai_movie(movie_title):

    prompt = f"""
You are a movie recommendation assistant.

Given the movie: "{movie_title}", suggest **4 similar movies** that:
- Are not already present in this database: {get_all_movies_titles()}
- Are similar in theme, genre, or tone to the original movie.
- Are well-known and critically appreciated (no obscure suggestions).
- Have a known release year.

Format the 4 recommendations exactly like this:
Movie Title (Year)
Movie Title (Year)
Movie Title (Year)
Movie Title (Year)

Do not include any explanation or commentary — just return the 4 formatted lines.
Do not include the input movie or any movies from the database list.
"""

    response = await async_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content.strip()


async def ai_collection():
    collection = get_all_movies_titles()

    prompt = f"""
You are a movie recommendation assistant.

Based on this movie collection: {collection}

Suggest 6 additional movies that:
- Are not already in the collection above.
- Would strongly appeal to someone who enjoys the movies listed.
- Are similar in tone, genre, or theme to the overall collection.
- Are well-known, critically appreciated, and have a known release year.

Format the 6 recommendations exactly like this:
Movie Title (Year)
Movie Title (Year)
Movie Title (Year)
Movie Title (Year)
Movie Title (Year)
Movie Title (Year)

Do not include any commentary, explanation, or repeats from the collection.
Do not include the words "Recommended movies" or any list numbers or bullet points.
"""

    response = await async_client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content.strip()

#formats the ai reccomendations and then queries tmdb to get the rest of the required information while making sure the right movie is found
async def format_ai_reccomendation(reccomendation):
    movies = []
    movies2 = reccomendation.split("\n")
    existing_titles = {title.strip().lower() for title in get_all_movies_titles()}

    for movie in movies2:
        try:
            hello = movie.strip().rsplit("(", 1)
            if len(hello) != 2:
                continue

            movie_title = hello[0].strip()
            year = hello[1].replace(")", "").strip()
            full_title = f"{movie_title} ({year})".lower()

            if full_title in existing_titles:
                continue
            #queries tmdb for the possible movies chatgpt meant
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{TMDB_BASE_URL}/search/movie",
                    params={
                        "api_key": TMDB_API_KEY,
                        "query": movie_title,
                        "include_adult": "false",
                        "language": "en-US",
                        "page": 1,
                    },
                )
                #response.raise_for_status()  # Raise HTTPStatusError for bad responses (4xx or 5xx)

                response_data = response.json()
                if "results" not in response_data or not isinstance(response_data["results"], list):
                    logging.error(f"Unexpected response format from TMDb for query '{movie_title}': 'results' key missing or not a list.")
                    raise HTTPException(status_code=500, detail="Unexpected response format from TMDb.")

                results = response_data["results"]
                
                if not results:
                    logging.warning(f"No results found for movie '{movie_title}'")
                    continue
                
                selected_movie = None
                #finds the movie chatgpt meant
                for result in results:
                    if result["release_date"][:4] == year[:4]:
                        selected_movie=result
                        break


                if not selected_movie:
                    selected_movie = results[0]

                movie1 = Movie(
                    id=selected_movie["id"],
                    title=selected_movie["title"],
                    year=selected_movie["release_date"][:4] if selected_movie.get("release_date") else None,
                    poster_path=f"https://image.tmdb.org/t/p/w500{selected_movie['poster_path']}"
                    if selected_movie.get("poster_path")
                    else None,
                    overview=selected_movie["overview"],
                    votes=selected_movie["vote_average"],
                )
                

                movies.append(movie1)

        except httpx.RequestError as e:
            logging.error(f"TMDb API request error for query '{movie_title}': {e}")
            continue
        except httpx.HTTPStatusError as e:
            logging.error(f"TMDb API error for query '{movie_title}': Status {e.response.status_code}")
            continue
    return movies
    
#queries for a specific movie based on its id returning the movie and the ai's reccomendations to the html
@app.get("/movie/{movie_id}")
async def movie_page(request: Request, movie_id: int):
    movie = get_movie(movie_id)
    return templates.TemplateResponse(
        "movie.html", {"request": request, 
                       "movie": movie,
                        "recomendations":  await format_ai_reccomendation(await ai_movie(movie.title))}
    )




#main home page which calls the function to get all of the movies so that the html can show all of them and calls the functions for ai reccomendations
@app.get("/")
async def home(request: Request):
    #makes sure the database is all set up
    init_db()
    movies = get_all_movies()
    reccomend_bot = await format_ai_reccomendation(await ai_collection())
    print(get_all_movies_titles())
    return templates.TemplateResponse(
        "index.html", {"request": request, 
                       "movies": movies,
                       "reccomended_movies": reccomend_bot
                       }
    )

#the stats page which calls the sql functions as variables for html
@app.get("/stats")
async def movie_page(request: Request):
    return templates.TemplateResponse(
        "stats.html", {"request": request, 
                       "movies_ranked": ranked_movies(),
                       "movies_recent": recent_movies(),
                       "popular": popular_movies(),  
                       "actors": popular_actors(),
                       "directors": popular_directors()}
    )

#search page which calls the tmdb api and then passes the results onto the html as a list of Movies
@app.get("/search")
async def search(request: Request, query: str):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TMDB_BASE_URL}/search/movie",
                params={
                    "api_key": TMDB_API_KEY,
                    "query": query,
                    "include_adult": "false",
                    "language": "en-US",
                    "page": 1,
                },
            )
            response.raise_for_status()  # Raise HTTPStatusError for bad responses (4xx or 5xx)

            response_data = response.json()
            if "results" not in response_data or not isinstance(response_data["results"], list):
                logging.error(f"Unexpected response format from TMDb for query '{query}': 'results' key missing or not a list.")
                raise HTTPException(status_code=500, detail="Unexpected response format from TMDb.")

            results = response_data["results"]
            
            
            movies = [
                Movie(
                    id=movie["id"],
                title=movie["title"],
                year=movie["release_date"][:4] if movie.get("release_date") else None,
                poster_path=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
                if movie.get("poster_path")
                else None,
                overview=movie["overview"],
                votes=movie["vote_average"],
            )
            for movie in results[:5]  # Limit to 5 results
        ]

        return templates.TemplateResponse(
            "search_results.html",
            {"request": request, "movies": movies, "query": query},
        )
    except httpx.RequestError as e:
        logging.error(f"TMDb API request error for query '{query}': {e}")
        raise HTTPException(status_code=503, detail="Could not connect to the movie service.")
    except httpx.HTTPStatusError as e:
        logging.error(f"TMDb API error for query '{query}': Status {e.response.status_code}")
        raise HTTPException(status_code=e.response.status_code, detail="Failed to fetch movies from TMDb.")

#adds the specified movie taking the variables passed by the html and then queries tmdb for the cast information which requires a different api call then the other movie information
@app.post("/add-movie")
async def add_movie(
    movie_id: int = Form(...),
    title: str = Form(...),
    year: str = Form(None),
    poster_path: str = Form(None),
    overview: str = Form(None),
    votes: float = Form(None),
    rating: int = Form(...),
):#ensures the rating is in the acceptable range
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    
    async with httpx.AsyncClient() as client:
        try:
            credits_response = await client.get(
                f"{TMDB_BASE_URL}/movie/{movie_id}/credits",
                params={"api_key": TMDB_API_KEY}
            )
            credits_response.raise_for_status()
            credits_data = credits_response.json()
            
            directors = [
                person["name"] 
                for person in credits_data.get("crew", []) 
                if person["job"] == "Director"
            ]

            director_images = [
                f"https://image.tmdb.org/t/p/w185{person['profile_path']}" 
                if person.get("profile_path") else None
                for person in credits_data.get("crew", []) 
                if person["job"] == "Director"
            ]
            
            cast = credits_data.get("cast", [])[:5]
            actors = [actor["name"] for actor in cast]
            
            actor_images = [
                f"https://image.tmdb.org/t/p/w185{actor['profile_path']}" 
                if actor.get("profile_path") else None
                for actor in cast
            ]

        except Exception as e:
            logging.error(f"Error fetching credits for movie {movie_id}: {e}")
            directors = []
            actors = []
            actor_images=[]
            director_images=[]
    
    add_movie_to_db(movie_id, title, year, poster_path, rating, overview, votes, directors, director_images, actors, actor_images)
    logging.info(f"Movie '{title}' (ID: {movie_id}) added with rating: {rating}.")
    return RedirectResponse(url="/", status_code=303)
#deletes the movie by calling sql function
@app.post("/delete-movie/{movie_id}")
async def delete_item(movie_id: int) -> dict[str, Movie | list[Movie]]:
    movies=get_all_movies()
    total_ids=[]
    for movie in movies:
        total_ids.append(movie.id)
    if movie_id not in total_ids:
        raise HTTPException (
            status_code=404, detail=f"Item with {movie_id=} does not exist"
        )
    
    
    delete_movie_from_db(movie_id)
    return RedirectResponse(url="/", status_code=303)
#updates the movies rating based on id and using sql function
@app.post("/update-movie")
async def add_movie(
    movie_id: int = Form(...),
    rating: int = Form(...),
):
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    update_movie_in_db(movie_id, rating)
    logging.info(f"Movie (ID: {movie_id}) changed rating to: {rating}.")

    return RedirectResponse(url="/", status_code=303)
#main loop
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
