"""Briefdesk map: a preview of geo alerting inside the portal.

Instance module for the Briefdesk demo. It adds one server rendered page under
`/briefdesk-map` showing the logged in client's sites and recent alerts on a
Leaflet map. All of its data is static JSON inside this package, see README.md.

Registration in `server/settings.py` is a single entry:

    INSTALLED_APPS = ["briefdesk_map"]

Do not also add it to `BLUEPRINTS`. `init_app` registers the blueprint itself,
the way `newsroom.auth.oauth` does, and `setup_blueprints` would then register
the same blueprint name a second time and fail.
"""

from superdesk.flask import Blueprint

blueprint = Blueprint("briefdesk_map", __name__, template_folder="templates")

from . import views  # noqa: E402,F401


def init_app(app):
    if blueprint.name not in app.blueprints:
        app.register_blueprint(blueprint)

    # No app.section() on purpose: the page is not gated on a company section,
    # so it needs no extra seeding to show up for the demo companies.
    app.sidenav("Map", "briefdesk_map.index", "alert", group=0)
