# Briefdesk portal seed

Puts a freshly deployed Briefdesk Portal into the demo state: companies, tier packages for
the Intelligence Feed and the Risk Calendar, users, navigations, Watches, a personal home
page per user and one monitoring profile per company.
Re-runnable: everything is looked up by name or email first, then created or updated.

Files:

- `seed_portal.py` The script. Python 3 standard library only.
- `briefdesk_portal.json` All the data. Edit this, not the script.

## The home page is per user, not global

Global home page cards backed by a product are not filtered by the viewing user's company
entitlement. `newsroom/wire/items.py::get_items_for_dashboard` fetches each card through
`WireSearchServiceAsync.get_product_items_for_dashboard`, which replaces the search filters
with the card's own product ("so we can get items for the supplied product even if the
current user/company doesn't have permission for them"). A client would see teasers for
regions and sectors it does not pay for, which is the opposite of what this demo is meant
to show. So the seed creates no home page cards and no products to back them. Instead every
user gets a personal dashboard (the "Personalize Home" feature) built from Watches of their
own: `newsroom/wire/views.py::get_personal_dashboards_data` fetches those items with the
ordinary wire search for that user and company, so the company's products filter the
result exactly as they do in the Intelligence Feed.

The portal administrator gets one too, "Operations overview", with a row per region. It is
written by the `dashboards` section through a separate path: an entry with
`"existing_user": true` is a user the seed does **not** create or change. Only the
`dashboards` field is written, the account keeps the password, role and company the
deployment gave it, and the whole entry is skipped with a log line when there is no such
user. The administrator has no company, so `get_personal_dashboards_data` passes
`company=None` and `is_admin=True` into the search and
`newsroom/search/filters.py::apply_products_filter` returns early ("admin will see
everything by default"). The overview is therefore unfiltered, which is what an internal
operations view wants. The Watches it creates have `company: null`, which
`TopicResourceModel.company` allows, and `get_user_topics_async` finds them by
`{"user": user.id}`.

### The DEFAULT / MY HOME toggle cannot be hidden

`assets/home/components/HomeApp.tsx` renders the toggle whenever the user has the `wire`
section and `personalizedDashboards[0].topic_items.length > 0` (`this.hasPersonalDashboard`,
computed once in the constructor), and it opens on MY HOME in that case
(`activeOptionId: this.hasPersonalDashboard ? 'my-home' : 'default'`). The two radio options
are hardcoded, and the DEFAULT panel renders `DashboardPanels` with the `newsroom` cards,
which shows "There's no card defined for Home page!" when that list is empty. No setting
suppresses either the option or the warning; `PERSONAL_DASHBOARD_CARD_TYPE` only picks the
card type. So the empty DEFAULT tab stays, one click away, until either global cards come
back or newsroom-core changes. It is left as it is.

## On Fireq (automatic)

Nobody has a shell on a Fireq instance, so the branch seeds itself. `server/Procfile` has a
`seed:` entry running `scripts/demo/run_seed.sh`, which:

1. does nothing unless `DB_NAME` is set (Fireq exports it, the Docker setups here do not);
   `BRIEFDESK_SEED=1` forces it and `BRIEFDESK_SEED=0` disables it,
2. skips when the marker document `briefdesk_seed/<SEED_VERSION>` exists in MongoDB,
3. waits for the admin user `admin@example.com` to exist, because Fireq starts the app before it
   runs `initialize_data` and `create_user`, then waits another 45 seconds for the rest of the
   initialisation,
4. runs `python3 -u scripts/demo/seed_portal.py --transport local`, which also applies
   `server/theme/briefdesk_ui_config.wire.json` to the `ui_config` collection,
5. writes the marker on success, and then idles forever. It never exits, because honcho stops the
   whole instance when one Procfile process ends.

- Instance: https://nra-hgbriefdeskportaldemo.test.superdesk.org (Fireq strips everything but
  letters and digits from the branch name `hg/briefdesk-portal-demo`).
- Admin login: `admin@example.com` / `admin`. Client users: see the table below, password
  `Briefdesk-demo-1`.
- Seed output: https://nra-hgbriefdeskportaldemo.test.superdesk.org/logs/ , lines start with
  `[briefdesk-seed]`.
- Mail the portal sends (watch alerts, digests, shared items):
  https://nra-hgbriefdeskportaldemo.test.superdesk.org/mail/
