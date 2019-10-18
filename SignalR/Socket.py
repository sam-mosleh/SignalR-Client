import json

import websockets


class Socket:
    """Documentation for Socket

    """

    def __init__(self, connection, connection_data, loop):
        self.connection = connection
        self.connection_data = connection_data
        self.loop = loop

    async def send(self, data):
        await self.websocket.send(json.dumps(data))

    async def close(self):
        await self.websocket.close()

    @property
    def still_open(self):
        return self.websocket.open()

    async def __aenter__(self):
        self._conn = websockets.connect(
            self.connection_data.websocket_channel_request_path,
            extra_headers=self.connection.headers,
            loop=self.loop)
        self.websocket = await self._conn.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._conn.__aexit__(*args, **kwargs)
