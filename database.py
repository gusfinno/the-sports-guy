import sqlite3
import json
from typing import List
from matplotlib.pyplot import table
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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
    broadcast_name: Optional[str] = None
    first_name: str
    last_name: str
    constructor_id: Optional[int] = None
    constructor_name: Optional[str] = None
    url: str
    points: Optional[float] = None
    nationality: str

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
    time: str
    url: str

class Constructor(BaseModel):
    id: int
    name: str
    driver_1_id: Optional[int] = None
    driver_2_id: Optional[int] = None
    nationality: str
    points: Optional[float]

class Statistics(BaseModel):
    id: int
    first_name: str
    last_name: str
    url: str
    overtakes: int
    poles: int
    wins: int
    podiums: int
    laps: int
    fastest_laps: int

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
             nationality TEXT NOT NULL);
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
             status TEXT NOT NULL,
             time TEXT NOT NULL,
             fastest_lap INTEGER,
             PRIMARY KEY (round, driver_id));
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS constructors
            (id INTEGER PRIMARY KEY,
             name TEXT NOT NULL,
             driver_1_id INTEGER,
             driver_2_id INTEGER,
             nationality TEXT NOT NULL);
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS driver_standings
            (id INTEGER PRIMARY KEY,
             year INTEGER NOT NULL,
             points FLOAT NOT NULL,
             last_updated INTEGER);
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS constructor_standings
            (id INTEGER PRIMARY KEY,
             year INTEGER NOT NULL,
             points FLOAT NOT NULL,
             last_updated INTEGER);
        """)
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
    status: int,
    time: str,
    fastest_lap: int
):  
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO results (round, driver_id, constructor_id, grid_position, position, stints, overtakes, laps, status, time, fastest_lap) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (round, driver_id, constructor_id, grid_position, position, json.dumps([s.model_dump() for s in stints]), overtakes, laps, status, time, fastest_lap)
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

def add_constructor_to_db(
    name: str,
    nationality: str
):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO constructors (name, nationality) VALUES (?, ?)",
            (name, nationality)
        )
        conn.commit()

def add_driver_standings_to_db(
    id: int,
    year: int,
    points: float,
    round: int,
):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO driver_standings (id, year, points, last_updated) VALUES (?, ?, ?, ?)",
            (id, year, points, round)
        )
        conn.commit()

def add_constructor_standings_to_db(
    name: str,
    year: int,
    points: float,
    round: int,
):
    id = get_constructor_id(name)
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO constructor_standings (id, year, points, last_updated) VALUES (?, ?, ?, ?)",
            (id, year, points, round)
        )
        conn.commit()

def add_drivers_to_db(
    id: int,
    broadcast_name: str,
    first_name: str,
    last_name: str,
    constructor_name: str,
    url: str,
    nationality: str
):
    with sqlite3.connect(DATABASE_NAME) as conn:
        constructor_id = get_constructor_id(constructor_name)
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO drivers (id, broadcast_name, first_name, last_name, constructor_id, url, nationality) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id, broadcast_name, first_name, last_name, constructor_id, url, nationality)
        )
        c.execute("SELECT driver_1_id, driver_2_id FROM constructors WHERE id = ?", (constructor_id,))
        row = c.fetchone()
        if row and id not in (row[0], row[1]):
            if row[0] is None:
                c.execute("UPDATE constructors SET driver_1_id = ? WHERE id = ?", (id, constructor_id))
            else:
                c.execute("UPDATE constructors SET driver_2_id = ? WHERE id = ?", (id, constructor_id))
        conn.commit()

#UPDATE functions

def update_driver_standings(
    id: int,
    year: int,
    points: float,
    round: int,
):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            f"UPDATE driver_standings SET points = ?, last_updated = ? WHERE id = ? AND year = ?",
            (points, round, id, year)
        )
        conn.commit()

def update_constructor_standings(
    name: str,
    year: int,
    points: float,
    round: int,
):
    id = get_constructor_id(name)
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute(
            f"UPDATE constructor_standings SET points = ?, last_updated = ? WHERE id = ? AND year = ?",
            (points, round, id, year)
        )
        conn.commit()
    

#GET functions


def get_races(date: datetime.date):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()

        c.execute("SELECT * FROM f1_races WHERE year = ? AND (month < ? OR (month == ? AND day < ?)) ORDER BY round ASC", (date.year, date.month, date.month, date.day))
        past_races = [
            F1Race(
                round=row[0], year=row[1], location=row[2], sprint=row[3], month=row[4], day=row[5]
            )
            
            for row in c.fetchall()
        ]

        if past_races == []:
            raise ValueError(f"No races yet this season?")


        c.execute("SELECT * FROM f1_races WHERE year = ? AND (month > ? OR (month == ? AND day >= ?)) ORDER BY round ASC", (date.year, date.month, date.month, date.day))
        future_races = [
            F1Race(
                round=row[0], year=row[1], location=row[2], sprint=row[3], month=row[4], day=row[5]
            )
            
            for row in c.fetchall()
        ]

        if future_races == []:
            future_races = None

        return past_races, future_races

def get_1_race():
    date = datetime.now()
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()

        c.execute("SELECT round FROM f1_races WHERE year = ? AND (month < ? OR (month == ? AND day < ?)) ORDER BY round DESC LIMIT 1", (date.year, date.month, date.month, date.day))
        row = c.fetchone()
        most_recent_round = row[0]
            
        return most_recent_round

def get_constructor_id(key):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        if isinstance(key, str):
            c.execute("SELECT id FROM constructors WHERE name = ?", (key,))
        else:
            c.execute("SELECT constructor_id FROM drivers WHERE id = ?", (key,))
        result = c.fetchone()
        return result[0] if result else 0

def get_basic_results(round: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT r.round, r.driver_id, d.first_name, d.last_name, c.name, r.grid_position,r.position, r.laps, r.status, d.url, r.stints, r.overtakes, r.time
            FROM results r
            JOIN drivers
            d ON d.id = r.driver_id
            JOIN constructors c ON c.id = r.constructor_id
            WHERE r.round = ?
            ORDER BY r.position ASC
            """, (round,))
        results = [
            Result(
                round=row[0], driver_id=row[1], first_name=row[2], last_name=row[3], constructor_name=row[4], grid_position=row[5], position=row[6], laps=row[7], status=row[8], url=row[9], stints=[Stint(**s) for s in json.loads(row[10])] if row[10] else None, overtakes=row[11], time=row[12]
            )
            
            for row in c.fetchall()
        ]
        return results

