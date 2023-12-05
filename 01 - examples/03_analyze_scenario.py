import sys
sys.path.append("..")  # Add the parent directory to the Python path for execution outside of an IDE
from hamlet import Analyzer

# Path to the results folder (relative or absolute)
path = "../05 - results/example_small"

# Create the analyzer object
sim = Analyzer(path)

# Plot the general analysis (more details in the documentation)
sim.plot_general_analysis()