- To seed again: the `[reset db]` button on https://test.superdesk.org/nra drops the database and
  with it the marker. Or bump `SEED_VERSION` in `run_seed.sh` and push (the seed is idempotent,
  so this only adds and updates). It is at `v3`; the instance was already seeded at `v2`, so the
  next deploy re-runs and adds the agenda products, the administrator's dashboard and the three
  new monitoring profiles on top of the existing data.
- Push order: this branch first, then `hg/briefdesk-branding` in superdesk-client-core, then
  `hg/briefdesk-demo` in superdesk. The portal should be seeded before Superdesk pushes content,
  so that watches exist when the first reports arrive.

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

Sections, in dependency order: `cleanup`, `navigations`, `products`, `companies`, `users`,
`topics`, `dashboards`, `cards`, `ui_config`, `monitoring`. `--only` is reordered into that
order for you.

`cleanup` deletes the documents listed in the `cleanup` block of the data file, which is how
a database seeded by an earlier version of this script loses the global home page cards and
the four `Dashboard: ...` products that backed them. Deleting a product is safe even when a
company still holds it: `ProductsService.on_deleted` strips the reference from every company
and user.

Environment: `PORTAL_URL`, `PORTAL_ADMIN_EMAIL` (default `admin@example.com`),
`PORTAL_ADMIN_PASSWORD`, `PORTAL_USER_PASSWORD` (default `Briefdesk-demo-1`).

## Which transport

`local` is the one that produces the demo. The HTTP admin API has four gaps that no
amount of scripting gets around:

- **Passwords.** Nothing in the web API sets one. `POST /users/new` and
  `POST /users/<id>` both go through `newsroom.users.forms.UserForm`, which has no
  password field; `/reset_password/<token>` needs a token that is only ever emailed, and
  `/change_password` needs the old password. Users created over HTTP cannot log in.
- **Watches for other people.** `POST /users/<id>/topics` is guarded by
  `url_arg_must_be_current_user`, with no administrator bypass. Only the owner can create
  their own Watch.
- **Personal home dashboards.** The user edit endpoint posts to
  `newsroom.users.forms.UserForm` too, and that form has no `dashboards` field, so the
  `dashboards` section cannot be written over HTTP either.
- **`ui_config` and monitoring profiles.** `ui_config` has no endpoint at all. The
  monitoring create endpoint reads a WTForms body and a JSON body from the same request,
  which a normal client cannot send.

The HTTP transport still does the cleanup, companies, products, navigations and users
(without passwords), and it prints exactly what it skipped. Use it when you only have the
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
3. The portal has the same value fixed as `PUSH_KEY` in `server/settings.py`. The environment
   is not read there, because Fireq exports its own `PUSH_KEY` to every Newsroom test instance.
   Both sides must match or every push is rejected.
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

## The Risk Calendar (agenda) needs its own products

`newsroom/agenda/views.py::get_view_data` calls `check_user_has_products` with
`get_products_by_company(company, product_type=SectionEnum.AGENDA)`, so a company with only
wire products gets a 403 "There is no product associated with your user". Each client
company now has one agenda product mirroring its Intelligence Feed entitlement, plus one
for Halden, all attached to the agenda navigation "Risk calendar". The section reference on
the company (`products[].section`) has to say `agenda`, not the product's `product_type`:
`newsroom/products/utils.py::get_products_by_company_async` filters on
`product.section == product_type`. The seed derives it from `product_type` in the data file.

An agenda product has two query fields and they behave differently:

- `query` is applied by `newsroom/search/filters.py::apply_products_filter` as a root scope
  `query_string`, exactly as for wire. `AgendaItem.subject` (`newsroom/types/agenda.py`) is
  `fields.nested_list(include_in_parent=True)` just like `WireItem.subject`, so
  `subject.code:europe` matches the flattened root copy. Bare, unqualified words would only
  hit `AGENDA_SEARCH_FIELDS` (name, slugline, headline, the definitions, description_text,
  location), so every clause is field qualified.
- `planning_item_query` is applied by `newsroom/agenda/filters.py::apply_product_planning_filters`,
  which wraps it in `nested_query("planning_items", ...)`. That path calls
  `planning_items_query_string(...)` **without** `nested=True`, so nothing rewrites the field
  names: a clause has to be written out as `planning_items.subject.code:europe` or it
  addresses a root field that does not exist inside the nested document and matches nothing.
  `AgendaPlanningItem.subject` is nested with `include_in_parent` too, so the single prefix is
  enough.

Both clauses land in the same `should` list with `minimum_should_match: 1`, so an entry
matches when either the event's own subjects or one of its planning items qualifies.

### What the Superdesk side must send

