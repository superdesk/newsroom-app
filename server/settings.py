import os
import sys
import pathlib

from quart_babel import lazy_gettext

from newsroom.types import AuthProviderType
from newsroom.web.default_settings import CLIENT_CONFIG as _CORE_CLIENT_CONFIG

SERVER_PATH = pathlib.Path(__file__).resolve().parent
CLIENT_PATH = SERVER_PATH.parent.joinpath("client")

# Instance modules such as ``briefdesk_map`` live next to this file and are imported by name.
# Depending on how the process is started, the server directory is not necessarily on ``sys.path``.
if str(SERVER_PATH) not in sys.path:
    sys.path.insert(0, str(SERVER_PATH))

WEBPACK_MANIFEST_PATH = os.environ.get(
    "WEBPACK_MANIFEST_PATH", CLIENT_PATH.joinpath("dist", "manifest.json")
)

# Branding

SITE_NAME = "Briefdesk Portal"
COPYRIGHT_HOLDER = "Halden Risk Intelligence"
COPYRIGHT_NOTICE = "Copyright Halden Risk Intelligence. Released to entitled clients only."
USAGE_TERMS = "For the internal use of the receiving client organisation. Do not redistribute."

CONTACT_ADDRESS = "mailto:clientdesk@halden.example"
PRIVACY_POLICY = "https://halden.example/privacy"
TERMS_AND_CONDITIONS = "https://halden.example/terms"
SHOW_COPYRIGHT = True

MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "briefdesk@halden.example")
EMAIL_DEFAULT_SENDER_NAME = SITE_NAME

AUTH_PROVIDERS = [
    {
        "_id": "newshub",
        "name": SITE_NAME,
        "auth_type": AuthProviderType.PASSWORD,
    }
]

# Section labels
#
# Read by ``newsroom.wire.init_app`` and ``newsroom.agenda.init_app`` to name the sidenav entries and
# the company permission sections, and handed to the client in ``window.sectionNames``.

HOME_SECTION = lazy_gettext("Home")
WIRE_SECTION = lazy_gettext("Intelligence Feed")
AGENDA_SECTION = lazy_gettext("Risk Calendar")
MONITORING_SECTION = lazy_gettext("Monitoring")
SAVED_SECTION = lazy_gettext("Saved")

# Locale

LANGUAGES = ["en"]
DEFAULT_LANGUAGE = "en"

# ``BABEL_DEFAULT_TIMEZONE`` is derived from ``DEFAULT_TIMEZONE`` at import time in
# ``newsroom.web.default_settings``, so overriding only ``DEFAULT_TIMEZONE`` would leave Babel on the
# server's local zone. Both have to be set.
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "Europe/Prague")
BABEL_DEFAULT_TIMEZONE = DEFAULT_TIMEZONE

# Per-instance English label overrides. ``BaseNewsroomApp.setup_babel`` appends this to
# ``BABEL_TRANSLATION_DIRECTORIES`` after the newsroom-core catalogue, and quart_babel merges the
# directories in order, so entries here win. Only the compiled ``messages.mo`` is read at runtime.
TRANSLATIONS_PATH = SERVER_PATH.joinpath("translations")

# Superdesk push

# ``newsroom.push.utils.test_signature`` calls ``hmac.new(key, ...)``, so this has to be bytes.
# The environment is deliberately not read: Fireq exports the same ``PUSH_KEY`` to every Newsroom
# test instance, and the Superdesk demo seed signs with the value below. Both instances have to
# agree without anyone having access to the host, so the key is fixed here. Demo only, a real
# deployment takes it from the environment.
PUSH_KEY = b"briefdesk-demo-push-key"

# ``newsroom.push.publishing`` drops every ``subject`` entry whose scheme is not listed here, and
# that includes entries with no scheme at all. These ids are the Superdesk custom vocabulary ids.
WIRE_SUBJECT_SCHEME_WHITELIST = [
    "severity",
    "threat_type",
    "region",
    "country",
    "sector",
    "tlp",
]

AGENDA_CSV_SUBJECT_SCHEMES = WIRE_SUBJECT_SCHEME_WHITELIST

# Instance apps
#
# ``briefdesk_map`` is the mock geo view, a package in this directory. ``INSTALLED_APPS`` is the
# instance extension point: ``BaseNewsroomApp.__init__`` runs ``setup_apps`` over ``CORE_APPS`` and
# then over ``INSTALLED_APPS``, which core leaves undefined, so the core defaults are untouched.
# Each entry must expose ``init_app(app)``, not an async ``module`` instance; that is what the
# ``MODULES`` list requires instead.
INSTALLED_APPS = [
    "briefdesk_map",
]

# Closed portal: no public self-signup, no News API.
#
# ``/signup`` aborts with 404 unless ``SIGNUP_EMAIL_RECIPIENTS`` is set, and the login page only
# offers the sign up link when ``SHOW_USER_REGISTER`` is true. Client accounts are created by an
# administrator or by the client's own company admin.

