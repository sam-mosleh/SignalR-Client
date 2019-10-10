import json


class Negotiator:
    """Documentation for Negotiator

    """

    def __init__(self,
                 url,
                 hub,
                 session,
                 extra_params,
                 is_safe,
                 client_protocol_version=1.5):
        self.url = self.get_url(url, is_safe)
        self.client_protocol_version = client_protocol_version
        self.connection_data = json.dumps([{'name': hub}])
        self.session = session
        self.extra_params = extra_params
        self.negotiate()
        try:
            self.data = self.response.json()
        except Exception:
            raise Exception(
                'No such hub. Negotiating status code is {}'.format(
                    self.response.status_code))

    def get_url(self, url, is_safe):
        if is_safe:
            return 'https://' + url + '/negotiate'
        else:
            return 'http://' + url + '/negotiate'

    def negotiate(self):
        params = {
            'connectionData': self.connection_data,
            'clientProtocol': self.client_protocol_version,
        }
        params.update(self.extra_params)
        self.response = self.session.get(self.url, params=params)
