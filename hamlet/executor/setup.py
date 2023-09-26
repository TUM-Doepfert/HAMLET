__author__ = "MarkusDoepfert"
__credits__ = ""
__license__ = ""
__maintainer__ = "MarkusDoepfert"
__email__ = "markus.doepfert@tum.de"

import os
from tqdm import tqdm
import shutil
import time
import warnings
import multiprocessing as mp
import pandas as pd
from ruamel.yaml import YAML
from pprint import pprint
import json
import polars as pl
pl.enable_string_cache(True)
from hamlet import functions as f
# from numba import njit, jit
import pandapower as pp
import concurrent.futures
from typing import Callable
from datetime import datetime
from hamlet.executor.agents.agent import Agent
from hamlet.executor.markets.markets import Markets
from hamlet.executor.grids.grids import Grids
from hamlet.executor.utilities.database.database import Database
import hamlet.constants as c
# pl.enable_string_cache(True)

# TODO: Considerations
# - Use Callables to create a sequence for all agents in executor: this was similarly done in the creator_backup and should be continued for consistency
# - Possible packages for multiprocessing: multiprocessing, joblib, threading (can actually be useful when using not just pure python)
# - Decrease file size wherever possible (define data types, shorten file lengths, etc.) -> this needs to occur in the scenario creation
# - Load all files into the RAM and not read/save as in lemlab to increase performance
# - Use polars instead of pandas to increase performance --> finding: polars is faster as long as lazy evaluation is used. Otherwise pandas 2.0 can keep up well (depending on use case)
# - Always check if numba can help improve performance


