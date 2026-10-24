"""Check the observed HTTP-to-incident path; always clear the controlled failure."""
import argparse
import getpass
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.review.run import ReviewFailure, inspect_report, local_url, login, request


def run(base_url: str, password: str) -> dict:
    if get_settings().investigation_provider != 'mock':
        raise ReviewFailure('Set INVESTIGATION_PROVIDER=mock and restart API before this check')
    with httpx.Client(base_url=local_url(base_url), timeout=25, trust_env=False) as client:
        admin = login(client, 'admin', password)
        responder = login(client, 'responder', password)
        status = request(client, 'GET', '/live-demo/status', admin)
        sid = status['service_id']
        request(client, 'POST', '/live-demo/failure', admin, json={'enabled': False})
        request(client, 'POST', '/knowledge/live-demo/runbook', admin, expected=201)
        baseline = request(client, 'GET', '/dashboard', admin)
        prior = next((item['latest']['id'] for item in baseline['services']
                      if item['id'] == sid and item['latest']), None)
        request(client, 'POST', '/live-demo/failure', admin, json={'enabled': True})
        try:
            deadline = time.monotonic() + 50
            sample = None
            while time.monotonic() < deadline:
                dashboard = request(client, 'GET', '/dashboard', admin)
                service = next((item for item in dashboard['services'] if item['id'] == sid), None)
                candidate = service['latest'] if service else None
                if (candidate and candidate['id'] != prior and candidate['source'] == 'live_demo'
                        and candidate['error_count'] > 0):
                    sample = candidate
                    break
                time.sleep(2)
            if sample is None:
                raise ReviewFailure('No failed observed HTTP batch within 50s; check checkout-traffic and checkout-collector logs')
            incidents = request(client, 'GET', f'/incidents?service_id={sid}', responder)['items']
            match = None
            for row in incidents:
                detail = request(client, 'GET', f'/incidents/{row["id"]}', responder)
                if any(alert['sample_id'] == sample['id'] for alert in detail['alerts']):
                    match = row
                    break
            if match is None:
                raise ReviewFailure('Failed HTTP batch produced no incident alert')
            report = request(client, 'POST', f'/investigations/incidents/{match["id"]}',
                             responder, expected=201)
            checked = inspect_report(report)
            result = {'stage': 10, 'at': datetime.now(timezone.utc).isoformat(),
                'origin': 'observed_local_http', 'service_id': sid,
                'sample_id': sample['id'], 'request_count': sample['request_count'],
                'error_count': sample['error_count'], 'incident_id': match['id'],
                'investigation': checked}
        finally:
            request(client, 'POST', '/live-demo/failure', admin, json={'enabled': False})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--output', default='../review-live-stage10.json')
    args = parser.parse_args()
    try:
        base = local_url(args.base_url)
        target = Path(args.output)
        if target.exists():
            raise ReviewFailure(f'Review report already exists: {target}')
        password = getpass.getpass('Local demo password: ')
        if not password:
            raise ReviewFailure('Password required')
        result = run(base, password)
        target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(f'Observed HTTP journey passed; failure cleared; report: {target}')
    except (ReviewFailure, ValueError) as exc:
        parser.exit(1, f'Review stopped: {exc}\n')


if __name__ == '__main__':
    main()
