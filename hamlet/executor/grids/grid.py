__author__ = "MarkusDoepfert"
__credits__ = ""
__license__ = ""
__maintainer__ = "MarkusDoepfert"
__email__ = "markus.doepfert@tum.de"

# This file is in charge of handling the grids in the execution of the scenario

# Imports
import os
import pandas as pd
import polars as pl
import numpy as np
import time
import logging
import traceback
from datetime import datetime
import pandapower as pp
import hamlet.constants as c
from hamlet.executor.utilities.database.database import Database

# Types of grids (add your own if others are created here)
from hamlet.executor.grids.electricity.electricity import Electricity
from hamlet.executor.grids.heat.heat import Heat
from hamlet.executor.grids.hydrogen.hydrogen import Hydrogen


class Grid:

    def __init__(self, grid_db, tasks: pl.DataFrame, grid_type: str, database: Database):

        self.types = {
            c.G_ELECTRICITY: Electricity,
            c.G_HEAT: Heat,
            c.G_H2: Hydrogen,
        }

        # Instance of the grid class
        self.grid = self.types[grid_type](grid_db=grid_db, tasks=tasks, database=database)

    def execute(self):
        """Executes the grid"""

        return self.grid.execute()
