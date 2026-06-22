import sqlite3
from typing import List
from pydantic import BaseModel
from typing import Optional
import datetime

DATABASE_NAME = "sports.db"

#defines the attributes and data types for each attribute for which each movie/actor/director will follow
class F1Race(BaseModel):
    round: int
    year: int
    location: str
    sprint: bool = False
    month: int
    day: int

class Driver(BaseModel):
    number: int
    broadcast_name: str
    first_name: str
    last_name: str
    url: str

def init_db(conn=None):  # Allow passing a connection
    supplied_conn = bool(conn)
    if not conn:
        conn = sqlite3.connect(DATABASE_NAME)

    try:
        c = conn.cursor() #checks to see if a table exists and if not creates one
        c.execute("""
            CREATE TABLE IF NOT EXISTS f1_races
            (round INTEGER PRIMARY KEY,
             year INTEGER NOT NULL,
             location TEXT NOT NULL,
             sprint BOOLEAN NOT NULL,
             month INTEGER NOT NULL,
             day INTEGER NOT NULL);
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS drivers
            (number INTEGER PRIMARY KEY,
             broadcast_name TEXT NOT NULL,
             first_name TEXT NOT NULL,
             last_name TEXT NOT NULL,
             url TEXT NOT NULL);
        """)
        conn.commit()
    finally:
        if not supplied_conn and conn:  # If we opened it, we close it
            conn.close()

#gets an individual movie using an id and defines it using base class
def get_races(date: datetime.date) -> List[F1Race]:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        races = []

        c.execute("SELECT * FROM f1_races WHERE (month < ?) OR (month == ? AND day <= ?) ORDER BY round DESC LIMIT 1", (date.month, date.month, date.day))
        last_race = c.fetchone()

        if last_race is None:
            raise ValueError(f"No races yet this season?")

        races.append(F1Race(round=last_race[0], year=last_race[1], location=last_race[2], sprint=last_race[3], month=last_race[4], day=last_race[5]))

        c.execute("SELECT * FROM f1_races WHERE round == ? ORDER BY round DESC LIMIT 1", (last_race[0] + 1,))
        next_race = c.fetchone()
        if next_race is not None:
            races.append(F1Race(round=next_race[0], year=next_race[1], location=next_race[2], sprint=next_race[3], month=next_race[4], day=next_race[5]))

        return races

def add_schedule_to_db(
    round: int,
    year: int,
    location: str,
    sprint: bool,
    month: int,
    day: int
):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO f1_races (round, year, location, sprint, month, day) VALUES (?, ?, ?, ?, ?, ?)",
            (round, year, location, sprint, month, day),
        )
        conn.commit()
def add_drivers_to_db(
    number: int,
    broadcast_name: str,
    first_name: str,
    last_name: str,
    url: str
):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO drivers (number, broadcast_name, first_name, last_name, url) VALUES (?, ?, ?, ?, ?)",
            (number, broadcast_name, first_name, last_name, url),
        )
        conn.commit()

def schedule_exists_for_year(year: int) -> bool:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM f1_races WHERE year = ? LIMIT 1", (year,))
        return c.fetchone() is not None

def drivers_exist() -> bool:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM drivers LIMIT 1")
        return c.fetchone() is not None

def clear_drivers():
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM drivers")
        conn.commit()

def get_driver_image(number: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT url FROM drivers WHERE number = ?", (number,))
        result = c.fetchone()
        return result[0] if result else None