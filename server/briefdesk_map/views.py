from quart_babel import gettext
from superdesk.flask import render_template, request, url_for
from werkzeug.routing import BuildError

from newsroom.auth.utils import get_company_or_none_from_request, get_user_or_none_from_request
from newsroom.decorator import login_required
from newsroom.flask import send_from_directory

from . import blueprint
from .data_store import STATIC_DIR, build_view_data


def _wire_url():
    try:
        return url_for("wire.wire")
    except (BuildError, RuntimeError):
        return "/wire"


def _is_staff(user, company):
    """Staff see every company and get the company switcher."""

    if user is None:
        return False
    if user.is_admin() or user.is_account_manager() or user.is_internal():
        return True
    if company is None:
        return True
    return bool(getattr(company, "internal", False))


def _strings():
    return {
        "no_sites": gettext("No sites are configured for this client in the map preview."),
        "no_alerts": gettext("No alerts match the current filters."),
        "within": gettext("within"),
        "of_your_sites": gettext("km of your sites"),
        "more_outside": gettext("more outside the radius"),
        "from_site": gettext("from"),
        "open_in_feed": gettext("Open in Intelligence Feed"),
        "notify_toast": gettext(
            "Preview feature. Geo alerting is a mock-up in this demo, so no notification was created."
        ),
        "your_site": gettext("Your site"),
        "leaflet_missing": gettext("The map could not be loaded. Check the network connection and reload the page."),
    }


@blueprint.route("/briefdesk-map")
@login_required
async def index():
    user = get_user_or_none_from_request(None)
    company = get_company_or_none_from_request(None)
    data = build_view_data(
        company_name=company.name if company is not None else None,
        is_staff=_is_staff(user, company),
        requested_company=request.args.get("company"),
        wire_url=_wire_url(),
    )
    data["strings"] = _strings()
    return await render_template("briefdesk_map_index.html", data=data)


@blueprint.route("/briefdesk-map/static/<path:filename>")
@login_required
async def static_file(filename):
    return await send_from_directory(str(STATIC_DIR), filename)
