# Briefdesk Portal (Newsroom distribution)

This branch turns the stock Newshub distribution into "Briefdesk Portal", the client portal of the
fictional risk intelligence firm Halden Risk Intelligence. Everything here is configuration, theme
overrides, shadowed Jinja templates and an English label catalogue. No `newsroom-core` change.

## Product and topic queries on custom schemes

Read this before writing products, section filters, navigations or topics for the demo.

### What the mapping actually is

`WireItem.subject` (newsroom-core `newsroom/types/wire.py`) overrides the ContentAPI schema with:

```python
subject: Annotated[list[CVItemWithCode], fields.nested_list(include_in_parent=True), Field(default_factory=list)]
```

`CVItemWithCode` (superdesk-core `superdesk/types/base.py`) has `code`, `name`, `schema`, `scheme`,
all `fields.Keyword`. `superdesk/core/elastic/mapping.py` turns `nested_list(include_in_parent=True)`
into `{"type": "nested", "include_in_parent": true, "properties": {...}}`.

So the Elasticsearch mapping for wire items is:

- `subject` is a **nested** field, and
- because of `include_in_parent: true`, every `subject.*` value is **also** indexed flat on the root
  document.

### Answer

**`subject.code:europe` in a product `query` works.** It does not need `subject.name`, and nothing
extra has to be added to `include_in_parent` / `include_in_root`: `include_in_parent` is already on.
Custom schemes are not special, they are ordinary `subject` entries with a `scheme`.

Why it works, step by step:

- A product query is applied in `newsroom/search/filters.py::apply_products_filter`, which calls
  `query_string_for_section(section, product.query)` and appends it to `query.should`.
- `newsroom/search/utils.py::query_string_for_section` builds a plain
  `{"query_string": {...}}` with `fields = WIRE_SEARCH_FIELDS`. That is a root-scope query, not a
  `nested` query. On a bare nested field a root-scope query would silently match nothing; with
  `include_in_parent: true` the flattened copies on the root document are matched, so it does match.
- `WIRE_SEARCH_FIELDS` not listing `subject` does not matter. In Elasticsearch an explicit
  `field:value` prefix inside the query text overrides the `fields` parameter; `fields` only applies
  to unqualified terms.
- This is an existing, shipped newsroom-core behaviour, not a guess: `newsroom/templates/wire_item.html`
  links every subject tag to `?q=subject.name:"<name>"`, and `newsroom/templates/search_tips_regular.html`
  documents `subject.name:Automobile` to end users. Both go through the same `query_string` path
  (`apply_query_string`, same `WIRE_SEARCH_FIELDS`). `newsroom/news_api/news/filters.py` likewise maps
  the `subject` API parameter to a root-scope terms filter on `subject.code`.

### Use `subject.code`, not `subject.name`

Both work. Prefer `code`:

- `code` and `name` are `keyword` fields, so query_string matches them **exactly**, with no analysis.
  `subject.name:Civil unrest` parses as `subject.name:Civil` AND `unrest` against the default fields.
  A multi-word name must be quoted: `subject.name:"Civil unrest"`.
- Our qcodes are single lowercase tokens (`europe`, `logistics`, `critical`, `pl`), so they need no
  quoting and do not break when a label is renamed.

### The one real caveat: `include_in_parent` loses correlation

The flattened root copies are independent multi-valued fields. The root document does not know which
`code` came from which `scheme`. So:

- `subject.scheme:region AND subject.code:europe` is **not** "has a region subject whose code is
  europe". It is "has some subject with scheme region" AND "has some subject with code europe", which
  can be two different entries.
- In practice this is harmless for the demo, because the contract's qcodes are unique across all six
  schemes (`severity`, `threat_type`, `region`, `country`, `sector`, `tlp` share no qcode). Query the
  code alone and drop the scheme term.
- Only a real `nested` query correlates the two, and product queries cannot express one: `query` is a
  query_string, not raw ES DSL.

### Recommended product queries (copy these)

| Entitlement | Product `query` |
|---|---|
| Nordfreight: Europe AND logistics | `subject.code:europe AND subject.code:logistics` |
| Aurelia: (Europe OR MENA) AND pharma | `(subject.code:europe OR subject.code:mena) AND subject.code:pharma` |
| Castellan: MENA AND energy | `subject.code:mena AND subject.code:energy` |

Tier packages filter on the report type, which is `profile` on the pushed item, so combine with e.g.
`profile:alert`. Verify the exact `profile` value the Superdesk NINJS formatter emits before relying
on it; `profile` is indexed as `text` (ContentAPI `schema["profile"] = {"type": "string"}`), not
keyword, so it is analysed and lowercased.

