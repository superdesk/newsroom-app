from pathlib import Path

from superdesk.default_settings import env, strtobool # noqa
from newsroom.web.default_settings import CORE_APPS, BLUEPRINTS


ABS_PATH = Path(__file__).resolve().parent

# extend apps
CORE_APPS.extend([])
BLUEPRINTS.extend([])

# logging
LOG_CONFIG_FILE = env('LOG_CONFIG_FILE', ABS_PATH / 'logging_config.yml')
