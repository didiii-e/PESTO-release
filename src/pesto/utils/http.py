"""One keep-alive HTTP session per service, sized for the parallelism PESTO uses.

`requests.get` and `requests.post` open a new connection, and so a new TLS
handshake, for every call. A `Session` keeps connections open and reuses them.
Its default pool holds ten connections per host, though, and a batch of pairs
runs more calls at once than that, so the extra ones are opened, used once and
thrown away. The pool is sized to cover the workers instead.

Nothing about a request changes: same URL, parameters, headers and timeout.
"""
import requests
from requests.adapters import HTTPAdapter


def pooled_session(size=32):
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=size, pool_maxsize=size)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