The default operator is `AND` (`ElasticDefaultOperator.AND`), so a query with no operators is an AND
of its terms. Write the operators anyway; it reads better.

### Topics are different: topic `filter` uses the display NAME

A topic has both a `query` (free text, goes through the same query_string path, so `subject.code:...`
works there too) and a `filter` dict. The `filter` dict is the filter-group mechanism and it is the
only path that produces a true `nested` query:

`newsroom/search/utils.py::get_filter_query` turns `{"<group field>": [values]}` into

```json
{"nested": {"path": "subject", "query": {"bool": {"filter": [
  {"term": {"subject.scheme": "<group value>"}},
  {"terms": {"subject.<searchfield>": ["<values>"]}}
]}}}}
```

`searchfield` defaults to `"name"` and this branch keeps the default, because the aggregation buckets
that feed the UI are built from `WIRE_AGGS["subject"]["terms"]["field"] = "subject.name"`. So:

- a topic `filter` must carry **display names**, not qcodes:
  `{"severity": ["Critical"], "region": ["Europe"], "country": ["Poland"]}`
- the group key is the `field` of the `WIRE_GROUPS` entry (`severity`, `threat_type`, `region`,
  `country`, `sector`, `tlp`), which this branch sets equal to the scheme id.
- this path *is* correlated, so it is exact. Prefer it for topics.

The contract's "High severity, Poland" watch is therefore:

```json
{"filter": {"severity": ["High"], "country": ["Poland"]}}
```

### Pushed items must carry the scheme

`newsroom/push/publishing.py` drops every `subject` entry whose `scheme` is not in
`WIRE_SUBJECT_SCHEME_WHITELIST` when that list is non-empty, including entries with no scheme at all.
All six schemes are whitelisted in `settings.py`. Anything Superdesk pushes with another scheme, or
with no scheme, is discarded on ingest and will never appear in a filter, a preview or an output.

`newsroom/push/utils.py::format_qcode_items` copies `qcode` to `code` on ingest, so Superdesk sending
either key is fine; the portal always stores and queries `code`.

## What is configured where

### `server/settings.py` (real configuration)

Loaded by `BaseNewsroomApp.load_app_instance_config` with `config.from_pyfile` from the process
working directory, after `newsroom/web/default_settings.py`, so every key here overrides a core
default. Only upper case names are read, which is why the helper names in that file start with `_`.

| Area | Keys |
|---|---|
| Branding | `SITE_NAME`, `COPYRIGHT_HOLDER`, `COPYRIGHT_NOTICE`, `USAGE_TERMS`, `CONTACT_ADDRESS`, `PRIVACY_POLICY`, `TERMS_AND_CONDITIONS`, `SHOW_COPYRIGHT`, `MAIL_DEFAULT_SENDER`, `EMAIL_DEFAULT_SENDER_NAME`, `AUTH_PROVIDERS` |
| Section labels | `HOME_SECTION`, `WIRE_SECTION`, `AGENDA_SECTION`, `MONITORING_SECTION`, `SAVED_SECTION` |
| Locale | `LANGUAGES`, `DEFAULT_LANGUAGE`, `DEFAULT_TIMEZONE`, `BABEL_DEFAULT_TIMEZONE`, `TRANSLATIONS_PATH` |
| Superdesk push | `PUSH_KEY`, `WIRE_SUBJECT_SCHEME_WHITELIST`, `AGENDA_CSV_SUBJECT_SCHEMES` |
| Instance apps | `INSTALLED_APPS` |
| Closed portal | `SHOW_USER_REGISTER`, `SIGNUP_EMAIL_RECIPIENTS`, `GOOGLE_LOGIN`, `NEWS_API_ENABLED` |
| Filters | `WIRE_GROUPS`, `AGENDA_GROUPS`, `WIRE_AGGS`, `WIRE_SEARCH_FIELDS`, `WIRE_TIME_FILTERS` |
| Feed behaviour | `DISPLAY_ABSTRACT`, `WIRE_NOTIFICATIONS_ON_CORRECTIONS`, `DEFAULT_SCHEDULED_NOTIFICATION_TIMES`, `CLIENT_CONFIG` |

Things in there that are not obvious:

- **`PUSH_KEY` must be bytes.** `newsroom/push/utils.py::test_signature` calls `hmac.new(key, ...)`.
  The value is fixed to `b"briefdesk-demo-push-key"` and the environment is not read, because Fireq
  exports `PUSH_KEY="newsroom"` to every Newsroom test instance and the Superdesk demo seed signs
  with the fixed value. A real deployment would read it from the environment again.
