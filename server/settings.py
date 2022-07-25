import pathlib

from newsroom.web.default_settings import CLIENT_CONFIG


SERVER_PATH = pathlib.Path(__file__).resolve().parent
CLIENT_PATH = SERVER_PATH.parent.joinpath("client")

DISPLAY_ABSTRACT = True

CLIENT_CONFIG.update(
    display_abstract=DISPLAY_ABSTRACT,
)
