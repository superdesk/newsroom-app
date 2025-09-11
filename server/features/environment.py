from superdesk.tests.environment import setup_before_all

from newsroom.news_api.factory import get_app as _get_app
from settings_newsapi import CORE_APPS


def get_app(*args, **kwargs):
    # explicitly set testing to True
    return _get_app(*args, testing=True, **kwargs)


def before_all(context):
    config = {
        "BEHAVE": True,
        "CORE_APPS": CORE_APPS,
        "INSTALLED_APPS": [],
        "ELASTICSEARCH_FORCE_REFRESH": True,
        "NEWS_API_ENABLED": True,
        "NEWS_API_TIME_LIMIT_DAYS": 100,
        "NEWS_API_BEHAVE_TESTS": True,
        "CACHE_TYPE": "null",
    }
    setup_before_all(context, config, app_factory=get_app)
