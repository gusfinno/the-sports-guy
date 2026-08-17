import fastf1
from fastf1.ergast import Ergast
fastf1.Cache.enable_cache('fastf1-cache') 

session = fastf1.get_session(2026, "Monaco", 'Race')
session.load()
results = session.results
print(results)