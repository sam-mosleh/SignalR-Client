import requests


class Connection:
    """Documentation for Connection

    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent':
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
        })

    def get(self, url, params={}):
        return self.session.get(url, params=params)

    @property
    def headers(self):
        return self.session.headers
