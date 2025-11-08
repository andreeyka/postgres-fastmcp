import warnings
from importlib.metadata import version

from .config import app_settings
from .logger import configure_logging


# Suppress deprecation warnings if configured
# Must be set early to catch warnings during imports
if app_settings.suppress_deprecation_warnings:
    # Suppress websockets deprecation warnings (including submodules)
    warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*websockets.*")
    # Also filter by module path for more specific control
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.legacy")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn.protocols.websockets")
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, module="uvicorn.protocols.websockets.websockets_impl"
    )

# Configure logging with Rich
# Set up logging early so all modules can use it
configure_logging(
    level="INFO",
    omit_repeated_times=False,  # Disable time grouping
)

__version__ = version("postgres-mcp")
