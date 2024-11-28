__author__ = "MarkusDoepfert"
__credits__ = ""
__license__ = ""
__maintainer__ = "MarkusDoepfert"
__email__ = "markus.doepfert@tum.de"

# Imports
import hamlet.constants as c
from hamlet.executor.agents.agent_base import AgentBase


class Sfh(AgentBase):

    def __init__(self, agent, timetable, market, grid_commands):

        # Type of agent
        super().__init__(agent_type=c.A_SFH, agent=agent, timetable=timetable, market=market,
                         grid_commands=grid_commands)
