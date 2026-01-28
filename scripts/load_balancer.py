"""
NOTE: This is an alternative round-robin implementation.
Currently NOT USED - we use nginx blue-green deployment instead.
See docker-compose.yml and nginx.conf for active load balancer.
"""

#!/usr/bin/env python3
"""
Simple round-robin TCP->HTTP forwarder for the recommender containers.
- Listens on port 8080 (host) and forwards requests to backend containers
  (e.g., http://localhost:8082 and http://localhost:8083) in round-robin.
- Forwards path and query string, returns backend response.

Usage (from project root):
  python scripts/load_balancer.py

Notes:
- Lightweight, single-threaded HTTP proxy using requests and Flask.
- For production replace with nginx / haproxy or a proper WSGI/gunicorn setup.
"""

from flask import Flask, request, Response
import requests
import itertools
import os

app = Flask(__name__)

# Backends: can be configured via env or defaults
BACKENDS = os.environ.get("RECSYS_BACKENDS", "http://recommender_v1:8082,http://recommender_v2:8082").split(",")
back_iter = itertools.cycle(BACKENDS)

# Timeout for backend requests
BACKEND_TIMEOUT = float(os.environ.get("RECSYS_BACKEND_TIMEOUT", "5.0"))

@app.route('/', defaults={'path': ''}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.route('/<path:path>', methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(path):
    backend = next(back_iter)
    url = backend.rstrip('/') + '/' + path

    try:
        resp = requests.request(
            method=request.method,
            url=url,
            headers={k: v for k, v in request.headers if k.lower() != 'host'},
            params=request.args,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=BACKEND_TIMEOUT,
        )

        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in excluded_headers] if getattr(resp, 'raw', None) else list(resp.headers.items())

        return Response(resp.content, resp.status_code, headers)
    except requests.RequestException as e:
        return Response(f"Backend request failed: {e}", status=502)

if __name__ == '__main__':
    host = os.environ.get('LOAD_BALANCER_HOST', '0.0.0.0')
    port = int(os.environ.get('LOAD_BALANCER_PORT', '8080'))
    # Recommend running under tmux / systemd in production
    print(f"Starting load balancer on {host}:{port} -> backends={BACKENDS}")
    app.run(host=host, port=port)
