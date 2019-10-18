import json
from urllib.parse import urlencode


class ConnectionData:
    """Documentation for ConnectionData

    """

    def __init__(self,
                 url,
                 hub,
                 extra_params,
                 is_safe,
                 client_protocol_version=1.5):
        self.url = url
        self.hub = hub
        self.extra_params = extra_params
        self.is_safe = is_safe
        self.client_protocol_version = client_protocol_version
        self.hub_connection_data = json.dumps([{'name': hub}])
        self.conection_token = ''

    @property
    def negotiator_url(self):
        if self.is_safe:
            return 'https://' + self.url + '/negotiate'
        else:
            return 'http://' + self.url + '/negotiate'

    @property
    def negotiator_params(self):
        params = {
            'connectionData': self.hub_connection_data,
            'clientProtocol': self.client_protocol_version,
        }
        params.update(self.extra_params)
        return params

    @property
    def websocket_url(self):
        if self.is_safe:
            return 'wss://' + self.url + '/connect'
        else:
            return 'ws://' + self.url + '/connect'

    @property
    def websocket_params(self):
        params = {
            'transport': 'webSockets',
            'connectionToken': self.connection_token,
            'connectionData': self.hub_connection_data,
            'clientProtocol': self.client_protocol_version,
        }
        params.update(self.extra_params)
        return params

    def set_negotiating_data(self, data):
        self.connection_token = data['ConnectionToken']

    @property
    def websocket_channel_request_path(self):
        return self.websocket_url + '?' + urlencode(self.websocket_params)

    @property
    def initialize_url(self):
        if self.is_safe:
            return 'https://' + self.url + '/start'
        else:
            return 'http://' + self.url + '/start'
