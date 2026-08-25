"""PROJECT FIRE - AI-native business operating system.

FIRE is a system that DISCOVERS, EVALUATES, VALIDATES, DESIGNS, BUILDS,
LAUNCHES, SELLS, OPERATES and OPTIMIZES multiple AI-enabled businesses.

Architecture (canonical):
    GITHUB  = canonical agent library + FIRE source
    LOCAL   = development / control / cache node
    RUNTIME = on-demand agent activation (lazy retrieval)

Only the agents required for the current mission are loaded/activated.
"""

__version__ = "0.1.0"
