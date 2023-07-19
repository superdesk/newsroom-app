import os
import pathlib

SERVER_PATH = pathlib.Path(__file__).resolve().parent
CLIENT_PATH = SERVER_PATH.parent.joinpath("client")

WEBPACK_MANIFEST_PATH = os.environ.get(
    "WEBPACK_MANIFEST_PATH", CLIENT_PATH.joinpath("dist", "manifest.json")
)
