"""Static data for the Briefdesk map mock.

Everything here is read from JSON files shipped inside this package. There is no
database resource and no Elasticsearch geo query: the map is a preview of what
geo alerting would look like, not an implementation of it.
"""

import json
import logging
import pathlib

from .vocabularies import (
    COUNTRIES,
    DEFAULT_SEVERITY,
    REGIONS,
    SECTORS,
    SEVERITIES,
    SEVERITY_BY_CODE,
    THREAT_TYPES,
    THREAT_TYPE_BY_CODE,
)

logger = logging.getLogger(__name__)

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
STATIC_DIR = PACKAGE_DIR / "static"

SITES_FILE = DATA_DIR / "sites.json"

#: Written by ``sync_alerts.py`` from the Superdesk seed script. Preferred over
#: ``alerts.json`` when present so the map shows the same alerts as the feed.
GEO_INDEX_FILE = DATA_DIR / "geo_index.json"

#: Invented fallback set, used when the seed script has not produced a geo index.
ALERTS_FILE = DATA_DIR / "alerts.json"

DEFAULT_RADIUS_KM = 50
RADIUS_OPTIONS_KM = [25, 50, 100]


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        logger.exception("briefdesk_map: could not read %s", path)
        return None


def load_companies():
    payload = _read_json(SITES_FILE) or {}
    return payload.get("companies") or []


def load_alerts():
    """Return the alert list, preferring the synced geo index over the fallback."""

    for path in (GEO_INDEX_FILE, ALERTS_FILE):
        if not path.exists():
            continue
        alerts = _read_json(path)
        if isinstance(alerts, list) and alerts:
            return [alert for alert in alerts if _has_coordinates(alert)]
    return []


def _has_coordinates(alert):
    try:
        float(alert["lat"])
        float(alert["lon"])
    except (KeyError, TypeError, ValueError):
        return False
    return True


def normalize_name(name):
    return (name or "").strip().casefold()


def find_company(companies, name):
    """Match a portal company name against the mock data.

    Falls back to a prefix match so that "Nordfreight" still resolves to
    "Nordfreight Logistics" if the seeded company name drifts.
    """

    wanted = normalize_name(name)
    if not wanted:
        return None

    for company in companies:
        if normalize_name(company.get("name")) == wanted:
            return company

    for company in companies:
        known = normalize_name(company.get("name"))
        if known and (known.startswith(wanted) or wanted.startswith(known)):
            return company

    return None


def matches_entitlement(alert, entitlement):
    """Region AND sector, with OR inside each list, as in the contract."""

    regions = entitlement.get("regions") or []
    sectors = entitlement.get("sectors") or []
    if regions and alert.get("region") not in regions:
        return False
    if sectors and alert.get("sector") not in sectors:
        return False
    return True


def decorate_alert(alert):
    severity = SEVERITY_BY_CODE.get(alert.get("severity"), DEFAULT_SEVERITY)
    threat_type = alert.get("threat_type")
    return {
        "reference": alert.get("reference") or "",
        "title": alert.get("title") or alert.get("reference") or "Untitled alert",
        "severity": severity["code"],
        "severity_name": severity["name"],
        "severity_color": severity["color"],
        "severity_rank": severity["rank"],
        "severity_radius": severity["radius"],
        "threat_type": threat_type,
        "threat_type_name": (THREAT_TYPE_BY_CODE.get(threat_type) or {}).get("name"),
        "region": alert.get("region"),
        "region_name": REGIONS.get(alert.get("region"), alert.get("region")),
        "sector": alert.get("sector"),
        "sector_name": SECTORS.get(alert.get("sector"), alert.get("sector")),
        "country": alert.get("country"),
        "country_name": COUNTRIES.get(alert.get("country"), alert.get("country")),
        "lat": float(alert["lat"]),
        "lon": float(alert["lon"]),
    }


def decorate_site(site):
    return {
        "id": site.get("id") or site.get("name"),
        "name": site.get("name") or "Site",
        "type": site.get("type") or "Site",
        "city": site.get("city") or "",
        "country": site.get("country"),
        "country_name": COUNTRIES.get(site.get("country"), site.get("country")),
        "lat": float(site["lat"]),
        "lon": float(site["lon"]),
    }


def entitlement_summary(entitlement):
    def group(names):
        joined = " or ".join(names)
        return f"({joined})" if len(names) > 1 else joined

    parts = [
        group([REGIONS.get(code, code) for code in entitlement.get("regions") or []]),
        group([SECTORS.get(code, code) for code in entitlement.get("sectors") or []]),
    ]
    return " and ".join(part for part in parts if part)


def build_view_data(company_name, is_staff, requested_company, wire_url):
    """Build the JSON payload handed to the browser.

    ``company_name`` is the logged in user's company. Staff (admin, account
    manager, internal, or a user without a company) see every company and can
    switch between them with ``requested_company``.
    """

    companies = load_companies()
    alerts = [decorate_alert(alert) for alert in load_alerts()]

    selected = None
    if is_staff:
        if requested_company and requested_company != "all":
            selected = find_company(companies, requested_company)
    else:
        selected = find_company(companies, company_name)

    if selected is not None:
        entitlement = selected.get("entitlement") or {}
        visible = [alert for alert in alerts if matches_entitlement(alert, entitlement)]
        sites = [decorate_site(site) for site in selected.get("sites") or []]
        company_payload = {
            "name": selected.get("name"),
            "tier": selected.get("tier"),
            "entitlement": entitlement,
            "entitlement_summary": entitlement_summary(entitlement),
        }
    elif is_staff:
        visible = alerts
        sites = [decorate_site(site) for company in companies for site in company.get("sites") or []]
        company_payload = None
    else:
        visible = []
        sites = []
        company_payload = {
            "name": company_name,
            "tier": None,
            "entitlement": {},
            "entitlement_summary": "",
            "unknown": True,
        }

    used_threat_types = {alert["threat_type"] for alert in visible if alert.get("threat_type")}
    used_severities = {alert["severity"] for alert in visible}

    return {
        "company": company_payload,
        "is_staff": is_staff,
        "companies": [{"name": company.get("name"), "tier": company.get("tier")} for company in companies],
        "selected_company": selected.get("name") if selected else "all",
        "sites": sites,
        "alerts": visible,
        "total_alerts": len(alerts),
        "severities": [item for item in SEVERITIES if item["code"] in used_severities],
        "threat_types": [item for item in THREAT_TYPES if item["code"] in used_threat_types],
        "radius_options": RADIUS_OPTIONS_KM,
        "default_radius": DEFAULT_RADIUS_KM,
        "wire_url": wire_url,
    }