- **`BABEL_DEFAULT_TIMEZONE` has to be set alongside `DEFAULT_TIMEZONE`.** Core derives it once at
  import time in `default_settings.py`, so overriding only `DEFAULT_TIMEZONE` would leave Babel on
  the server's local zone.
- **`CLIENT_CONFIG` has to be restated.** Core builds that dict at import time from
  `DEFAULT_TIMEZONE`, `DISPLAY_ABSTRACT` and `DEFAULT_SCHEDULED_NOTIFICATION_TIMES`, so overriding
  those settings alone never reaches the browser. `settings.py` shallow copies the core dict and
  replaces the top level keys, which keeps every other client default intact.
- **`sys.path`.** `settings.py` puts the server directory on `sys.path` so `INSTALLED_APPS` entries
  such as `briefdesk_map` import by name regardless of how the process was started.
- **The AAP legacy sections are already off.** `newsroom.am_news`, `newsroom.factcheck`,
  `newsroom.media_releases` and `newsroom.market_place` are not in core's `CORE_APPS` or `MODULES`.
  They only appear when an instance adds them to `INSTALLED_APPS`, which this one does not. There is
  nothing to switch off; the sections simply never register.
- **`INSTALLED_APPS`, not `MODULES`.** `BaseNewsroomApp.__init__` runs `setup_apps(CORE_APPS)` and
  then `setup_apps(INSTALLED_APPS)`, both of which call `init_app(app)` on the imported module.
  `MODULES` is the async module list and requires a `module = Module(...)` instance instead; putting
  an `init_app` style package there raises `Module '...' is missing a 'module' instance` at boot.
  `briefdesk_map` registers its own blueprint inside `init_app`, so it must not also appear in
  `BLUEPRINTS`: `setup_blueprints` runs after `setup_apps` and a second registration of the same
  blueprint name fails.
- **The News API.** `NEWS_API_ENABLED = False` turns off the `api_tokens` blueprint and the API tabs
  in company and user admin for the web app. The separate `newsapi` process in the `Procfile` reads
  `settings_newsapi.py`, which still forces it on. That file is out of scope for this branch, so the
  answer is simply not to start the `newsapi` process. Run `web`, `websocket`, `worker` and `beat`.
- **Filter groups.** Removing `subject` from `WIRE_GROUPS` in favour of nested per scheme groups is
  the supported path, not a workaround: `newsroom/commands/fix_topic_nested_filters.py` exists to
  migrate saved topics after exactly that change. The AAP news groups (`genre`, `service`, `urgency`,
  `place`) are gone because nothing in the demo populates them and an empty group still renders its
  heading. `nested.searchfield` is left at its default of `name`, which is what the aggregation
  buckets are keyed on.

### `server/theme/` (real configuration)

`NewsroomWebApp.__init__` sets `theme_folder` to `SERVER_PATH/theme` and puts it first in
`_theme_folders`, which is both the Jinja loader search path and the lookup path for
`theme_url(filename)`. The folder is also served at `/theme/<filename>`.

The filenames core looks for, verified in `base_layout.html`, `layout_without_bars.html`,
`logo.html` and `login_logo.html`:

| File | Used by | Contents here |
|---|---|---|
| `favicon.ico` | `base_layout.html`, `layout_without_bars.html` | copy of `assets/favicon.ico` |
| `theme.css` | `base_layout.html`, `layout_without_bars.html` | the Briefdesk palette |
| `newshub_logo.svg` | `logo.html`, the top navigation | copy of `assets/briefdesk-logo_white.svg` (the bar is navy) |
| `login-logo.svg` | `login_logo.html` | copy of `assets/briefdesk-logo.svg`, because the login card is white. `templates/login.html` wraps it in the `.login-logo` element core's stylesheet expects |

`briefdesk-logo.svg` (dark version) and `briefdesk-mark.svg` are also in the folder. Nothing
references them yet; they are there so anything added later can reach them at `/theme/<name>`.

There is no email logo lookup. Core's email templates carry no image at all, and a remote SVG in an
HTML email is blocked by most clients, so the email branding is text. A branded HTML email formatter
is a small build and is already on the ledger as one.

**Palette and contrast.** `theme.css` only restates the custom properties from
`assets/styles/custom-variables.scss`. The SCSS helpers `alpha()` and `lightness()` compile to
`hsl(var(--x-h), var(--x-s), var(--x-l))`, so `--color-primary` is redefined as all four values, not
just the one.

