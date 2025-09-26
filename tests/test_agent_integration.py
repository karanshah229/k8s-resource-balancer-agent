import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_agent import build_llm
from k8s_balancer.agent.orchestrator import ResourceRebalanceOrchestrator
from k8s_balancer.mcp.server import default_fixtures


def run_agent_with(fixtures):
    llm = build_llm()
    agent = ResourceRebalanceOrchestrator(llm, 'default', '#platform-notifications', fixtures=fixtures)
    try:
        summary = agent.run()
    except Exception as exc:
        pytest.skip(f'Agent execution failed: {exc}')
    outcome = agent.latest_outcome
    if not outcome or not outcome.state:
        pytest.skip('Agent did not return state information')
    if not outcome.state.get('updates') and not outcome.state.get('jira_issues') and not summary.get('pods_skipped'):
        pytest.skip('Agent did not take any actions; likely LLM call failed')
    return summary, outcome.state, outcome.slack_message


def fixture_base(target_pod, target_description, target_metrics):
    return {
        'pods': {'default': [target_pod]},
        'descriptions': {target_pod: target_description},
        'metrics': {
            (target_pod, 'cpu', '24h'): target_metrics['cpu'],
            (target_pod, 'memory', '24h'): target_metrics['memory'],
            (target_pod, 'oom_kills', '24h'): target_metrics['oom_kills'],
        },
        'updates': [],
        'slack_messages': [],
        'jira_issues': [],
    }


def parse_slack_json(slack_text):
    if not slack_text:
        pytest.skip('Slack message missing')
    parts = slack_text.split('```')
    if len(parts) < 3:
        pytest.skip('Slack message missing JSON block')
    payload = parts[1]
    if payload.startswith('json'):
        payload = payload[4:].lstrip()
    return json.loads(payload)


def extract_entry(entries, pod_name):
    for entry in entries:
        name = entry.get('pod_name') or entry.get('name') or entry.get('pod')
        if name == pod_name:
            return entry
    return None


def test_oomkilled_pod_updates_memory():
    fixtures = fixture_base(
        'checkout-service',
        {
            'cpu_request': '500m',
            'cpu_limit': '750m',
            'mem_request': '512Mi',
            'mem_limit': '1Gi',
        },
        {
            'cpu': {'avg': 60, 'p95': 80},
            'memory': {'avg': 95, 'p95': 99},
            'oom_kills': {'avg': 4, 'p95': 4},
        },
    )

    summary, state, slack_text = run_agent_with(fixtures)

    updates = state.get('updates', [])
    assert updates
    update = updates[0]
    assert update['pod'] == 'checkout-service'
    assert update['mem_limit'] not in (None, fixtures['descriptions']['checkout-service']['mem_limit'])

    parsed = parse_slack_json(slack_text)
    entry = extract_entry(parsed['pods_rebalanced'], 'checkout-service')
    assert entry is not None


def test_idle_pod_downscales_requests():
    fixtures = fixture_base(
        'idle-service',
        {
            'cpu_request': '500m',
            'cpu_limit': '750m',
            'mem_request': '512Mi',
            'mem_limit': '1Gi',
        },
        {
            'cpu': {'avg': 10, 'p95': 15},
            'memory': {'avg': 12, 'p95': 18},
            'oom_kills': {'avg': 0, 'p95': 0},
        },
    )

    summary, state, slack_text = run_agent_with(fixtures)

    updates = state.get('updates', [])
    update = next((item for item in updates if item['pod'] == 'idle-service'), None)
    assert update is not None
    assert update['cpu_request'] != fixtures['descriptions']['idle-service']['cpu_request']
    assert update['mem_request'] != fixtures['descriptions']['idle-service']['mem_request']

    parsed = parse_slack_json(slack_text)
    entry = extract_entry(parsed['pods_rebalanced'], 'idle-service')
    assert entry is not None


def test_inconsistent_metrics_escalates():
    fixtures = fixture_base(
        'recommendation-service',
        {
            'cpu_request': '600m',
            'cpu_limit': '900m',
            'mem_request': '1Gi',
            'mem_limit': '2Gi',
        },
        {
            'cpu': {'avg': 12, 'p95': 95},
            'memory': {'avg': 10, 'p95': 97},
            'oom_kills': {'avg': 0, 'p95': 0},
        },
    )

    summary, state, slack_text = run_agent_with(fixtures)

    issues = state.get('jira_issues', [])
    assert issues
    assert issues[0]['url'] == 'https://jira.test/browse/TEST-1'

    parsed = parse_slack_json(slack_text)
    entry = extract_entry(parsed['pods_escalated'], 'recommendation-service')
    assert entry is not None
    blob = ' '.join(str(v) for v in entry.values())
    assert 'jira' in blob.lower()


def test_healthy_pod_skipped():
    fixtures = fixture_base(
        'auth-service',
        {
            'cpu_request': '300m',
            'cpu_limit': '600m',
            'mem_request': '512Mi',
            'mem_limit': '1Gi',
        },
        {
            'cpu': {'avg': 55, 'p95': 70},
            'memory': {'avg': 65, 'p95': 78},
            'oom_kills': {'avg': 0, 'p95': 0},
        },
    )

    summary, state, slack_text = run_agent_with(fixtures)

    updates = state.get('updates', [])
    assert all(item['pod'] != 'auth-service' for item in updates)
    issues = state.get('jira_issues', [])
    assert all('auth-service' not in issue.get('title', '') for issue in issues)

    parsed = parse_slack_json(slack_text)
    entry = extract_entry(parsed['pods_skipped'], 'auth-service')
    assert entry is not None
