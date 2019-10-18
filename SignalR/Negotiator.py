class Negotiator:
    """Documentation for Negotiator

    """

    def __init__(self, connection, connection_data):
        self.connection = connection
        self.connection_data = connection_data

    def negotiate(self):
        url = self.connection_data.negotiator_url
        params = self.connection_data.negotiator_params
        self.response = self.connection.get(url, params=params)
        self.parse_response()
        return self

    def parse_response(self):
        try:
            self.data = self.response.json()
        except Exception:
            raise Exception(
                'No such hub. Negotiating status code is {}'.format(
                    self.response.status_code))
