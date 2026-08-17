import fastf1
from fastf1.ergast import Ergast
fastf1.Cache.enable_cache('fastf1-cache') 

session = fastf1.get_session(2026, "Hungary", 'Race')
session.load(laps=False, telemetry=False, weather=False, messages=True)
messages = session.race_control_messages
penalties = messages[messages['Category'] == 'Penalty']
# or filter by message text containing 'penalty'
penalties = messages[messages['Message'].str.contains('Penalty', case=False, na=False)]
print(penalties)