import fastf1
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
fastf1.Cache.enable_cache('fastf1-cache')  # Enable caching for faster data retrieval
schedule = fastf1.get_event_schedule(2023)
print(str(schedule.EventDate[5])[5:7])
print(str(schedule.EventDate[5])[8:10])