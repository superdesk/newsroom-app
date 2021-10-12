from superdesk.tests.environment import setup_before_all, setup_before_scenario

from newsroom.news_api.app import get_app as _get_app
from settings_newsapi import CORE_APPS


def get_app(*args, **kwargs):
    # explicitly set testing to True
    return _get_app(*args, testing=True, **kwargs)


def before_all(context):
    config = {
        'BEHAVE': True,
        'CORE_APPS': CORE_APPS,
        'INSTALLED_APPS': [],
        'ELASTICSEARCH_FORCE_REFRESH': True,
        'NEWS_API_ENABLED': True,
        'NEWS_API_TIME_LIMIT_DAYS': 100,
        'NEWS_API_BEHAVE_TESTS': True,
    }
    setup_before_all(context, config, app_factory=get_app)


def before_scenario(context, scenario):
    config = {
        'BEHAVE': True,
        'CORE_APPS': CORE_APPS,
        'INSTALLED_APPS': [],
        'ELASTICSEARCH_FORCE_REFRESH': True,
        'NEWS_API_ENABLED': True,
        'NEWS_API_TIME_LIMIT_DAYS': 100,
        'NEWS_API_BEHAVE_TESTS': True,
    }

    if 'rate_limit' in scenario.tags:
        config['RATE_LIMIT_PERIOD'] = 300  # 5 minutes
        config['RATE_LIMIT_REQUESTS'] = 2

    setup_before_scenario(context, scenario, config, app_factory=get_app)
