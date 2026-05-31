import os
os.environ["TMDB_API_KEY"] = "test_api_key" # Set dummy API key for tests

import pytest
import httpx
from fastapi.testclient import TestClient
from main import app
import database

import sqlite3

@pytest.fixture(scope="function")
def client(monkeypatch):
    db_uri = "file::memory:?cache=shared"
    monkeypatch.setattr(database, "DATABASE_NAME", db_uri)
    
    # Establish a connection that will keep the shared DB alive AND initialize it.
    keep_alive_conn = sqlite3.connect(db_uri)
    database.init_db(conn=keep_alive_conn) # Pass the connection

    with TestClient(app) as c:
        yield c
    
    keep_alive_conn.close()

def test_home_empty_db(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Movie Ratings" in response.text
    # Assuming an empty database shows a specific message or lacks movie items
    assert "No movies found." not in response.text # Or some other assertion

def test_home_with_movies(client):
    # Add a movie directly to the in-memory DB using database.add_movie_to_db
    database.add_movie_to_db(1, "Test Movie", "2023", "/poster.jpg", 4)
    response = client.get("/")
    assert response.status_code == 200
    assert "Test Movie" in response.text
    assert "2023" in response.text

def test_add_movie_success(client):
    response = client.post("/add-movie", data={
        "movie_id": "123", "title": "New Movie", "year": "2024", 
        "poster_path": "/new_poster.jpg", "rating": "5"
    }) # TestClient handles redirects by default; allow_redirects is not a valid param for .post()

    assert len(response.history) == 1  # Check that there was one redirect
    assert response.history[0].status_code == 303 # The redirect itself
    assert response.status_code == 200 # The page after redirect (home page)

    # Verify movie in DB
    movies = database.get_all_movies()
    assert len(movies) == 1
    assert movies[0].title == "New Movie"

def test_add_movie_invalid_rating(client):
    response = client.post("/add-movie", data={
        "movie_id": "124", "title": "Bad Rating Movie", "year": "2024", 
        "poster_path": "/poster.jpg", "rating": "0" # Invalid rating
    })
    assert response.status_code == 400 
    assert "Rating must be between 1 and 5" in response.text

def test_search_success(client, mocker):
    mock_tmdb_response = {
        "results": [
            {"id": 789, "title": "Found Movie", "release_date": "2024-01-01", "poster_path": "/found.jpg"}
        ]
    }
    mock_get = mocker.patch("httpx.AsyncClient.get")
    mock_response = mocker.Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_tmdb_response
    # Make the .get() call return this mock_response; note it's an async context
    mock_get.return_value = mock_response


    response = client.get("/search?query=Found")
    assert response.status_code == 200
    assert "Found Movie" in response.text
    mock_get.assert_called_once()

def test_search_tmdb_request_error(client, mocker):
    mocker.patch("httpx.AsyncClient.get", side_effect=httpx.RequestError("Network error"))
    response = client.get("/search?query=Fail")
    assert response.status_code == 503
    assert "Could not connect to the movie service" in response.text

def test_search_tmdb_status_error(client, mocker):
    mock_response = mocker.Mock(spec=httpx.Response)
    mock_response.status_code = 401 # Unauthorized
    # The request object is needed by HTTPStatusError
    mock_request = mocker.Mock(spec=httpx.Request)
    mocker.patch("httpx.AsyncClient.get", side_effect=httpx.HTTPStatusError("API Error", request=mock_request, response=mock_response))
    response = client.get("/search?query=ApiFail")
    assert response.status_code == 401 
    assert "Failed to fetch movies from TMDb" in response.text
