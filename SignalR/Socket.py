import json
from urllib.parse import urlencode

import websockets


class Socket:
    """Documentation for Socket

    """
    def __init__(self, url, hub, session, negotiator_data, loop, extra_params,
                 is_safe):
        if is_safe:
            self.url = 'wss://' + url + '/connect'
        else:
            self.url = 'ws://' + url + '/connect'
        self.session = session
        self.data = negotiator_data
        self.connection_data = json.dumps([{'name': hub}])
        self.client_protocol_version = 1.5
        self.loop = loop
        self.extra_params = extra_params

    async def send(self, data):
        await self.websocket.send(json.dumps(data))

    async def close(self):
        await self.websocket.close()

    @property
    def still_open(self):
        return self.websocket.open()

    async def __aenter__(self):
        params = {
            'transport': 'webSockets',
            'connectionToken': self.data['ConnectionToken'],
            'connectionData': self.connection_data,
            'clientProtocol': self.client_protocol_version,
        }
        params.update(self.extra_params)
        self.url += '?' + urlencode(params)
        self._conn = websockets.connect(self.url,
                                        extra_headers=self.session.headers,
                                        loop=self.loop)
        self.websocket = await self._conn.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._conn.__aexit__(*args, **kwargs)
