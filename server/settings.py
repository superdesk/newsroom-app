import os
import pathlib

ABS_PATH = pathlib.Path(__file__).resolve().parent
WEBPACK_MANIFEST_PATH = os.path.join(
    ABS_PATH.parent,
    'client',
    'dist',
    'manifest.json'
)

DEBUG = bool(os.environ.get('NEWSROOM_DEBUG'))
