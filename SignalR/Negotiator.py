import json


class Negotiator:
    """Documentation for Negotiator

    """
    def __init__(self, url, hub, session, extra_params, is_safe):
        if is_safe:
            self.url = 'https://' + url + '/negotiate'
        else:
            self.url = 'http://' + url + '/negotiate'
        self.client_protocol_version = 1.5
        self.connection_data = json.dumps([{'name': hub}])
        self.session = session
        self.extra_params = extra_params
        self.negotiate()
        try:
            self.data = self.response.json()
        except Exception:
            self.data = {'Errors': True}

    def negotiate(self):
        params = {
            'connectionData': self.connection_data,
            'clientProtocol': self.client_protocol_version,
        }
        params.update(self.extra_params)
        self.response = self.session.get(self.url, params=params)