def get_driver(id: int) -> Optional[Driver]:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM drivers WHERE id = ?", (id,))
        row = c.fetchone()
        if row:
            return Driver(id=row[0], broadcast_name=row[1], first_name=row[2], last_name=row[3], constructor_id=row[4], url=row[5], nationality=row[6])
        return None
    
def get_driver_standings(year: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT ds.id, d.first_name, d.last_name, c.name, d.url, ds.points, d.nationality 
            FROM driver_standings ds 
            JOIN drivers d ON ds.id = d.id
            JOIN constructors c ON d.constructor_id = c.id
            WHERE year = ?
            ORDER BY ds.points DESC
            """, (year,))
        standings = [
            Driver(id=row[0], first_name=row[1], last_name=row[2], constructor_name=row[3], url=row[4], points=row[5], nationality=row[6])
            for row in c.fetchall()
        ]
        return standings
    
def get_constructor_standings(year: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT cs.id, c.name, c.nationality, cs.points
            FROM constructor_standings cs 
            JOIN constructors c ON cs.id = c.id
            WHERE year = ?
            ORDER BY cs.points DESC
            """, (year,))
        standings = [
            Constructor(id=row[0], name=row[1], nationality=row[2], points=row[3])
            for row in c.fetchall()
        ]
        return standings

def get_broad_statistics(year: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT r.driver_id,
                d.first_name,
                d.last_name,
                d.url,
                SUM(r.overtakes),
                SUM(r.grid_position = 1),
                SUM(r.position = 1),
                SUM(r.position <= 3),
                SUM(r.laps),
                COALESCE(SUM(r.fastest_lap), 0)
            FROM results r
            JOIN f1_races f ON f.round = r.round
            JOIN drivers d ON d.id = r.driver_id
            WHERE f.year = ?
            GROUP BY r.driver_id
            ORDER BY SUM(r.position = 1) DESC
            """, (year,))
        statistics = [
            Statistics(id=row[0], first_name=row[1], last_name=row[2], url=row[3], overtakes=row[4], poles=row[5], wins=row[6], podiums=row[7], laps=row[8], fastest_laps=row[9])
            for row in c.fetchall()
        ]
        return statistics



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
        c.execute("SELECT 1 FROM drivers LIMIT 1")
        return c.fetchone() is not None
    
def constructors_exist() -> bool:
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM constructors LIMIT 1")
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

def leader_up_to_date():
    round = get_1_race()
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM driver_standings WHERE last_updated = ? LIMIT 1", (round,))
        return [c.fetchone() is not None, round]


def delete_most_recent_round_for_testing():
    with sqlite3.connect(DATABASE_NAME) as conn:
        c = conn.cursor()
        c.execute("DROP TABLE results")
        conn.commit()
        return