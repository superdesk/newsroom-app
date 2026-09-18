# Briefdesk portal seed

Puts a freshly deployed Briefdesk Portal into the demo state: companies, tier packages,
users, navigations, Watches, the home page dashboard and a monitoring profile. Re-runnable:
everything is looked up by name or email first, then created or updated.

Files:

- `seed_portal.py` The script. Python 3 standard library only.
- `briefdesk_portal.json` All the data. Edit this, not the script.

## Run it

Two transports. Read "Which transport" below before choosing.

### On the instance (complete)

```
cd /path/to/newsroom-app/server
python3 scripts/demo/seed_portal.py --transport local
```

On a Fireq deploy that is inside the web container, for example:

```
docker exec -it <container> bash -lc 'cd /opt/newsroom/server && python3 scripts/demo/seed_portal.py --transport local'
```

The script changes to the `server` directory itself, so it picks up `settings.py`, the
Mongo and Elasticsearch URLs and the rest of the instance config exactly as
`newsroom.web.app` does.

### From a laptop (incomplete, see the limits)

```
PORTAL_URL=https://briefdesk-portal.example \
PORTAL_ADMIN_EMAIL=admin@example.com \
PORTAL_ADMIN_PASSWORD=... \
python3 server/scripts/demo/seed_portal.py
```

### Options

```
--transport auto|http|local   auto picks http when PORTAL_URL is set, local otherwise
--only SECTION                run these sections only, repeatable
--dry-run                     print what would happen, connect to nothing
--data PATH                   another seed data file
--subject-filter-field name|code
```

Sections, in dependency order: `navigations`, `products`, `companies`, `users`, `topics`,
`cards`, `ui_config`, `monitoring`. `--only` is reordered into that order for you.

Environment: `PORTAL_URL`, `PORTAL_ADMIN_EMAIL` (default `admin@example.com`),
`PORTAL_ADMIN_PASSWORD`, `PORTAL_USER_PASSWORD` (default `Briefdesk-demo-1`).

## Which transport

`local` is the one that produces the demo. The HTTP admin API has three gaps that no
amount of scripting gets around:

- **Passwords.** Nothing in the web API sets one. `POST /users/new` and
  `POST /users/<id>` both go through `newsroom.users.forms.UserForm`, which has no
  password field; `/reset_password/<token>` needs a token that is only ever emailed, and
  `/change_password` needs the old password. Users created over HTTP cannot log in.
- **Watches for other people.** `POST /users/<id>/topics` is guarded by
  `url_arg_must_be_current_user`, with no administrator bypass. Only the owner can create
  their own Watch.
- **`ui_config` and monitoring profiles.** `ui_config` has no endpoint at all. The
  monitoring create endpoint reads a WTForms body and a JSON body from the same request,
  which a normal client cannot send.

The HTTP transport still does companies, products, navigations, users (without passwords)
and home page cards, and it prints exactly what it skipped. Use it when you only have the
URL, then finish with `--transport local`.

The management API (`newsroom/mgmt_api/`) would have solved the topics problem, but it is
a second app on its own port that this distribution's `Procfile` never starts, and it
needs `MGMT_API_ENABLED` plus `AUTH_SERVER_SHARED_SECRET`. It is not reachable on a Fireq
deploy, and it has no cards, ui_config or monitoring resources either.

## Order of operations against the Superdesk seed

**Seed the portal first, then push content.** Two reasons:

- Entitlement is evaluated at search time from the company's products, so content pushed
  before the products exist is not lost. But the Superdesk side has to be told the portal
  URL and push key anyway, and doing the portal first means the first pushed report is
  immediately visible to the right clients.
- Topic alerts (`notification_type: real-time`) only fire for Watches that exist when the
  item arrives. If you want the "a Watch fires" beat of the demo to work on the first
  push, the Watches must be seeded first.

So: deploy the portal, run this script, then wire the Superdesk recipient and publish.

## Wiring Superdesk to this portal (manual, on the Superdesk side)

1. In Superdesk, Settings, Recipients, create a recipient `Briefdesk Portal`.
2. Destination: format `Newsroom NINJS`, delivery type `HTTP Push`, resource URL
   `<PORTAL_URL>/push`, secret token `briefdesk-demo-push-key`.
