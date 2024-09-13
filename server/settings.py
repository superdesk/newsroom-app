import os
import pathlib

SERVER_PATH = pathlib.Path(__file__).resolve().parent
CLIENT_PATH = SERVER_PATH.parent.joinpath("client")

WEBPACK_MANIFEST_PATH = os.environ.get(
    "WEBPACK_MANIFEST_PATH", CLIENT_PATH.joinpath("dist", "manifest.json")
)

WIRE_AGGS = {
    "genre": {"terms": {"field": "genre.name", "size": 50}},
    "service": {"terms": {"field": "service.name", "size": 50}},
    "subject": {"terms": {"field": "subject.name", "size": 100}},
    "urgency": {"terms": {"field": "urgency"}},
    "place": {"terms": {"field": "place.name", "size": 50}},
}

SHOW_USER_REGISTER = True
