import sqlite3
import json
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

class Stint(BaseModel):
    tire: str
    laps: int

class Driver(BaseModel):
    id: int
    broadcast_name: str
    first_name: str
    last_name: str
    constructor_id: int
    url: str
    points: float

class Result(BaseModel):
    round: int
    driver_id: int
    first_name: str
    last_name: str
    constructor_name: str
    grid_position: int
    position: int
    stints: Optional[List[Stint]]
    overtakes: Optional[int]
    laps: int
    status: str
    url: str

class Constructor(BaseModel):
    id: int
    name: str
    driver_1_id: Optional[int] = None
    driver_2_id: Optional[int] = None

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
            (id INTEGER PRIMARY KEY,
             broadcast_name TEXT NOT NULL,
             first_name TEXT NOT NULL,
             last_name TEXT NOT NULL,
             constructor_id INTEGER NOT NULL,
             url TEXT NOT NULL,
             points FLOAT NOT NULL);
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS results
            (round INTEGER NOT NULL,
             driver_id INTEGER NOT NULL,
             constructor_id INTEGER NOT NULL,
             grid_position INTEGER NOT NULL,
             position INTEGER NOT NULL,
             stints TEXT NOT NULL,
             overtakes INTEGER NOT NULL,
             laps INTEGER NOT NULL,
             status TEXT NOT NULL);
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS constructors
            (id INTEGER PRIMARY KEY,
             name TEXT NOT NULL,
             driver_1_id INTEGER,
             driver_2_id INTEGER);
        """)
        conn.commit()
    finally:
        if not supplied_conn and conn:  # If we opened it, we close it
            conn.close()



#ADD functions

def add_race_to_db(
    round: int,
    driver_id: int,
    constructor_id: int,
    grid_position: int,
    position: int,
    stints: List[Stint],
    overtakes: int,
    laps: int,
    status: int
):  
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO results (round, driver_id, constructor_id, grid_position, position, stints, overtakes, laps, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (round, driver_id, constructor_id, grid_position, position, json.dumps([s.model_dump() for s in stints]), overtakes, laps, status)
        )

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
    id: int,
    broadcast_name: str,
    first_name: str,
    last_name: str,
    constructor_name: str,
    url: str,
    points: int
):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id FROM constructors WHERE name = ?", (constructor_name,))
        row = c.fetchone()
        if row:
            constructor_id = row[0]
        else:
            c.execute(
            "INSERT INTO constructors (name, driver_1_id) VALUES (?, ?)", (constructor_name, id))
            constructor_id = c.lastrowid
        c.execute(
            "INSERT OR IGNORE INTO drivers (id, broadcast_name, first_name, last_name, constructor_id, url, points) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id, broadcast_name, first_name, last_name, constructor_id, url, points)
        )
        c.execute(
            "UPDATE constructors SET driver_2_id = ? WHERE id = ?", (id, constructor_id)
        )
        conn.commit()
    

#GET functions


def get_races(date: datetime.date) -> List[F1Race]:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()

        c.execute("SELECT * FROM f1_races WHERE year = ? AND (month < ?) OR (month == ? AND day <= ?) ORDER BY round ASC", (date.year, date.month, date.month, date.day))
        races = [
            F1Race(
                round=row[0], year=row[1], location=row[2], sprint=row[3], month=row[4], day=row[5]
            )
            
            for row in c.fetchall()
        ]

        if races == []:
            raise ValueError(f"No races yet this season?")


        c.execute("SELECT * FROM f1_races WHERE round == ? ORDER BY round DESC LIMIT 1", (races[-1].round + 1,))
        next_race = c.fetchone()
        if next_race is not None:
            races.append(F1Race(round=next_race[0], year=next_race[1], location=next_race[2], sprint=next_race[3], month=next_race[4], day=next_race[5]))

        return races

def get_driver(id: int) -> Optional[Driver]:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM drivers WHERE id = ?", (id,))
        row = c.fetchone()
        if row:
            return Driver(id=row[0], broadcast_name=row[1], first_name=row[2], last_name=row[3], constructor_id=row[4], url=row[5], points=row[6])
        return None

def get_driver_image(id: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT url FROM drivers WHERE id = ?", (id,))
        result = c.fetchone()
        return result[0] if result else None

def get_constructor_id(driver_id: int) -> int:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT constructor_id FROM drivers WHERE id = ?", (driver_id,))
        result = c.fetchone()
        return result[0] if result else 0

def get_basic_results(round: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("""
                  SELECT r.round, r.driver_id, d.first_name, d.last_name, c.name, r.grid_position,r.position, r.laps, r.status, d.url, r.stints, r.overtakes
                  FROM results r
                  JOIN drivers
                   d ON d.id = r.driver_id
                  JOIN constructors c ON c.id = r.constructor_id
                  WHERE r.round = ?
                  ORDER BY r.position ASC
                  """, (round,))
        results = [
            Result(
                round=row[0], driver_id=row[1], first_name=row[2], last_name=row[3], constructor_name=row[4], grid_position=row[5], position=row[6], laps=row[7], status=row[8], url=row[9], stints=[Stint(**s) for s in json.loads(row[10])] if row[10] else None, overtakes=row[11]
            )
            
            for row in c.fetchall()
        ]
        return results


#Housekeeping functions
def schedule_exists_for_year(year: int) -> bool:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM f1_races WHERE year = ? LIMIT 1", (year,))
        return c.fetchone() is not None

def results_exist_for_round(round: int) -> bool:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM results WHERE round = ? LIMIT 1", (round,))
        return c.fetchone() is not None

def drivers_exist() -> bool:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM drivers LIMIT 1")
        return c.fetchone() is not None

def clear_drivers():
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM drivers")
        conn.commit()

def clear_results_for_round(round: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM results WHERE round = ?", (round,))
        conn.commit()