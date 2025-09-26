"""FastMCP server exposing mocked K8s, Slack, and Jira tools for the challenge."""

import copy
import json
import os

from fastmcp import FastMCP


DEFAULT_FIXTURES = {
    'pods': {
        'default': [
            'checkout-service',
            'idle-service',
            'recommendation-service',
            'auth-service',
        ],
    },
    'descriptions': {
        'checkout-service': {
            'cpu_request': '500m',
            'cpu_limit': '750m',
            'mem_request': '512Mi',
            'mem_limit': '1Gi',
        },
        'idle-service': {
            'cpu_request': '400m',
            'cpu_limit': '500m',
            'mem_request': '512Mi',
            'mem_limit': '1Gi',
        },
        'recommendation-service': {
            'cpu_request': '600m',
            'cpu_limit': '900m',
            'mem_request': '1Gi',
            'mem_limit': '2Gi',
        },
        'auth-service': {
            'cpu_request': '300m',
            'cpu_limit': '600m',
            'mem_request': '512Mi',
            'mem_limit': '1Gi',
        },
    },
    'metrics': {
        ('checkout-service', 'cpu', '24h'): {'avg': 65, 'p95': 80},
        ('checkout-service', 'memory', '24h'): {'avg': 95, 'p95': 98},
        ('checkout-service', 'oom_kills', '24h'): {'avg': 4, 'p95': 4},
        ('idle-service', 'cpu', '24h'): {'avg': 10, 'p95': 18},
        ('idle-service', 'memory', '24h'): {'avg': 12, 'p95': 19},
        ('idle-service', 'oom_kills', '24h'): {'avg': 0, 'p95': 0},
        ('recommendation-service', 'cpu', '24h'): {'avg': 18, 'p95': 92},
        ('recommendation-service', 'memory', '24h'): {'avg': 15, 'p95': 93},
        ('recommendation-service', 'oom_kills', '24h'): {'avg': 0, 'p95': 0},
        ('auth-service', 'cpu', '24h'): {'avg': 42, 'p95': 55},
        ('auth-service', 'memory', '24h'): {'avg': 47, 'p95': 58},
        ('auth-service', 'oom_kills', '24h'): {'avg': 0, 'p95': 0},
    },
}


def default_fixtures():
    fixtures = copy.deepcopy(DEFAULT_FIXTURES)
    fixtures['updates'] = []
    fixtures['slack_messages'] = []
    fixtures['jira_issues'] = []
    return fixtures


def _load_fixtures_from_file(path):
    with open(path) as handle:
        data = json.load(handle)
    fixtures = {
        'pods': data.get('pods', {'default': []}),
        'descriptions': data.get('descriptions', {}),
        'metrics': {},
        'updates': data.get('updates', []),
        'slack_messages': data.get('slack_messages', []),
        'jira_issues': data.get('jira_issues', []),
    }

    for item in data.get('metrics', []):
        fixtures['metrics'][(item['pod'], item['metric'], item['window'])] = item['values']

    return fixtures


def _serialize_metrics(metrics):
    serialized = []
    for (pod, metric, window), payload in metrics.items():
        serialized.append({
            'pod': pod,
            'metric': metric,
            'window': window,
            'values': payload,
        })
    return serialized


def _persist_state(fixtures, state_file):
    if not state_file:
        return
    state = {
        'pods': fixtures.get('pods', {}),
        'descriptions': fixtures.get('descriptions', {}),
        'metrics': _serialize_metrics(fixtures.get('metrics', {})),
        'updates': fixtures.get('updates', []),
        'slack_messages': fixtures.get('slack_messages', []),
        'jira_issues': fixtures.get('jira_issues', []),
    }
    with open(state_file, 'w') as handle:
        json.dump(state, handle, indent=2)


def create_server(fixtures=None):
    fixture_file = os.environ.get('K8S_BALANCER_FIXTURE_FILE')
    if fixtures is None and fixture_file:
        fixtures = _load_fixtures_from_file(fixture_file)
    fixtures = fixtures or default_fixtures()
    state_file = os.environ.get('K8S_BALANCER_STATE_FILE')
    _persist_state(fixtures, state_file)

    server = FastMCP('k8s-balancer')

    @server.tool('k8s_list_pods')
    def list_pods(namespace):
        pods = fixtures['pods'].get(namespace)
        if pods is None:
            return {'items': []}
        return {'items': pods}

    @server.tool('k8s_query_metrics')
    def metrics_query(pod, metric, window):
        return fixtures['metrics'].get((pod, metric, window))

    @server.tool('k8s_describe_pod')
    def describe(pod):
        return fixtures['descriptions'].get(pod)

    @server.tool('k8s_update_resources')
    def update_resources(pod, cpu_request=None, cpu_limit=None, mem_request=None, mem_limit=None):
        updates = fixtures.setdefault('updates', [])
        updates.append({
            'pod': pod,
            'cpu_request': cpu_request,
            'cpu_limit': cpu_limit,
            'mem_request': mem_request,
            'mem_limit': mem_limit,
        })
        _persist_state(fixtures, state_file)
        return {'status': 'updated'}

    @server.tool('slack_post_message')
    def post_message(channel, text, blocks=None):
        messages = fixtures.setdefault('slack_messages', [])
        messages.append({'channel': channel, 'text': text, 'blocks': blocks})
        _persist_state(fixtures, state_file)
        return {'ts': '0', 'url': 'https://slack.test/message/0'}

    @server.tool('jira_create_issue')
    def create_issue(project, title, body):
        issues = fixtures.setdefault('jira_issues', [])
        issues.append({'project': project, 'title': title, 'body': body, 'url': 'https://jira.test/browse/TEST-1', 'issue_id': 'TEST-1'})
        _persist_state(fixtures, state_file)
        return {'issue_id': 'TEST-1', 'url': 'https://jira.test/browse/TEST-1'}

    return server


if __name__ == '__main__':
    server = create_server()
    server.run()