SHOW_USER_REGISTER = False
SIGNUP_EMAIL_RECIPIENTS = None
GOOGLE_LOGIN = False

# Turns off the api_tokens blueprint and the API tabs in company and user admin. The separate
# ``newsapi`` Procfile process reads ``settings_newsapi.py``, which still enables it; that process is
# not started for the demo.
NEWS_API_ENABLED = False

# Search: filter groups
#
# Every group below is a nested search group over ``subject``, which is mapped as ``nested`` with
# ``include_in_parent`` (newsroom-core ``newsroom/types/wire.py``). At startup
# ``newsroom.search.config.init_nested_aggregation`` rewrites the aggregations from these
# definitions: one nested aggregation per group filtered on ``subject.scheme``, plus a plain
# ``subject`` aggregation narrowed to everything that is not one of our schemes.
#
# ``nested.searchfield`` is left at its default of ``name``, so the values the client posts back
# match the aggregation buckets, which are built from ``subject.name``.
#
# The AAP news groups (genre, service, urgency, place) are dropped. Nothing in the demo populates
# them and an empty filter group still renders its heading.

_SUBJECT_GROUPS = [
    ("severity", lazy_gettext("Severity")),
    ("threat_type", lazy_gettext("Threat type")),
    ("region", lazy_gettext("Region")),
    ("country", lazy_gettext("Country")),
    ("sector", lazy_gettext("Sector")),
    ("tlp", lazy_gettext("TLP marking")),
]

WIRE_GROUPS = [
    {
        "field": scheme,
        "label": label,
        "nested": {
            "parent": "subject",
            "field": "scheme",
            "value": scheme,
        },
    }
    for scheme, label in _SUBJECT_GROUPS
]

AGENDA_GROUPS = [
    {
        "field": scheme,
        "label": label,
        "nested": {
            "parent": "subject",
            "field": "scheme",
            "value": scheme,
            "include_planning": True,
        },
    }
    for scheme, label in _SUBJECT_GROUPS
]

# ``init_nested_aggregation`` clones this ``subject`` entry for every group, so its ``size`` caps
# each of them. The largest vocabulary is ``country`` with 15 values.
WIRE_AGGS = {
    "subject": {"terms": {"field": "subject.name", "size": 100}},
}

WIRE_SEARCH_FIELDS = [
    "slugline",
    "headline",
    "body_html",
    "body_text",
    "description_html",
    "description_text",
    "keywords",
]

# Wire

DISPLAY_ABSTRACT = True
WIRE_NOTIFICATIONS_ON_CORRECTIONS = True

WIRE_TIME_FILTERS = [
    {"name": lazy_gettext("Today"), "filter": "today", "default": False, "query": {"gte": "now/d"}},
    {"name": lazy_gettext("Last 7 days"), "filter": "last_week", "default": True, "query": {"gte": "now-7d/d"}},
    {"name": lazy_gettext("Last 30 days"), "filter": "last_30_days", "default": False, "query": {"gte": "now-30d/d"}},
    {"name": lazy_gettext("Last 90 days"), "filter": "last_90_days", "default": False, "query": {"gte": "now-90d/d"}},
]

# Topic alert digest times, evaluated in each recipient's own timezone.
DEFAULT_SCHEDULED_NOTIFICATION_TIMES = [
    "07:00",
    "13:00",
    "18:00",
]

# Client config
#
# ``CLIENT_CONFIG`` is built once at import time in ``newsroom.web.default_settings``, so the values
# it derives from other settings (timezone, abstract, digest times) do not follow an override of
# those settings and have to be restated here. A shallow copy is enough, only top level keys change.

CLIENT_CONFIG = dict(_CORE_CLIENT_CONFIG)
CLIENT_CONFIG.update(
    {
        "default_language": DEFAULT_LANGUAGE,
        "default_timezone": DEFAULT_TIMEZONE,
        "display_abstract": DISPLAY_ABSTRACT,
        "display_news_only": False,
        "display_agenda_featured_stories_only": False,
        "display_credits": False,
        "display_author_role": False,
        "scheduled_notifications": {"default_times": DEFAULT_SCHEDULED_NOTIFICATION_TIMES},
        "advanced_search": {
            "fields": {
                "wire": ["headline", "slugline", "body_html"],
                "agenda": ["name", "headline", "slugline", "description"],
            },
        },
        "filter_panel_defaults": {
            "tab": {"wire": "filters", "agenda": "filters"},
            "open": {"wire": True, "agenda": False},
        },
    }
)

# Personal home dashboards default to a card type built around pictures. Briefdesk reports carry
# no images, so the text-only card is used.
PERSONAL_DASHBOARD_CARD_TYPE = "4-text-only"
