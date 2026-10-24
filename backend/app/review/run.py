"""Run three synthetic API journeys against the local stack; no live provider calls."""
import argparse
import getpass
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings


class ReviewFailure(Exception):
    pass


def local_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != 'http' or parts.hostname not in ('localhost', '127.0.0.1') or parts.username or parts.password or parts.path not in ('', '/') or parts.query or parts.fragment:
        raise ValueError('Use a local http://localhost:PORT or http://127.0.0.1:PORT URL')
    return value.rstrip('/')


def request(client: httpx.Client, method: str, path: str, token: str | None = None,
            expected: int = 200, **kwargs) -> dict:
    headers = dict(kwargs.pop('headers', {}))
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        response = client.request(method, '/api/v1' + path, headers=headers, **kwargs)
    except httpx.HTTPError:
        raise ReviewFailure(f'{method} {path}: local API unavailable') from None
    if response.status_code != expected:
        raise ReviewFailure(f'{method} {path}: expected HTTP {expected}, got {response.status_code}; request_id={response.headers.get("X-Request-ID", "unknown")}')
    return response.json()


def login(client: httpx.Client, role: str, password: str) -> str:
    result = request(client, 'POST', '/auth/token', expected=200,
                     data={'username': f'{role}@local.example', 'password': password})
    return result['access_token']


def inspect_report(report: dict) -> dict:
    if report['status'] != 'completed' or report['provider'] != 'mock':
        raise ReviewFailure('Investigation did not finish with the mock provider')
    evidence = report['evidence']
    ids = {item['id'] for item in evidence}
    structured = report['report']
    cited = [*structured['summary_evidence_ids']]
    for field in ('observations', 'hypotheses', 'recommendations'):
        cited.extend(ref for item in structured[field] for ref in item['evidence_ids'])
    if not cited or any(ref not in ids for ref in cited):
        raise ReviewFailure('Investigation has missing or unsupported citation IDs')
    if not any(item['kind'] == 'source' for item in evidence):
        raise ReviewFailure('No accessible runbook source was retrieved; verify embedding mode and reindex demo documents')
    if not structured['hypotheses'] or any(not h['uncertainty'] for h in structured['hypotheses']):
        raise ReviewFailure('Investigation lacks explicit hypothesis uncertainty')
    return {'id': report['id'], 'status': report['status'], 'evidence_count': len(ids),
            'citation_count': len(cited), 'source_count': sum(item['kind'] == 'source' for item in evidence)}


def poll(client: httpx.Client, path: str, token: str, target: str, timeout: int = 35) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = request(client, 'GET', path, token)
        if row['state'] == target:
            return row
        if row['state'] in ('failed', 'cancelled', 'completed'):
            raise ReviewFailure(f'Workflow stopped in state {row["state"]}, expected {target}')
        time.sleep(1)
    raise ReviewFailure(f'Workflow did not reach {target} within {timeout}s; check worker logs')


def run(base_url: str, password: str) -> dict:
    settings = get_settings()
    if settings.investigation_provider != 'mock':
        raise ReviewFailure('Set INVESTIGATION_PROVIDER=mock in backend/.env and restart API before review')
    result = {'stage': 8, 'at': datetime.now(timezone.utc).isoformat(),
              'synthetic': True, 'provider': 'mock', 'journeys': {}}
    with httpx.Client(base_url=local_url(base_url), timeout=25, trust_env=False) as client:
        admin = login(client, 'admin', password)
        responder = login(client, 'responder', password)
        approver = login(client, 'approver', password)
        viewer = login(client, 'viewer', password)
        fixture = request(client, 'POST', '/demo/replay', admin)
        incident_ids = fixture['incident_ids']
        if not incident_ids:
            raise ReviewFailure('Replay returned no incident; inspect the synthetic alert rule')
        incident_id = incident_ids[0]
        request(client, 'POST', '/knowledge/demo', admin, expected=201)
        details = request(client, 'GET', f'/incidents/{incident_id}', responder)
        if not details['alerts'] or not details['timeline']:
            raise ReviewFailure('Synthetic incident lacks alerts or timeline')
        report = request(client, 'POST', f'/investigations/incidents/{incident_id}',
                         responder, expected=201)
        checked = inspect_report(report)
        for evidence in report['evidence']:
            if evidence['kind'] == 'source':
                request(client, 'GET', evidence['source_url'].removeprefix('/api/v1'), responder)
        result['journeys']['investigation'] = {'incident_id': incident_id, **checked}

        workflow = request(client, 'POST', f'/workflows/incidents/{incident_id}', responder,
                           expected=201, headers={'Idempotency-Key': str(uuid.uuid4())},
                           json={'action': 'simulate_pool_refresh'})
        workflow_id = workflow['id']
        path = f'/workflows/{workflow_id}'
        pending = poll(client, path, responder, 'awaiting_approval')
        approval = pending['approval']
        request(client, 'GET', path, viewer, expected=404)
        request(client, 'POST', path + '/decision', approver,
                json={'approval_id': approval['id'], 'plan_hash': approval['plan_hash'],
                      'decision': 'approved'})
        completed = poll(client, path, responder, 'completed')
        if not completed['result']['simulated'] or len([e for e in completed['events'] if e['type'] == 'completed']) != 1:
            raise ReviewFailure('Approved workflow has no single simulated completion')
        own = request(client, 'POST', f'/workflows/incidents/{incident_id}', approver,
                      expected=201, headers={'Idempotency-Key': str(uuid.uuid4())},
                      json={'action': 'simulate_pool_refresh'})
        own_path = f'/workflows/{own["id"]}'
        own_pending = poll(client, own_path, approver, 'awaiting_approval')
        own_approval = own_pending['approval']
        request(client, 'POST', own_path + '/decision', approver, expected=403,
                json={'approval_id': own_approval['id'], 'plan_hash': own_approval['plan_hash'],
                      'decision': 'approved'})
        request(client, 'POST', own_path + '/cancel', approver)
        result['journeys']['workflow'] = {'id': workflow_id, 'state': 'completed',
            'self_approval_denied': True, 'viewer_access_denied': True,
            'simulated': True, 'effect_id': completed['result']['effect_id']}

        evaluation = request(client, 'GET', '/evaluation/offline', admin)
        if evaluation['metrics']['passed'] != evaluation['metrics']['total']:
            raise ReviewFailure('Offline evaluation has failing checks')
        result['journeys']['evaluation'] = {'dataset_sha256': evaluation['dataset']['sha256'],
            'passed': evaluation['metrics']['passed'], 'total': evaluation['metrics']['total'],
            'retrieval': evaluation['metrics']['retrieval']['status']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--output', default='../review-stage8.json')
    args = parser.parse_args()
    try:
        base_url = local_url(args.base_url)
        password = getpass.getpass('Local demo password: ')
        if not password:
            raise ReviewFailure('Password required')
        target = Path(args.output)
        if target.exists():
            raise ReviewFailure(f'Review report already exists: {target}')
        result = run(base_url, password)
        target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(f'Three synthetic journeys passed; report: {target}')
    except (ReviewFailure, ValueError) as exc:
        parser.exit(1, f'Review stopped: {exc}\n')


if __name__ == '__main__':
    main()