- Tag **the event**, not only its planning items. For an event backed agenda item
  `newsroom/agenda/agenda_service.py::convert_event_to_agenda_dict` sets
  `agenda["subject"] = format_qcode_items(event.get("subject"))` from the event alone; the
  planning subjects go to `planning_items[].subject`. Only a planning item with no
  `event_item` copies its own subjects to the root.
- `subject` entries as `{"qcode": ..., "name": ..., "scheme": ...}`. `format_qcode_items`
  copies `qcode` into `code` on ingest, so the portal queries `code`.
- **Codes, not names.** The products match `subject.code:europe`, `subject.code:logistics`
  and the rest against the contract qcodes. `code` is a `keyword`, so the match is exact and
  case sensitive: send `europe`, not `Europe`.
- Schemes `region` and `sector` are what the entitlement needs; `country` and `threat_type`
  feed the `AGENDA_GROUPS` filter panel. The qcodes are unique across all schemes, so the
  product queries do not name the scheme (see the `include_in_parent` caveat above).
- Nothing drops custom schemes on the agenda side. `WIRE_SUBJECT_SCHEME_WHITELIST` is read
  only in the wire branch of `newsroom/push/publishing.py`, and `AGENDA_CSV_SUBJECT_SCHEMES`
  is a CSV export filter. No `settings.py` change was needed, and `AGENDA_GROUPS` was
  already configured there for all six schemes.
- An entry with a region but no sector matches no client agenda product, because every
  client entitlement is region AND sector. It still reaches Halden, whose product asks for a
  region only. Tag both on anything a client should see in the Risk Calendar.

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
  company, product, navigation, Watch or user email in the data file creates a second
  document rather than renaming the first, because the name is the lookup key. Add the old
  name to the `cleanup` block to have the leftover deleted on the next run.

## Known limitations

- The HTTP transport cannot set passwords, create Watches, write personal dashboards or
  `ui_config`, or create monitoring profiles. See "Which transport".
- `ui_config` is only applied if `server/theme/briefdesk_ui_config.wire.json` exists. That
  file belongs to the theme work package and holds one document per section (`wire`,
  `home`, `agenda`), the same shape as `newsroom/init_data/ui_config.json`. The
  alternative route is `server/data/ui_config.json` plus
  `python manage.py initialize_data -n ui_config -f`.
- The home page of a user without a personal dashboard is empty, because the seed creates no
  global cards. Everyone in the data file has one, and so does `admin@example.com` through
  the `existing_user` path. Any account added by hand afterwards will land on the empty
  DEFAULT panel.
- The portal administrator cannot have a monitoring profile.
  `newsroom/monitoring/views.py::get_monitoring_for_company` lists profiles with
  `search({"company": user.company})` and there is no administrator bypass, so a
  company-less account always sees an empty `/monitoring`. `MonitoringForm` also makes
  `company` a `DataRequired()` field. The seed therefore does not try. What the
  administrator does get is Settings, Monitoring (`/settings/monitoring`), where
  `GET /monitoring/all` with no `where` parameter lists every profile in the instance, now
  four instead of one.
- The personal dashboard cards are rendered as `PERSONAL_DASHBOARD_CARD_TYPE`, a single
  setting for the whole instance, default `4-picture-text`. The `type` stored on each
  dashboard is what the Personalize Home modal writes and is not read back.
- `PersonalizeHomeModal` caps a selection at `MAX_SELECTED_TOPICS = 6`, but the server renders
  every entry of `dashboards[].topic_ids`. The administrator's "Operations overview" has 8, so
  a pass through the Personalize Home modal would trim it. The modal also replaces the whole
  dashboard when a user edits it.
- If global cards are ever wanted back, `PERMISSION_DASHBOARD_CARDS` in `server/settings.py`
  makes the home page mark each card item with `user_has_access` and blank its body, but the
  headlines of items outside the entitlement are still listed.
- A monitoring profile is written whether or not the monitoring section is enabled and
  whether or not Celery beat is running. Nothing will actually be emailed unless the
  `beat` and `worker` processes are up. All four companies now have `sections.monitoring`
  on, which is what puts the profile in front of their users and lists the company in the
  Settings, Monitoring company filter (`newsroom/monitoring/views.py::get_settings_data`
  searches `{"sections.monitoring": True}`).
- `--dry-run` connects to nothing, so it reports every document as "would create" even if
  the portal already has it. It is there to validate the data file, not to diff an instance.
- Company `expiry_date` is cleared and `archive_access` is on for all four companies, so
  nothing ages out mid demo.
