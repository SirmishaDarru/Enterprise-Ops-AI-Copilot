"""No database or Docker needed to prove real HTTP outcomes and event emission."""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from demo_service import server


class CheckoutHTTPTest(unittest.TestCase):
    def setUp(self):
        self.previous = server.state
        server.state = server.State()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.state = self.previous

    def test_health_failure_and_recovery_emit_observed_events(self):
        with urlopen(self.base + '/health') as response:
            self.assertEqual(response.status, 200)
        with urlopen(self.base + '/checkout') as response:
            self.assertEqual(response.status, 200)
        control = Request(self.base + '/internal/failure',
            data=b'{"enabled":true}', headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(control) as response:
            self.assertTrue(json.load(response)['failure_enabled'])
        with self.assertRaises(HTTPError) as failure:
            urlopen(self.base + '/checkout')
        self.assertEqual(failure.exception.code, 503)
        with urlopen(self.base + '/internal/events?after=0') as response:
            events = json.load(response)['events']
        self.assertEqual([item['status'] for item in events], [200, 503])
        self.assertEqual([item['seq'] for item in events], [1, 2])
        with urlopen(self.base + '/metrics') as response:
            metrics = response.read().decode()
        self.assertIn('checkout_requests_total{status="503"} 1', metrics)
        self.assertIn('checkout_failure_mode 1', metrics)
        control = Request(self.base + '/internal/failure', data=b'{"enabled":false}', method='POST')
        with urlopen(control):
            pass
        with urlopen(self.base + '/checkout') as response:
            self.assertEqual(response.status, 200)


if __name__ == '__main__':
    unittest.main()
