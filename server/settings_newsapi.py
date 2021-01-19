from pathlib import Path

from superdesk.default_settings import env, strtobool # noqa
from newsroom.news_api.default_settings import CORE_APPS, INSTALLED_APPS, BLUEPRINTS


ABS_PATH = Path(__file__).resolve().parent

# extend apps
CORE_APPS.extend([])
INSTALLED_APPS.extend([])
BLUEPRINTS.extend([])
