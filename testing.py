import fastf1
from fastf1.ergast import Ergast
fastf1.Cache.enable_cache('fastf1-cache') 

session = fastf1.get_session(2026, "Hungary", 'Race')
session.load()

fastest_lap = session.laps.pick_fastest()
print(fastest_lap["DriverNumber"])