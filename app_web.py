import os

from newsroom.web import get_app

import settings


instance_settings = {}

for key in dir(settings):
    if key.isupper():
        instance_settings.setdefault(key, getattr(settings, key))

app = get_app(config=instance_settings)

if __name__ == '__main__':
    host = '0.0.0.0'
    port = int(os.environ.get('PORT', '5050'))
    app.run(debug=True, host=host, port=port, threaded=True)
