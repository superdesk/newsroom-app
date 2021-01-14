from pathlib import Path

from superdesk.default_settings import env, strtobool
from newsroom.web.default_settings import CORE_APPS, BLUEPRINTS


ABS_PATH = Path(__file__).resolve().parent

# extend apps
CORE_APPS.extend([])
BLUEPRINTS.extend([])
