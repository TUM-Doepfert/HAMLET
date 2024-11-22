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
from hamlet.executor.grids.grid_base import GridBase

# TODO: Considerations
# - None so far


class Hydrogen(GridBase):

    def __init__(self, grid_db, tasks: pl.DataFrame, database):

        # Call the super class
        super().__init__(grid_db=grid_db, tasks=tasks, database=database)