- Top navigation and sidenav: ink navy `#10243E`, white foreground. 15.6:1.
- Primary buttons, links and focus: `hsl(156, 80%, 27%)`, a darker relative of the brand green, with
  white text. 5.2:1. **White on the brand green `#1FB57A` is 2.6:1 and fails AA**, so the brand green
  is only used where it carries no small text: the notification badge (navy on green, 5.9:1), the
  sidenav badge, and the logo.
- Content area: neutral greys, so the severity colours in the content are the only strong colour.

**Severity styling, CSS only.** `assets/wire/components/PreviewTagsSubjects.tsx` groups an item's
subjects by scheme whenever the scheme is a configured filter group, labels each block with the
group's label, and renders each value through `PreviewTagsLink` as

```html
<a class="wire-column__preview__tag" href="<prefix><urlencoded {"severity":["Critical"]}>">Critical</a>
```

The urlencoded filter in the `href` is the **only** hook on the existing markup that identifies both
the scheme and the value; there is no class or data attribute carrying either. `theme.css` therefore
matches on `[href*="%22severity%22%3A%5B%22Critical%22%5D"]` and friends, and draws a coloured bar on
the inline start edge plus a pale tint. The text keeps near black on near white, and the colour is
redundant with the tag text, which always spells the severity out.

What this cannot do without a newsroom-core client change:

- **No severity badge or colour in the list.** `WireListItem` renders only the `metadata_fields`
  components (`MAP_FIELD_TO_COMPONENT` in `assets/wire/components/fields/index.tsx`), and an unknown
  field name only renders if `item[field]` is a string. `subject` is an array, so it is skipped. The
  feed list shows no severity at all.
- **No severity first sorting.** The feed sorts by `versioncreated`.
- Both are already on the demo ledger as "not in the demo".

### `server/theme/briefdesk_ui_config.wire.json` (for the seed agent, not loaded from here)

This is **not** read from the theme folder. It is the desired `ui_config` documents for the `wire`,
`home` and `agenda` sections. `ui_config` lives in MongoDB and is loaded by
`python manage.py newsroom initialize_data`, which reads `SERVER_PATH/data/ui_config.json` in
preference to core's `newsroom/init_data/ui_config.json`
(`newsroom/commands/initialize_data.py`). `server/data/` is not owned by this work package, so the
file sits in `server/theme/` for whoever owns the seed step.

**Action for the seed agent's owner:** copy it to `server/data/ui_config.json` and run
`python manage.py newsroom initialize_data -n ui_config`. `init_version` is `2`; core ships `1`, and
`newsroom/commands/utils.py::async_entity_import` only patches an existing document when the file's
`init_version` is higher, so this replaces core's without `--force`.

It shows severity, threat type, region, country, sector and TLP in the preview and detail panes
(the keys are the scheme ids, matched by `isDisplayed(scheme, displayConfig)`), hides the unschemed
`subjects` block, hides `genre`, `services`, `wordcount` and `charcount`, and sets the metadata
lines to source, previous versions and the release time.

Note that the theme folder is served publicly at `/theme/<filename>`, so this file is readable
without logging in. It contains nothing sensitive, but move or delete it once it has been copied.

### `server/translations/` (real configuration)

`TRANSLATIONS_PATH` is appended to `BABEL_TRANSLATION_DIRECTORIES` after the core catalogue by
`newsroom/factory/app.py::setup_babel`. `quart_babel`'s `Domain.get_translations` merges the
directories in order and a later merge wins, so entries here override newsroom-core's English.

The same catalogue reaches the browser: `newsroom/templates/scripts.html` serialises
`get_client_translations()`, which is the merged catalogue, into `window.translations`, and
`assets/utils.tsx::gettext` looks each string up by exact match. So one catalogue covers both the
Jinja templates and the React client.

- `build_en.py` generates the catalogue. Standard library only, so it runs without the server's
  virtualenv. It reads newsroom-core's `messages.pot` (which covers both `newsroom/` and `assets/`,
  see the `[extract_messages]` section of newsroom-core's `setup.cfg`), applies word rules plus an
  override table, and writes both files. Message ids must match core character for character or the
  override silently does nothing, which is why the ids are read from the pot rather than typed.

  ```
  cd server/translations
  python3 build_en.py                                   # reads origin/develop of the newsroom-core checkout
  NEWSROOM_CORE=/path/to/newsroom-core python3 build_en.py
  python3 build_en.py /path/to/messages.pot
  ```

  It prints a warning for any override that no longer matches a message id, which is what to watch
  after a newsroom-core bump.

