import os

from newsroom.news_api.app import get_app

import settings_newsapi


instance_settings = {}

for key in dir(settings_newsapi):
    if key.isupper():
        instance_settings.setdefault(key, getattr(settings_newsapi, key))

app = get_app(config=instance_settings)

if __name__ == '__main__':
    host = '0.0.0.0'
    port = int(os.environ.get('APIPORT', '5400'))
    app.run(host=host, port=port, debug=True, use_reloader=True)
