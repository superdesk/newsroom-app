# briefdesk_map

A "Map" page in the Briefdesk Portal showing the logged-in client's sites and recent alerts as pins, with "alerts within N km of your sites". It is a **mock-up** for the demo, labelled `Preview` in the page header.

## What is mocked

- Site locations. There is no company sites resource in Newsroom. Sites come from `data/sites.json`, keyed by the portal company name from the demo contract (Nordfreight Logistics, Aurelia Pharma, Castellan Energy).
- Alert locations. Alerts carry no coordinates in either stack. They come from `data/alerts.json` (invented) or `data/geo_index.json` (copied from the Superdesk seed script, see below).
- Entitlement. Computed server-side from the static entitlement in `sites.json` (region AND sector, OR inside each list), not from the company's products or content filters.
- Distance and radius. Haversine in the browser, not a geo query.
- "Notify me about alerts within N km of my sites" only shows a toast.

## What is real

- The page is a normal instance module: a Quart blueprint, `login_required`, the standard base layout, so it gets the real top bar, side navigation, footer and session.
- Links out of a pin go to the real Intelligence Feed: `/wire?q=<reference>`, a text search on the alert's Reference (slugline). They resolve only when an alert with that reference actually exists in the portal, which is why `sync_alerts.py` exists.

## Registration

The module is a plain Python package under `server/`, so it is importable as `briefdesk_map` (the app runs with `server/` as the working directory). In `server/settings.py`, one entry is enough:

```python
INSTALLED_APPS = [
    "briefdesk_map",
]
```

`BaseNewsroomApp.__init__` runs `setup_apps` over `CORE_APPS` and then over `INSTALLED_APPS`, calling `init_app(app)` on each. `init_app` registers both the blueprint (the routes) and the sidenav entry, the way `newsroom.auth.oauth` registers its own blueprint.

- `CORE_APPS.append("briefdesk_map")` works just as well. `INSTALLED_APPS` is skipped when `BEHAVE` is set, which only matters for the behave test suite.
- Do **not** also add it to `BLUEPRINTS`. `setup_blueprints` runs after `setup_apps` and would register the same blueprint name a second time, which fails.
- Do **not** put it in `MODULES`: that list is for `superdesk.core.module.Module` objects, which this is not.

No `app.section(...)` is registered on purpose, so the page needs no per-company section seeding and is visible to every logged-in user.

Routes:

| Route | Endpoint | Purpose |
|---|---|---|
| `/briefdesk-map` | `briefdesk_map.index` | the page |
| `/briefdesk-map/static/<path:filename>` | `briefdesk_map.static_file` | this package's CSS and JS |

Staff (admin, account manager, internal, no company, or a company flagged `internal`) see every company's sites and every alert, plus a client switcher: `/briefdesk-map?company=Nordfreight%20Logistics`.

## Syncing alerts with the seeded content

The Superdesk seed script writes `superdesk/server/scripts/demo/content/geo_index.json`. Copy it in before the demo so the map and the feed agree:

```
python3 server/briefdesk_map/sync_alerts.py
python3 server/briefdesk_map/sync_alerts.py --clear   # back to the invented fallback
```

The copy lands in `data/geo_index.json` and takes precedence over `data/alerts.json`. Entries need `reference`, `title`, `severity`, `lat`, `lon`, `region`, `sector`; `threat_type` and `country` are optional (the threat-type filter chips disappear without them).

## Third-party assets

- Leaflet 1.9.4 from unpkg, with SRI hashes, loaded in the page template. newsroom-core sets no Content-Security-Policy (checked on `origin/develop`), and the base layout already loads Google Fonts and jsDelivr, so a CDN is consistent with the rest of the portal. If a CSP is ever added, vendor Leaflet into `static/` and serve it through `briefdesk_map.static_file`.
- Tiles: OpenStreetMap standard tiles with the required attribution. Fine for an internal demo. A product must not use them: OSM's tile policy forbids commercial or heavy use, so a real build needs a paid provider (MapTiler, Mapbox, HERE) or self-hosted tiles.

## What the real thing would be

Roughly the "1 to 2 weeks prototype, 1 to 2 months production" line in the ledger. In dependency order:

1. **Location on the Superdesk side.** The Alert content profile already has a free-text `location_text` field. Replace it with a real location field that resolves to coordinates (Planning's `Location` resource and its `location` lookup already do this for events, in `superdesk-planning`), and put the result on the item as `place[].location` or a dedicated `location` object with a `geo_point`.
2. **Carry it through the push.** `superdesk-core`'s NINJS formatter for Newsroom must emit the coordinates, and `newsroom/push/publishing.py` must keep them.
3. **Index it.** Add a `geo_point` mapping for the field to the wire items resource in `newsroom/wire/module.py` (`ElasticResourceConfig`), and the matching mapping on the Superdesk side. This needs an Elasticsearch reindex, which is the only part with real operational cost.
4. **Company sites.** A new async resource (`newsroom/companies/sites.py` plus a `ResourceConfig` in `newsroom/companies/module.py`), editable from the company admin UI (`assets/companies/components/EditCompany*.tsx` and `assets/company-admin/`). Each site: name, type, address, `geo_point`.
5. **Matching in the notification pipeline.** `newsroom/push/notifications.py` decides who is notified about a new item. Add a check that runs a `geo_distance` query, or an in-process haversine against the company's sites, and treat "within N km of one of my sites" as a topic-like subscription. The per-user radius belongs on the topic or on the user's notification settings.
6. **Map view.** Replace this page with a React view under `assets/` so it gets the usual filter panel, saved searches and list/preview behaviour, and add a "near my sites" filter to the normal Intelligence Feed rather than leaving the map as a separate place.

Files that would change in newsroom-core: `newsroom/wire/module.py`, `newsroom/push/publishing.py`, `newsroom/push/notifications.py`, `newsroom/companies/module.py` and `newsroom/companies/companies_async/`, `newsroom/types/company.py`, `newsroom/types/wire.py`, `newsroom/search/filters.py`, plus client code under `assets/companies/`, `assets/company-admin/` and a new `assets/map/`.