- `en/LC_MESSAGES/messages.po` and `en/LC_MESSAGES/messages.mo`, 102 entries. **The `.mo` is
  committed on purpose.** Only the compiled file is read at runtime, and nothing compiles catalogues
  for us: the `Dockerfile` installs requirements and copies the tree, the `Procfile` starts servers,
  and neither runs `pybabel compile`. newsroom-core does the same thing, committing the `.mo` next to
  the `.po` for its `fi` and `fr_CA` catalogues. If a build step is ever added, it is
  `pybabel compile -d server/translations -D messages`.

Applied: Wire to Intelligence Feed, Agenda to Risk Calendar, Topic and Topics to Watch and Watches,
Coverage to Deliverable, Slugline to Reference, Headline to Title, story, stories and article to
report and reports, Newsroom and Newshub to Briefdesk Portal. `{{ placeholder }}` spans are protected
from the rules because they carry a config value, not the English word.

**Company is deliberately left alone.** A client user reads their own organisation as their company;
"Client" is how the operator refers to them, not how they refer to themselves, and renaming "Company
Admin" to "Client Admin" makes the client's own admin screen read as if it belonged to someone else.

### `server/templates/` (shadowed templates, the least real part of this branch)

`NewsroomWebApp` puts `SERVER_PATH/templates` second in the Jinja search path, ahead of core's own
template folder, so a file of the same name shadows core's. Each of these is a copy of the
`origin/develop` original with wording and branding changed and nothing else.

| Shadow | Overrides in newsroom-core | Why |
|---|---|---|
| `login.html` | `newsroom/templates/login.html` | core's is an empty extend and leaves the `login_logo` block empty, so no logo shows unless an instance fills it. The heading comes from the catalogue, not from here |
| `footer.html` | `newsroom/templates/footer.html` | adds the operator line, links unchanged |
| `page-copyright.html` | `newsroom/templates/page-copyright.html` | core's text is written for a news agency redistributing wire copy; replaced with handling and TLP terms |
| `email_footer.html` | `newsroom/templates/email_footer.html` | core signs every email off with the Sourcefabric credit, which a client of the operator should not see |
| `email_layout.txt` | `newsroom/templates/email_layout.txt` | the same footer, inline in core's plain text layout, so the whole layout has to be shadowed |
| `email_item.html`, `email_item.txt` | same names | the field labels are literal strings, not `gettext` calls, so the catalogue cannot reach them. Slugline to Reference, Headline dropped for the title, Category replaced by the six schemes, Published to Released |
| `scheduled_notification_topic_matches_email.html`, `.txt` | same names | the digest email's table heading and body wording; same reason, literal strings |
| `share_items.html`, `.txt` | same names | "articles" to "reports" |
| `search_tips_regular.html` | `newsroom/templates/search_tips_regular.html` | core's is written for a wire agency and names The Canadian Press throughout. Replaced with the field names and filter groups this instance actually has, including the `subject.code` syntax above |

`email_layout.html` is **not** shadowed. It includes `email_footer.html`, which is, so the HTML email
branding changes with one file. The new item notification emails
(`new_wire_notification_email.*`, `new_item_notification.*`) are not shadowed either; they only
include `email_item.*` and the layout.

`email_layout.fr_ca.*` and `share_items.fr_ca.*` were already in this folder and are untouched.
`LANGUAGES` is `["en"]`, so they are dead but harmless.

## Manual steps that cannot be done from files

1. **Compile nothing, but do rebuild elastic.** `WIRE_GROUPS` changes the aggregations, not the
   mapping, so no reindex is needed for them. A fresh instance still needs
   `python manage.py newsroom initialize_data` once.
2. **`ui_config`** lives in MongoDB. See the seed agent note above.
3. **Products, companies, users, watches** are all database records, created through the settings UI
   or the seed script. Product queries: use the `subject.code:...` syntax in the table above.
4. **The Superdesk side** needs a recipient with an HTTP push destination to `<PORTAL_URL>/push`,
   format "Newsroom NINJS", secret `briefdesk-demo-push-key`.
5. **Change the admin password.** `admin@example.com` keeps whatever password the instance was
   created with.
6. **General settings** that are database backed, not config: the news only filter query and
   `wire_time_limit_days` under Settings. Leave both empty for the demo.

## Not verified

Nothing here was run against a live instance. Everything above was read out of `origin/develop` of
newsroom-core and superdesk-core. `settings.py` was executed the way `config.from_pyfile` executes
it, with the two `newsroom` imports stubbed, and the generated `.mo` was loaded with Babel the way
`quart_babel` loads it, but no Elasticsearch query was ever issued. In particular the claim that
`subject.code:europe` matches through `include_in_parent` is read from the mapping code and from
newsroom-core's own shipped `?q=subject.name:"..."` links, not from a query against a real index.
The day one spike in the demo plan is what confirms it.
