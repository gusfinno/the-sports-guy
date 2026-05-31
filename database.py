import sqlite3
from typing import List
from pydantic import BaseModel
from typing import Optional

DATABASE_NAME = ".db"

#defines the attributes and data types for each attribute for which each movie/actor/director will follow
class Movie(BaseModel):
    id: int
    title: str
    year: Optional[str] = None
    poster_path: Optional[str] = None
    rating: Optional[int] = None
    overview: Optional[str] = None
    votes: Optional[float]= None
    directors: Optional[list] = []
    actors: Optional[list] = []

def init_db(conn=None):  # Allow passing a connection
    supplied_conn = bool(conn)
    if not conn:
        conn = sqlite3.connect(DATABASE_NAME)

    try:
        c = conn.cursor() #checks to see if a table exists and if not creates one
        c.execute("""
            CREATE TABLE IF NOT EXISTS movies
            (id INTEGER PRIMARY KEY,
             title TEXT NOT NULL,
             year TEXT,
             poster_path TEXT,
             rating INTEGER NOT NULL, 
             overview TEXT NOT NULL, 
             votes FLOAT NOT NULL);
        """)
        conn.commit()
    finally:
        if not supplied_conn and conn:  # If we opened it, we close it
            conn.close()
    
#gets an individual movie using an id and defines it using base class
def get_movie(movie_id: int) -> Movie:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        
        # Get the movie
        c.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
        row = c.fetchone()
        
        if not row:
            raise ValueError(f"Movie with id {movie_id} not found")
        
        # Get directors for this movie
        c.execute("SELECT name FROM directors WHERE movie_id = ?", (movie_id,))
        directors = [row[0] for row in c.fetchall()]
        
        # Get actors for this movie
        c.execute("SELECT name FROM actors WHERE movie_id = ?", (movie_id,))
        actors = [row[0] for row in c.fetchall()]
        
        return Movie(
            id=row[0],
            title=row[1],
            year=row[2],
            poster_path=row[3],
            rating=row[4],
            overview=row[5],
            votes=row[6],
            directors=directors,
            actors=actors
        )