class Executor:

    progress_bar = tqdm()

    def __init__(self, path_scenario, name: str = None, num_workers: int = None, overwrite_sim: bool = True):

        # Paths
        self.name = name if name else os.path.basename(path_scenario)  # Name of the scenario
        self.path_scenario = os.path.abspath(path_scenario)  # Path to the scenario folder
        self.root_scenario = os.path.dirname(self.path_scenario)  # Path to the root folder of the scenario
        self.path_results = None  # Path to the results folder

        # Scenario general information and configuration
        self.general = None
        self.config = None

        # Scenario timetable
        self.timetable = None

        # Scenario type (sim or in the future also rts)
        self.type = None  # set in self.__prepare_scenario()

        # Database containing all information
        self.database = Database(self.path_scenario)  # TODO: Will be structured according to structure and contain agent, market and grid tables and data

        # Scenario structure
        self.structure = {}  # TODO: this will need to contain more information than just the path. Also: above and below markets to know where to look for the data

        # Number of workers for parallelization
        self.num_workers = num_workers

        # Thread pool for parallelization
        self.pool = None

        # Overwrites the results folder if it already exists
        self.overwrite = overwrite_sim

    def run(self):
        """Runs the simulation"""

        self.setup()

        self.execute()

        self.stop()

    def setup(self):
        """Sets up the scenario before execution"""

        self.__prepare_scenario()

        self.__setup_database()

    def execute(self):
        """Executes the scenario

        """

        # Get number of logical processors (for parallelization)
        if not self.num_workers:
            self.num_workers = os.cpu_count() - 1  # logical processors (threads) - 1
        # num_workers = mp.cpu_count() - 1  # physical processors - 1
        # Apparently this calculates the number of usable CPUs: len(os.sched_getaffinity(0)) (see os manual)

        # Setup up the thread pool for parallelization
        if self.num_workers > 1:
            self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers)  # TODO: Benchmark with ProcessPoolExecutor

        # Loop through the timetable and execute the tasks for each market for each timestamp
        # Note: The design assumes that there is nothing to be gained for the simulation to run in between market
        #   timestamps. Therefore, the simulation is only executed for the market timestamps
        # Iterate over timetable by timestamp
        timetable = self.timetable.collect()

        # TODO: Add progress bar @Jiahe
        self.progress_bar.reset(total=len(timetable.partition_by('timestamp')))
        self.progress_bar.set_description_str(desc='Start execution')

        for timestamp in timetable.partition_by('timestamp'):
            # Wait for the timestamp to be reached if the simulation is to be carried out in real-time
            if self.type == 'rts':
                self.__wait_for_ts(timestamp.iloc[0, 0])

            # get current timestamp as string item for progress bar
            timestamp_str = str(timestamp.select(c.TC_TIMESTAMP).sample(n=1).item())

            # Iterate over timestamp by region
            for region in timestamp.partition_by('region'):
                # get current region as string item for progress bar
                region_str = str(region.select(c.TC_REGION).sample(n=1).item())
                region = region.lazy()

                # update progress bar description
                self.progress_bar.set_description_str('Executing timestamp ' + timestamp_str + ' for region ' + region_str
                                                 + ': ')

                # Execute the agents and market in parallel or sequentially
                if self.pool:
                    # Execute the agents for this market
                    self.__execute_agents_parallel(tasklist=region)

                    # Execute the market
                    self.__execute_market_parallel(tasklist=region)
                else:
                    # Execute the agents for this market
                    self.__execute_agents(tasklist=region)

                    # Execute the market
                    self.__execute_markets(tasklist=region)

            # Calculate the grids for the current timestamp (calculated together as they are connected)
            self.progress_bar.set_description_str('Executing timestamp ' + timestamp_str + ' for grid: ')
            self.__execute_grids()

            self.progress_bar.update(1)

        # Cleanup the thread pool
        if self.pool:
            self.pool.shutdown()

    def __execute_agents_parallel(self, tasklist: pl.LazyFrame):
        """Executes all agent tasks for all agents in parallel"""

        # Get the data of the agents that are part of the tasklist
        agents = self.database.get_agent_data(region=tasklist.collect()[0, 'region'])

        # Define the function to be executed in parallel
        def tasks(agent):
            # Execute the agent
            agent.execute()

        # Create a list to store the agents
        agents_list = []

        # Iterate over the tasklist and populate the agents_list
        for agent_type, agent in agents.items():
            for agent_id, data in agent.items():
                agents_list.append(Agent(data, tasklist, agent_type, self.database))

        # Submit the agents for parallel execution
        results = [self.pool.submit(tasks, agent) for agent in agents_list]

        # Wait for all agents to complete
        concurrent.futures.wait(results)

        print('results parallel:')
        for result in results:
            print(result.bids_offers.collect())

        # Post the agent data back to the database
        self.database.post_agents_to_region(region=tasklist.collect()[0, 'region'], agents=results)
        print('Exiting...')
        exit()

    def __execute_market_parallel(self, tasklist: pl.DataFrame):
        """Executes the market tasks in parallel"""

        # Define the function to be executed in parallel
        def tasks(market):
            # Create an instance of the Markets class and execute its tasks
            Markets(market).execute()

        # Create a list to store the markets
        markets_list = []

        # Iterate over the tasklist and populate the markets_list
        for market in tasklist:
            markets_list.append(market)

        # Submit the markets for parallel execution
        futures = [self.pool.submit(tasks, market) for market in markets_list]

        # Wait for all markets to complete
        concurrent.futures.wait(futures)

    def __execute_agents(self, tasklist: pl.LazyFrame):
        """Executes all agent tasks for all agents sequentially
        """

        # Get the data of the agents that are part of the tasklist
        agents = self.database.get_agent_data(region=tasklist.collect()[0, 'region'])

        # Create a list to store the results
        results = []

        # Iterate over the agents and execute them sequentially
        for agent_type, agent in agents.items():
            for agent_id, data in agent.items():
                # Create an instance of the Agents class and execute its tasks
                results.append(Agent(agent_type=agent_type, data=agent[agent_id], timetable=tasklist,
                                     database=self.database).execute())

        # print('results sequential:')
        # for result in results:
        #     print(result.bids_offers.collect())

        # Post the agent data back to the database
        self.database.post_agents_to_region(region=tasklist.collect()[0, 'region'], agents=results)

    def __execute_markets(self, tasklist: pl.LazyFrame):

        # Turn tasklist into dataframe to be able to iterate over it
        tasklist = tasklist.collect()

        # Create a list to store the results
        results = []

        # Iterate over tasklist row by row
        for tasks in tasklist.iter_rows(named=True):
            # Get the market data for the current market
            market = self.database.get_market_data(region=tasks['region'],
                                                   market_type=tasks['market'],
                                                   market_name=tasks['name'])
            # Create an instance of the Markets class and execute its tasks
            results.append(Markets(data=market, tasks=tasks, database=self.database).execute())

        # Post the agent data back to the database
        self.database.post_agents_to_region(region=tasklist.collect()[0, 'region'], agents=results)

    def __execute_grids(self):

        return
        # Pass info to grids class and execute its tasks
        Grids().execute()

    def pause(self):
        """Pauses the simulation"""
        raise NotImplementedError("Pause functionality not implemented yet")

    def resume(self):
        """Resumes the simulation"""
        raise NotImplementedError("Resume functionality not implemented yet")

    def save_results(self):
        """Saves the (current) results of the simulation"""
        ...

    def stop(self):
        """Cleans up the scenario after execution"""

        self.save_results()

    def __prepare_scenario(self):
        """Prepares the scenario"""

        # Load general information and configuration
        self.general = f.load_file(os.path.join(self.path_scenario, 'general', 'general.json'))
        self.config = f.load_file(os.path.join(self.path_scenario, 'config', 'config_setup.yaml'))

        # Load timetable
        self.timetable = f.load_file(os.path.join(self.path_scenario, 'general', 'timetable.ft'),
                                     df='polars', method='lazy')

        # Load scenario structure
        self.structure = self.general['structure']

        # Set the results path
        self.path_results = os.path.join(self.config['paths']['results'], self.name)
        # Check if the results folder exists and stop simulation if overwrite is set to False
        if os.path.exists(self.path_results) and self.overwrite is False:
            raise FileExistsError(f"Results folder already exists. "
                                  f"Set overwrite to True to overwrite the results folder.")
        # Copy the scenario folder to the results folder
        # Note: For the execution the files in the results folder are used and not the ones in the scenario folder
        f.copy_folder(self.path_scenario, self.path_results)

        # Create a gurobi env file in the cwd
        with open("gurobi.env", "w") as file:
            # Write the desired setting to the file
            file.write("OutputFlag 0\n"
                       "LogToConsole 0\n")

    def __setup_database(self):
        """Creates a database connector object"""

        self.database.setup_database(self.structure)

    @staticmethod
    def __wait_for_ts(timestamp):
        """Waits until the target timestamp is reached"""

        # Get current datetime
        current_datetime = datetime.now()

        # Calculate time difference
        time_difference = (timestamp - current_datetime).total_seconds()

        # Wait until the target time is reached
        if time_difference > 0:
            time.sleep(time_difference)
        elif time_difference < 0:
            warnings.warn(f"Target time is in the past: {timestamp} vs. {current_datetime}")

        return
