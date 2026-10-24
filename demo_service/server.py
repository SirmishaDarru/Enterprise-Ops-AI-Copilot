"""A real local HTTP target with an intentionally controllable failure mode."""
import json
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.instance_id = str(uuid.uuid4())
        self.failure = False
        self.sequence = 0
        self.events = deque(maxlen=1000)
        self.ok = 0
        self.errors = 0

    def checkout(self):
        started = time.monotonic()
        with self.lock:
            failure = self.failure
        time.sleep(0.04 if failure else 0.01)
        status = 503 if failure else 200
        with self.lock:
            self.sequence += 1
            self.errors += int(failure)
            self.ok += int(not failure)
            event = {'seq': self.sequence, 'at': datetime.now(timezone.utc).isoformat(),
                     'status': status, 'latency_ms': max(1, round((time.monotonic() - started) * 1000)),
                     'message': 'Database connection pool exhausted' if failure else 'Checkout completed'}
            self.events.append(event)
        return status

    def snapshot(self, after: int):
        with self.lock:
            return {'instance_id': self.instance_id, 'latest_seq': self.sequence,
                    'oldest_seq': self.events[0]['seq'] if self.events else self.sequence + 1,
                    'events': [item for item in self.events if item['seq'] > after][:200]}

    def set_failure(self, enabled: bool):
        with self.lock:
            self.failure = enabled
            return {'failure_enabled': self.failure}

    def metrics(self):
        with self.lock:
            ok, errors, failure = self.ok, self.errors, self.failure
        return ('# HELP checkout_requests_total HTTP checkout requests by status\n'
                '# TYPE checkout_requests_total counter\n'
                f'checkout_requests_total{{status="200"}} {ok}\n'
                f'checkout_requests_total{{status="503"}} {errors}\n'
                '# TYPE checkout_failure_mode gauge\n'
                f'checkout_failure_mode {int(failure)}\n').encode()


state = State()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass  # Request paths and payloads stay out of container logs.

    def respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/health':
            return self.respond(200, {'status': 'ok'})
        if parsed.path == '/checkout':
            status = state.checkout()
            return self.respond(status, {'status': 'unavailable' if status == 503 else 'accepted'})
        if parsed.path == '/internal/events':
            try:
                after = int(parse_qs(parsed.query).get('after', ['0'])[0])
                if after < 0:
                    raise ValueError
            except ValueError:
                return self.respond(400, {'error': 'invalid cursor'})
            return self.respond(200, state.snapshot(after))
        if parsed.path == '/internal/state':
            with state.lock:
                enabled = state.failure
            return self.respond(200, {'failure_enabled': enabled})
        if parsed.path == '/metrics':
            body = state.metrics()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        self.respond(404, {'error': 'not found'})

    def do_POST(self):
        if urlsplit(self.path).path != '/internal/failure':
            return self.respond(404, {'error': 'not found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > 100:
                raise ValueError
            body = json.loads(self.rfile.read(length))
            if set(body) != {'enabled'} or type(body['enabled']) is not bool:
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError):
            return self.respond(400, {'error': 'invalid control request'})
        self.respond(200, state.set_failure(body['enabled']))


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8081), Handler).serve_forever()