3. The portal reads the same value from `PUSH_KEY` in `server/settings.py`, which defaults
   to `briefdesk-demo-push-key` and can be overridden with the `PUSH_KEY` environment
   variable. Both sides must match or every push is rejected.
4. Give the recipient a product or content filter that matches every released report, so
   the portal gets everything and does its own per-client filtering.

## How report types are told apart

The tier packages filter on `profile`, which the Superdesk NINJS formatter fills from the
content profile and the portal stores on the wire item. **The Superdesk side must name its
content profiles exactly `Alert`, `Daily Brief`, `Country Assessment` and `RFI Response`,
and must not set an `output_name` on them.**

`superdesk/publish/formatters/ninjs_formatter.py` sets `ninjs["profile"]` from
`content_types.get_output_name(profile)`, which is `output_name or label` with everything
outside `[0-9a-zA-Z_]` stripped. So those four labels arrive as `Alert`, `DailyBrief`,
`CountryAssessment` and `RFIResponse`, which is what `briefdesk_portal.json` queries. The
field is analysed text, so case does not matter, but spaces and punctuation are removed
before indexing and a renamed profile silently breaks the tiers.

If that turns out to be fragile on the day, the sturdier alternative is a seventh Superdesk
vocabulary `report_type` (single selection, qcodes `alert`, `daily_brief`,
`country_assessment`, `rfi_response`), added to `WIRE_SUBJECT_SCHEME_WHITELIST` and to
`_SUBJECT_GROUPS` in `server/settings.py`. Then replace `profile:Alert` with
`subject.code:alert` in `briefdesk_portal.json` and re-run. That change is a one line edit
per product here, but it needs the vocabulary on the Superdesk side.

## How entitlement is modelled

A company's products are OR-ed together (`newsroom/search/filters.py::apply_products_filter`
appends each product query to `query.should`), so every product query carries its own AND:

```
profile:Alert AND subject.code:europe AND subject.code:logistics
```

`subject` is mapped as `nested` with `include_in_parent: true`, so a root scope
`query_string` against `subject.code` matches. The contract's qcodes are unique across all
six vocabularies, so the scheme never has to appear in the query. See
`server/BRIEFDESK_PORTAL.md`, "Product and topic queries on custom schemes", for the full
argument.

Each company gets one product per report type it is entitled to, and each product is
attached to the navigation for that report type plus "All reports". That way the tier is
the union of the company's products, and the navigation picks a subset of it.

Watch filters are different: they use the filter group mechanism, which does produce a
correlated `nested` query, and it matches on `subject.name`, the display name, because
`WIRE_GROUPS` in `server/settings.py` leaves `nested.searchfield` at its default. If that
setting ever switches to `code`, run the script with `--subject-filter-field code`.

## Reset

There is no undo. To start over:

- Fastest: redeploy the instance with an empty database, then re-run the script.
- Otherwise delete the demo documents by hand in the admin UI (Companies, Products,
  Global Topics, Dashboards) and re-run. Deleting a company deletes its users.
- To fix one part only, edit `briefdesk_portal.json` and re-run with `--only`. Renaming a
  company, product, navigation, card or user email in the data file creates a second
  document rather than renaming the first, because the name is the lookup key.

## Known limitations

- The HTTP transport cannot set passwords, create Watches, write `ui_config` or create
  monitoring profiles. See "Which transport".
- `ui_config` is only applied if `server/theme/briefdesk_ui_config.wire.json` exists. That
  file belongs to the theme work package and holds one document per section (`wire`,
  `home`, `agenda`), the same shape as `newsroom/init_data/ui_config.json`. The
  alternative route is `server/data/ui_config.json` plus
  `python manage.py initialize_data -n ui_config -f`.
- Home page cards are global, not per company. Users see teasers for items outside their
  entitlement unless `PERMISSION_DASHBOARD_CARDS` is on in `server/settings.py`, which makes
  the home page mark each card item with `user_has_access`.
- The four `Dashboard: ...` products exist only to feed home page cards. They are
  deliberately not assigned to any company.
- The monitoring profile is written whether or not the monitoring section is enabled and
  whether or not Celery beat is running. Nothing will actually be emailed unless the
  `beat` and `worker` processes are up.
- `--dry-run` connects to nothing, so it reports every document as "would create" even if
  the portal already has it. It is there to validate the data file, not to diff an instance.
- Company `expiry_date` is cleared and `archive_access` is on for all four companies, so
  nothing ages out mid demo.
