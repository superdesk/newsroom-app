#!/usr/bin/env python3
"""Seed a Newsroom instance into the Briefdesk portal demo state.

Two transports, one data file (``briefdesk_portal.json``):

``local``
    Run on the instance itself. Creates the newsroom app and writes through its own
    services. This is the only transport that can set user passwords, create Watches
    (topics) owned by somebody other than the caller and write personal home
    dashboards, so it is the one that produces the complete demo state.

``http``
    Run from anywhere against ``PORTAL_URL``. Logs in as the portal administrator and
    uses the same JSON and form endpoints the React admin UI uses. It cannot set
    passwords (no endpoint sets one), cannot create a Watch for another user (the
    topic endpoints are guarded by ``url_arg_must_be_current_user``), and cannot write
    personal dashboards, ``ui_config`` or monitoring profiles. Those sections report
    themselves as skipped.

Both transports are idempotent: everything is looked up by name or email first, then
created or updated. ``--dry-run`` touches nothing and needs no instance at all.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
SERVER_DIR = HERE.parent.parent
DEFAULT_DATA_FILE = HERE / "briefdesk_portal.json"
DEFAULT_USER_PASSWORD = "Briefdesk-demo-1"

SECTIONS = [
    "cleanup",
    "navigations",
    "products",
    "companies",
    "users",
    "topics",
    "dashboards",
    "cards",
    "ui_config",
    "monitoring",
]

# The ui_config documents belong to the theme and settings work package. Applied only when
# the file is there. Same shape as newsroom/init_data/ui_config.json: a list of documents,
# each with its own _id naming the section it configures.
UI_CONFIG_FILES = [SERVER_DIR / "theme" / "briefdesk_ui_config.wire.json"]

# Fields the local transport has to hand to the services as real ObjectIds.
OBJECT_ID_FIELDS = {"company", "user", "folder", "monitoring_administrator"}
OBJECT_ID_LIST_FIELDS = {"navigations", "navigation", "users"}


class SeedError(Exception):
    pass


class Log:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.skipped: List[str] = []

    def section(self, name: str) -> None:
        print(f"\n== {name}")

    def action(self, verb: str, kind: str, name: str) -> None:
        prefix = "would " if self.dry_run else ""
        print(f"   {prefix}{verb} {kind} {name!r}")

    def unchanged(self, kind: str, name: str) -> None:
        print(f"   unchanged {kind} {name!r}")

    def info(self, message: str) -> None:
        print(f"   {message}")

    def skip(self, message: str) -> None:
        print(f"   SKIPPED: {message}")
        self.skipped.append(message)


def values_match(current: Any, wanted: Any) -> bool:
    """Compare a stored value with the wanted one, tolerating str versus ObjectId."""

    if isinstance(wanted, dict) and isinstance(current, dict):
        return all(values_match(current.get(key), val) for key, val in wanted.items())
    if isinstance(wanted, list) and isinstance(current, list):
        if len(wanted) != len(current):
            return False
        return all(values_match(c, w) for c, w in zip(current, wanted))
    if wanted is None:
        return current is None
    return str(current) == str(wanted)


def changed_fields(current: dict, wanted: dict) -> List[str]:
    return sorted(key for key, val in wanted.items() if not values_match(current.get(key), val))


# --------------------------------------------------------------------------------------
# backends
# --------------------------------------------------------------------------------------


class Backend:
    """The resource operations the seeder needs, independent of how they reach a portal."""

    name = "backend"
    can_set_passwords = False
    can_write_ui_config = False
    can_write_monitoring = False
    can_write_other_users_topics = False
    can_write_user_dashboards = False
    # fields this transport silently drops, so the seeder does not report them as
    # changed on every run
    unwritable_fields: Dict[str, set] = {}

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def find(self, resource: str, field: str, value: str) -> Optional[dict]:
        raise NotImplementedError

    async def create(self, resource: str, doc: dict) -> str:
        raise NotImplementedError

    async def update(self, resource: str, item_id: str, doc: dict) -> None:
        raise NotImplementedError

    async def delete(self, resource: str, item_id: str) -> None:
        raise NotImplementedError

    async def set_password(self, user_id: str, password: str) -> None:
        raise NotImplementedError

    async def find_topic(self, owner_id: str, label: str) -> Optional[dict]:
        raise NotImplementedError


class DryRunBackend(Backend):
    """Pretends the portal is empty. Used by --dry-run so it needs no instance."""

    name = "dry-run"

    def __init__(self, transport: str):
        template = HttpBackend if transport == "http" else LocalBackend
        self.name = f"dry-run ({transport})"
        self.can_set_passwords = template.can_set_passwords
        self.can_write_ui_config = template.can_write_ui_config
        self.can_write_monitoring = template.can_write_monitoring
        self.can_write_other_users_topics = template.can_write_other_users_topics
        self.can_write_user_dashboards = template.can_write_user_dashboards
        self.unwritable_fields = template.unwritable_fields

    async def find(self, resource: str, field: str, value: str) -> Optional[dict]:
        return None

    async def find_topic(self, owner_id: str, label: str) -> Optional[dict]:
        return None

    async def delete(self, resource: str, item_id: str) -> None:
        return None


# --- HTTP ------------------------------------------------------------------------------

CSRF_RE = re.compile(r'name="csrf_token"[^>]*?value="([^"]+)"')
CSRF_RE_ALT = re.compile(r'value="([^"]+)"[^>]*?name="csrf_token"')


class HttpBackend(Backend):
    """Talks to a running portal as the administrator, over the web admin endpoints."""

    name = "http"
    can_set_passwords = False
    can_write_ui_config = False
    can_write_monitoring = False
    can_write_other_users_topics = False
    can_write_user_dashboards = False
    # newsroom.navigations.views.prepare_navigation_data never reads `order`
    unwritable_fields = {"navigations": {"order"}}

    def __init__(self, base_url: str, email: str, password: str, log: Log):
        self.base = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.log = log
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def _request(self, method: str, path: str, data=None, content_type=None) -> bytes:
        url = path if path.startswith("http") else f"{self.base}{path}"
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/json")
        if content_type:
            request.add_header("Content-Type", content_type)
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")[:800]
            raise SeedError(f"{method} {url} -> HTTP {err.code}: {body}") from err
        except urllib.error.URLError as err:
            raise SeedError(f"{method} {url} -> {err.reason}") from err

    @staticmethod
    def _decode(raw: bytes) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            # login and a few other endpoints answer with a redirect to HTML
            return None

    def _get(self, path: str) -> Any:
        return self._decode(self._request("GET", path))

    def _post_json(self, path: str, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        return self._decode(self._request("POST", path, body, "application/json"))

    def _post_form(self, path: str, fields: Dict[str, str]) -> Any:
        body = urllib.parse.urlencode(fields).encode("utf-8")
        content_type = "application/x-www-form-urlencoded; charset=UTF-8"
        return self._decode(self._request("POST", path, body, content_type))

    @staticmethod
    def _new_id(response: Any, path: str) -> str:
        if not isinstance(response, dict) or not response.get("_id"):
            raise SeedError(f"POST {path} did not answer with a new _id: {response!r}")
        return str(response["_id"])

    async def open(self) -> None:
        page = self._request("GET", "/login").decode("utf-8", "replace")
        match = CSRF_RE.search(page) or CSRF_RE_ALT.search(page)
        if not match:
            raise SeedError("no csrf_token on the login page, is PORTAL_URL a newsroom?")
        self._post_form(
            "/login",
            {"email": self.email, "password": self.password, "csrf_token": match.group(1)},
        )
        # /companies/search is account-manager-only, so a 200 proves both that the
        # session took and that the account has the rights the rest of the run needs
        if self._get("/companies/search?q=") is None:
            raise SeedError(f"login as {self.email} failed, check PORTAL_ADMIN_PASSWORD")
        self.log.info(f"logged in to {self.base} as {self.email}")

    async def find(self, resource: str, field: str, value: str) -> Optional[dict]:
        quoted = urllib.parse.quote(value)
        paths = {
            "companies": f"/companies/search?q={quoted}",
            "products": f"/products/search?q={quoted}",
            "navigations": f"/navigations/search?q={quoted}",
            "users": f"/users/search?q={quoted}",
            "cards": f"/cards/search?q={quoted}",
        }
        if resource not in paths:
            raise SeedError(f"{resource} cannot be read over HTTP")
        for item in self._get(paths[resource]) or []:
            if str(item.get(field, "")).lower() == value.lower():
                return item
        return None

    async def create(self, resource: str, doc: dict) -> str:
        if resource == "companies":
            return self._new_id(self._post_json("/companies/new", doc), "/companies/new")
        if resource == "products":
            return self._new_id(self._post_json("/products/new", doc), "/products/new")
        if resource == "navigations":
            payload = {"navigation": json.dumps(doc)}
            return self._new_id(self._post_form("/navigations/new", payload), "/navigations/new")
        if resource == "users":
            return self._new_id(self._post_form("/users/new", user_form_fields(doc)), "/users/new")
        if resource == "cards":
            payload = {"card": json.dumps(doc)}
            return self._new_id(self._post_form("/cards/new", payload), "/cards/new")
        raise SeedError(f"{resource} cannot be created over HTTP")

    async def update(self, resource: str, item_id: str, doc: dict) -> None:
        if resource == "companies":
            self._post_json(f"/companies/{item_id}", doc)
        elif resource == "products":
            # the edit endpoint rebuilds the product from the payload and ignores
            # navigations, which has an endpoint of its own
            payload = {key: val for key, val in doc.items() if key != "navigations"}
            self._post_json(f"/products/{item_id}", payload)
            if doc.get("navigations") is not None:
                self._post_json(
                    f"/products/{item_id}/navigations", {"navigations": doc["navigations"]}
                )
        elif resource == "navigations":
            self._post_form(f"/navigations/{item_id}", {"navigation": json.dumps(doc)})
        elif resource == "users":
            self._post_form(f"/users/{item_id}", user_form_fields(doc))
        elif resource == "cards":
            self._post_form(f"/cards/{item_id}", {"card": json.dumps(doc)})
        else:
            raise SeedError(f"{resource} cannot be updated over HTTP")

    async def delete(self, resource: str, item_id: str) -> None:
        if resource not in ("cards", "products"):
            raise SeedError(f"{resource} cannot be deleted over HTTP")
        # both endpoints take an optional If-Match, so a plain DELETE is accepted
        self._request("DELETE", f"/{resource}/{item_id}")


def user_form_fields(doc: dict) -> Dict[str, str]:
    """Render a user document as the fields ``newsroom.users.forms.UserForm`` reads.

    The endpoint is a WTForms POST, not JSON. ``BooleanField.false_values`` accepts the
    string "false", and the list fields are comma separated.
    """

    fields: Dict[str, str] = {}
    for key in ("first_name", "last_name", "email", "phone", "mobile", "role", "locale"):
        if doc.get(key):
            fields[key] = str(doc[key])
    for key in ("user_type", "company"):
        if doc.get(key):
            fields[key] = str(doc[key])
    for key in (
        "is_validated",
        "is_enabled",
        "is_approved",
        "expiry_alert",
        "receive_email",
        "receive_app_notifications",
        "manage_company_topics",
    ):
        if key in doc:
            fields[key] = "true" if doc[key] else "false"
    if doc.get("products") is not None:
        fields["products"] = ",".join(str(product) for product in doc["products"])
    return fields


# --- local -----------------------------------------------------------------------------


class LocalBackend(Backend):
    """Writes through the newsroom services, from inside an app context on the instance."""

    name = "local"
    can_set_passwords = True
    can_write_ui_config = True
    can_write_monitoring = True
    can_write_other_users_topics = True
    can_write_user_dashboards = True

    def __init__(self, log: Log):
        self.log = log
        self._services: Dict[str, Any] = {}

    async def open(self) -> None:
        from newsroom.cards.service import CardsResourceService
        from newsroom.companies.companies_async import CompanyService
        from newsroom.monitoring.service import MonitoringProfileService
        from newsroom.navigations.service import NavigationsService
        from newsroom.products.service import ProductsService
        from newsroom.topics.topics_async import TopicService
        from newsroom.ui_config_async import UiConfigResourceService
        from newsroom.users.service import UsersAuthService

        self._services = {
            "companies": CompanyService(),
            "products": ProductsService(),
            "navigations": NavigationsService(),
            "users": UsersAuthService(),
            "topics": TopicService(),
            "cards": CardsResourceService(),
            "ui_config": UiConfigResourceService(),
            "monitoring": MonitoringProfileService(),
        }

    def _service(self, resource: str):
        try:
            return self._services[resource]
        except KeyError:
            raise SeedError(f"no service registered for {resource}")

    @staticmethod
    def _coerce(doc: dict) -> dict:
        """Turn the id strings the data file carries into the ObjectIds the models want."""

        from bson import ObjectId

        out = dict(doc)
        for key in OBJECT_ID_FIELDS:
            if isinstance(out.get(key), str):
                out[key] = ObjectId(out[key])
        for key in OBJECT_ID_LIST_FIELDS:
            if isinstance(out.get(key), list):
                out[key] = [ObjectId(value) if isinstance(value, str) else value for value in out[key]]
        if isinstance(out.get("products"), list):
            out["products"] = [
                dict(ref, _id=ObjectId(ref["_id"])) if isinstance(ref.get("_id"), str) else ref
                for ref in out["products"]
                if isinstance(ref, dict)
            ]
        if isinstance(out.get("dashboards"), list):
            out["dashboards"] = [
                dict(entry, topic_ids=[ObjectId(topic_id) for topic_id in entry["topic_ids"]])
                if isinstance(entry, dict) and entry.get("topic_ids")
                else entry
                for entry in out["dashboards"]
            ]
        if isinstance(out.get("subscribers"), list):
            out["subscribers"] = [
                dict(sub, user_id=ObjectId(sub["user_id"])) if isinstance(sub.get("user_id"), str) else sub
                for sub in out["subscribers"]
                if isinstance(sub, dict)
            ]
        return out

    async def find(self, resource: str, field: str, value: str) -> Optional[dict]:
        service = self._service(resource)
        if resource == "ui_config" or field == "_id":
            item = await service.find_by_id(value)
        else:
            pattern = re.compile(f"^{re.escape(value)}$", re.IGNORECASE)
            item = await service.find_one(**{field: pattern})
        return item.to_dict() if item is not None else None

    async def create(self, resource: str, doc: dict) -> str:
        items = await self._service(resource).create([self._coerce(doc)])
        first = items[0]
        return str(getattr(first, "id", first))

    async def update(self, resource: str, item_id: str, doc: dict) -> None:
        # the service converts the id to an ObjectId itself when the resource uses one
        await self._service(resource).update(item_id, self._coerce(doc))

    async def delete(self, resource: str, item_id: str) -> None:
        service = self._service(resource)
        item = await service.find_by_id(item_id)
        if item is not None:
            await service.delete(item)

    async def set_password(self, user_id: str, password: str) -> None:
        await self.update("users", user_id, {"password": password})

    async def find_topic(self, owner_id: str, label: str) -> Optional[dict]:
        from bson import ObjectId

        item = await self._service("topics").find_one(user=ObjectId(owner_id), label=label)
        return item.to_dict() if item is not None else None


# --------------------------------------------------------------------------------------
# seeder
# --------------------------------------------------------------------------------------


class Seeder:
    def __init__(self, data: dict, backend: Backend, log: Log, subject_filter_field: str):
        self.data = data
        self.backend = backend
        self.log = log
        self.subject_filter_field = subject_filter_field
        self.ids: Dict[str, Dict[str, str]] = {}

    def _remember(self, resource: str, name: str, item_id: str) -> str:
        self.ids.setdefault(resource, {})[name] = str(item_id)
        return str(item_id)

    async def _require(self, resource: str, field: str, name: str) -> str:
        cached = self.ids.get(resource, {}).get(name)
        if cached:
            return cached
        found = await self.backend.find(resource, field, name)
        if found:
            return self._remember(resource, name, str(found["_id"]))
        if self.log.dry_run:
            return self._remember(resource, name, f"<{resource}:{name}>")
        raise SeedError(f"{resource} {name!r} not found, run the earlier sections first")

    async def _upsert(
        self,
        resource: str,
        key_field: str,
        key_value: str,
        wanted: dict,
        create_doc: Optional[dict] = None,
    ) -> Tuple[str, str]:
        """Create or update one document. Returns its id and what happened to it."""

        dropped = self.backend.unwritable_fields.get(resource, set())
        if dropped:
            wanted = {key: val for key, val in wanted.items() if key not in dropped}
            if create_doc is not None:
                create_doc = {k: v for k, v in create_doc.items() if k not in dropped}

        existing = await self.backend.find(resource, key_field, key_value)

        if existing is None:
            if self.log.dry_run:
                self.log.action("create", resource, key_value)
                return self._remember(resource, key_value, f"<{resource}:{key_value}>"), "created"
            item_id = await self.backend.create(resource, create_doc or wanted)
            self.log.action("create", resource, key_value)
            return self._remember(resource, key_value, item_id), "created"

        item_id = self._remember(resource, key_value, str(existing["_id"]))
        changed = changed_fields(existing, wanted)
        if not changed:
            self.log.unchanged(resource, key_value)
            return item_id, "unchanged"
        self.log.action("update", resource, key_value)
        self.log.info(f"     fields: {', '.join(changed)}")
        if not self.log.dry_run:
            # the edit endpoints rebuild the document from the payload, so send it whole
            await self.backend.update(resource, item_id, wanted)
        return item_id, "updated"

    def _filter_values(self, scheme: str, codes: List[str]) -> List[str]:
        if self.subject_filter_field == "code":
            return list(codes)
        vocabulary = self.data["vocabularies"].get(scheme, {})
        values = []
        for code in codes:
            if code not in vocabulary:
                raise SeedError(f"{code!r} is not a value of the {scheme!r} vocabulary")
            values.append(vocabulary[code])
        return values

    # -- sections

    async def cleanup(self) -> None:
        """Delete documents an earlier version of this seed created and no longer wants.

        Products and their home page cards are looked up by name, so a renamed or dropped
        entry in the data file leaves the old document behind. Deleting a product is safe
        even when it is still in use: ``ProductsService.on_deleted`` strips the reference
        from every company and user.
        """

        self.log.section("Cleanup")
        removals = self.data.get("cleanup") or {}
        for resource, key_field in (("cards", "label"), ("products", "name")):
            for name in removals.get(resource, []):
                existing = await self.backend.find(resource, key_field, name)
                if existing is None:
                    self.log.info(f"no {resource} {name!r} to delete")
                    continue
                self.log.action("delete", resource, name)
                if not self.log.dry_run:
                    await self.backend.delete(resource, str(existing["_id"]))

    async def navigations(self) -> None:
        self.log.section("Navigations")
        for nav in self.data["navigations"]:
            await self._upsert(
                "navigations",
                "name",
                nav["name"],
                {
                    "name": nav["name"],
                    "description": nav.get("description", ""),
                    "is_enabled": nav.get("is_enabled", True),
                    "product_type": nav.get("product_type", "wire"),
                    "order": nav.get("order"),
                },
            )

    async def products(self) -> None:
        self.log.section("Products")
        for product in self.data["products"]:
            navigation_ids = [
                await self._require("navigations", "name", name)
                for name in product.get("navigations", [])
            ]
            wanted = {
                "name": product["name"],
                "description": product.get("description", ""),
                "query": product["query"],
                # only read by the agenda search, where it is wrapped in a nested query on
                # `planning_items` without any field prefixing, so its field names have to be
                # written out in full (`planning_items.subject.code:...`)
                "planning_item_query": product.get("planning_item_query"),
                "is_enabled": product.get("is_enabled", True),
                "product_type": product.get("product_type", "wire"),
                "navigations": navigation_ids,
            }
            # /products/new hands the payload straight to the resource model, which
            # wants real ObjectIds; the navigations endpoint converts them for us
            create_doc = {key: val for key, val in wanted.items() if key != "navigations"}
            product_id, action = await self._upsert(
                "products", "name", product["name"], wanted, create_doc=create_doc
            )
            if action == "created" and navigation_ids and not self.log.dry_run:
                await self.backend.update("products", product_id, {"navigations": navigation_ids})

    def _product_type(self, name: str) -> str:
        for product in self.data["products"]:
            if product["name"] == name:
                return product.get("product_type", "wire")
        raise SeedError(f"{name!r} is not in the products section of the data file")

    async def companies(self) -> None:
        self.log.section("Companies")
        for company in self.data["companies"]:
            # `section` on the reference, not `product_type` on the product, is what
            # newsroom.products.utils.get_products_by_company_async filters a section's
            # products on, so the two have to agree or the section looks unsubscribed
            product_refs = [
                {
                    "_id": await self._require("products", "name", name),
                    "section": self._product_type(name),
                    "seats": 0,
                }
                for name in company.get("products", [])
            ]
            await self._upsert(
                "companies",
                "name",
                company["name"],
                {
                    "name": company["name"],
                    "url": company.get("url"),
                    "contact_name": company.get("contact_name"),
                    "contact_email": company.get("contact_email"),
                    "is_enabled": True,
                    "is_approved": True,
                    "expiry_date": None,
                    "archive_access": True,
                    "internal": company.get("internal", False),
                    "sections": company.get("sections", {"wire": True}),
                    "products": product_refs,
                },
            )

    async def users(self) -> None:
        self.log.section("Users")
        password = os.environ.get("PORTAL_USER_PASSWORD") or DEFAULT_USER_PASSWORD
        for user in self.data["users"]:
            company_id = await self._require("companies", "name", user["company"])
            user_id, _ = await self._upsert(
                "users",
                "email",
                user["email"],
                {
                    "first_name": user["first_name"],
                    "last_name": user["last_name"],
                    "email": user["email"],
                    "user_type": user["user_type"],
                    "company": company_id,
                    "is_validated": True,
                    "is_enabled": True,
                    "is_approved": True,
                    "receive_email": True,
                    "receive_app_notifications": True,
                    "manage_company_topics": user.get("manage_company_topics", False),
                },
            )
            if not self.backend.can_set_passwords:
                self.log.skip(
                    f"password for {user['email']}: nothing in the web API sets a "
                    "password, rerun with --transport local on the instance"
                )
            elif self.log.dry_run:
                self.log.info(f"     would set the password of {user['email']}")
            else:
                await self.backend.set_password(user_id, password)
                self.log.info(f"     password set for {user['email']}")

    async def _existing_user(self, email: str) -> Optional[Tuple[str, Optional[str]]]:
        """Look up a user the seed does not own. Returns its id and company id, or None.

        The deployment creates the portal administrator with its own password, role and no
        company, so this reads that document and never writes to it outside the one
        ``dashboards`` field the caller sets.
        """

        found = await self.backend.find("users", "email", email)
        if found is None:
            if self.log.dry_run:
                return self._remember("users", email, f"<users:{email}>"), None
            return None
        company = found.get("company")
        return (
            self._remember("users", email, str(found["_id"])),
            str(company) if company else None,
        )

    def _company_of(self, email: str) -> str:
        for user in self.data["users"]:
            if user["email"] == email:
                return user["company"]
        raise SeedError(f"{email} is not in the users section of the data file")

    async def _upsert_topic(self, topic: dict, company_id: Optional[str]) -> str:
        """Create or update one Watch, owned by ``topic["owner"]``. Returns its id.

        ``company_id`` may be None. A Watch of a user without a company has none either, which
        ``TopicResourceModel.company`` allows.
        """

        owner_id = await self._require("users", "email", topic["owner"])
        wanted = {
            "label": topic["label"],
            "topic_type": topic.get("topic_type", "wire"),
            "query": topic.get("query"),
            "filter": {
                scheme: self._filter_values(scheme, codes)
                for scheme, codes in (topic.get("filter") or {}).items()
            },
            "user": owner_id,
            "company": company_id,
            "is_global": topic.get("is_global", False),
            "subscribers": [
                {
                    "user_id": await self._require("users", "email", subscriber["user"]),
                    "notification_type": subscriber["notification_type"],
                }
                for subscriber in topic.get("subscribers", [])
            ],
        }
        existing = await self.backend.find_topic(owner_id, topic["label"])
        if existing is None:
            self.log.action("create", "topic", topic["label"])
            if self.log.dry_run:
                return f"<topic:{topic['owner']}:{topic['label']}>"
            return await self.backend.create(
                "topics", dict(wanted, original_creator=owner_id, version_creator=owner_id)
            )

        topic_id = str(existing["_id"])
        changed = changed_fields(existing, wanted)
        if not changed:
            self.log.unchanged("topic", topic["label"])
            return topic_id
        self.log.action("update", "topic", topic["label"])
        self.log.info(f"     fields: {', '.join(changed)}")
        if not self.log.dry_run:
            await self.backend.update("topics", topic_id, wanted)
        return topic_id

    async def topics(self) -> None:
        self.log.section("Watches (topics)")
        if not self.backend.can_write_other_users_topics:
            self.log.skip(
                "every Watch: POST /users/<id>/topics only accepts the logged in user, "
                "rerun with --transport local on the instance"
            )
            return
        for topic in self.data["topics"]:
            company_id = await self._require("companies", "name", self._company_of(topic["owner"]))
            await self._upsert_topic(topic, company_id)

    async def dashboards(self) -> None:
        """Give each user a personal home page built from Watches of their own.

        This is the only entitlement safe home page. The items of a personal dashboard are
        fetched by ``newsroom.wire.views.get_personal_dashboards_data``, which runs the
        normal wire search for the viewing user and company, so the company's products
        filter the result. Product backed home page cards skip that filter.

        An entry marked ``existing_user`` belongs to an account the seed does not own, such as
        the portal administrator the deployment creates. Only its ``dashboards`` field is
        written, and the entry is skipped when there is no such user.
        """

        self.log.section("Personal home dashboards")
        if not self.backend.can_write_user_dashboards:
            self.log.skip(
                "every personal home dashboard: newsroom.users.forms.UserForm has no "
                "dashboards field, rerun with --transport local on the instance"
            )
            return
        for dashboard in self.data.get("dashboards", []):
            owner = dashboard["owner"]
            if dashboard.get("existing_user"):
                resolved = await self._existing_user(owner)
                if resolved is None:
                    self.log.info(f"no user {owner!r} on this instance, no dashboard for them")
                    continue
                user_id, company_id = resolved
            else:
                user_id = await self._require("users", "email", owner)
                company_id = await self._require("companies", "name", self._company_of(owner))
            topic_ids = [
                await self._upsert_topic(dict(watch, owner=owner), company_id)
                for watch in dashboard.get("watches", [])
            ]
            name = dashboard["name"]
            wanted = {
                "dashboards": [
                    {
                        "name": name,
                        # only the config PERSONAL_DASHBOARD_CARD_TYPE decides how the cards
                        # are rendered, this is what the Personalize Home modal stores
                        "type": dashboard.get("type", "4-picture-text"),
                        "topic_ids": topic_ids,
                    }
                ]
            }
            existing = await self.backend.find("users", "email", owner)
            if existing is not None and not changed_fields(existing, wanted):
                self.log.unchanged("dashboard", f"{owner}: {name}")
                continue
            self.log.action("set", "dashboard", f"{owner}: {name}")
            if not self.log.dry_run:
                await self.backend.update("users", user_id, wanted)

    async def cards(self) -> None:
        self.log.section("Home page cards")
        for card in self.data["cards"]:
            config = dict(card.get("config") or {})
            if config.get("product"):
                config["product"] = await self._require("products", "name", config["product"])
            await self._upsert(
                "cards",
                "label",
                card["label"],
                {
                    "label": card["label"],
                    "type": card["type"],
                    "dashboard": card.get("dashboard", "newsroom"),
                    "order": card.get("order", 0),
                    "config": config,
                },
            )

    async def ui_config(self) -> None:
        self.log.section("UI config")
        if not self.backend.can_write_ui_config:
            self.log.skip(
                "ui_config: the web app exposes no ui_config endpoint. Rerun with "
                "--transport local, or drop the file at server/data/ui_config.json and "
                "run `python manage.py initialize_data -n ui_config -f`"
            )
            return
        for path in UI_CONFIG_FILES:
            if not path.exists():
                self.log.info(f"no {path.name}, leaving the ui_config documents alone")
                continue
            with path.open(encoding="utf-8") as handle:
                loaded = json.load(handle)
            documents = loaded if isinstance(loaded, list) else [loaded]
            for document in documents:
                section = document.get("_id")
                if not section:
                    raise SeedError(f"a ui_config document in {path.name} has no _id")
                config = {key: val for key, val in document.items() if key != "_id"}
                existing = await self.backend.find("ui_config", "_id", section)
                if existing is None:
                    self.log.action("create", "ui_config", section)
                    if not self.log.dry_run:
                        await self.backend.create("ui_config", dict(config, _id=section))
                else:
                    self.log.action("update", "ui_config", section)
                    if not self.log.dry_run:
                        await self.backend.update("ui_config", section, config)

    async def monitoring(self) -> None:
        self.log.section("Monitoring profiles")
        if not self.backend.can_write_monitoring:
            self.log.skip(
                "monitoring profiles: POST /monitoring/new wants a WTForms body and a "
                "JSON body in the same request, rerun with --transport local"
            )
            return
        for profile in self.data.get("monitoring", []):
            company_id = await self._require("companies", "name", profile["company"])
            user_ids = [
                await self._require("users", "email", email) for email in profile.get("users", [])
            ]
            await self._upsert(
                "monitoring",
                "name",
                profile["name"],
                {
                    "name": profile["name"],
                    "subject": profile.get("subject"),
                    "description": profile.get("description"),
                    "company": company_id,
                    "query": profile.get("query"),
                    "alert_type": profile.get("alert_type", "full_text"),
                    "format_type": profile.get("format_type", "monitoring_pdf"),
                    "is_enabled": profile.get("is_enabled", True),
                    "always_send": profile.get("always_send", False),
                    "headline_subject": profile.get("headline_subject", False),
                    "schedule": profile.get("schedule"),
                    "users": user_ids,
                },
            )

    async def run(self, sections: List[str]) -> None:
        for section in sections:
            await getattr(self, section)()


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a Newsroom instance into the Briefdesk portal demo state.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment:\n"
            "  PORTAL_URL             base URL of the portal, selects the http transport\n"
            "  PORTAL_ADMIN_EMAIL     portal administrator, default admin@example.com\n"
            "  PORTAL_ADMIN_PASSWORD  its password\n"
            f"  PORTAL_USER_PASSWORD   demo user password, default {DEFAULT_USER_PASSWORD}\n"
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["auto", "http", "local"],
        default="auto",
        help="auto picks http when PORTAL_URL is set, local otherwise",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=SECTIONS,
        metavar="SECTION",
        help=f"run these sections only, repeatable. One of: {', '.join(SECTIONS)}",
    )
    parser.add_argument("--dry-run", action="store_true", help="print, connect to nothing")
    parser.add_argument("--data", default=str(DEFAULT_DATA_FILE), help="path to the seed data")
    parser.add_argument(
        "--subject-filter-field",
        choices=["name", "code"],
        default="name",
        help=(
            "which subject field Watch filters carry. Must match `searchfield` in the "
            "WIRE_GROUPS nested config in server/settings.py, whose default is `name`"
        ),
    )
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, data: dict, log: Log, transport: str) -> None:
    sections = [section for section in SECTIONS if section in (args.only or SECTIONS)]

    if args.dry_run:
        backend: Backend = DryRunBackend(transport)
    elif transport == "http":
        backend = HttpBackend(
            os.environ["PORTAL_URL"].strip(),
            os.environ.get("PORTAL_ADMIN_EMAIL", "admin@example.com"),
            os.environ["PORTAL_ADMIN_PASSWORD"],
            log,
        )
    else:
        # the instance settings are read from the working directory
        os.chdir(SERVER_DIR)
        sys.path.insert(0, str(SERVER_DIR))
        from newsroom.web.factory import get_app

        app = get_app()
        backend = LocalBackend(log)
        print(f"Briefdesk portal seed, transport=local, sections={','.join(sections)}")
        async with app.app_context():
            await backend.open()
            await Seeder(data, backend, log, args.subject_filter_field).run(sections)
        return

    print(f"Briefdesk portal seed, transport={backend.name}, sections={','.join(sections)}")
    try:
        await backend.open()
        await Seeder(data, backend, log, args.subject_filter_field).run(sections)
    finally:
        await backend.close()


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    log = Log(args.dry_run)

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"seed data file not found: {data_path}", file=sys.stderr)
        return 2
    with data_path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    portal_url = os.environ.get("PORTAL_URL", "").strip()
    transport = args.transport
    if transport == "auto":
        transport = "http" if portal_url else "local"

    if transport == "http" and not args.dry_run:
        if not portal_url:
            print("PORTAL_URL is required for the http transport", file=sys.stderr)
            return 2
        if not os.environ.get("PORTAL_ADMIN_PASSWORD"):
            print("PORTAL_ADMIN_PASSWORD is required", file=sys.stderr)
            return 2

    try:
        asyncio.run(run(args, data, log, transport))
    except SeedError as err:
        print(f"\nFAILED: {err}", file=sys.stderr)
        return 1

    print("\nDone.")
    if log.skipped:
        print("Not done by this transport:")
        for message in log.skipped:
            print(f" - {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
