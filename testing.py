import fastf1
import pandas as pd
from pydantic import BaseModel
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
fastf1.Cache.enable_cache('fastf1-cache')  # Enable caching for faster data retrieval

from fastf1.ergast import Ergast

ergast = Ergast(
    result_type='pandas',  # or 'raw'
    auto_cast=True,
    limit=None
)
standings = ergast.get_constructor_standings(season='current')
standings = standings.content[0]

# # Get current driver standings
# standings = ergast.get_driver_standings(season='current')
# standings = standings.content[0]
print(standings)