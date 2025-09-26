import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from langchain.llms.base import LLM


from pydantic import PrivateAttr


class DummyLLM(LLM):
    """Simple deterministic LLM used to make tests reproducible."""

    _responses = PrivateAttr(default=None)

    def __init__(self, responses):
        super().__init__()
        self._responses = responses

    @property
    def _llm_type(self):
        return 'dummy-llm'

    def _call(self, prompt, stop=None):
        responses = self._responses or {}
        for key, value in responses.items():
            if key != '__default__' and key in prompt:
                return value
        if '__default__' in responses:
            return responses['__default__']
        raise RuntimeError('No dummy response configured for prompt: %s' % prompt)

    @property
    def _identifying_params(self):
        return {}


class FakeMCPClient:
    """Records MCP tool interactions and returns fixture data."""

    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.calls = fixtures.setdefault('mcp_calls', [])

    def call(self, tool, payload):
        self.calls.append((tool, payload))

        if tool == 'mcp:k8s.list_pods':
            namespace = payload['namespace']
            pods = self.fixtures['pods'].get(namespace)
            if pods is None:
                raise KeyError('Unknown namespace %s' % namespace)
            return {'items': pods}

        if tool == 'mcp:k8s.describe':
            pod = payload['pod']
            description = self.fixtures['descriptions'].get(pod)
            if description is None:
                raise KeyError('Missing description for %s' % pod)
            return description

        if tool == 'mcp:k8s.metrics.query':
            key = (payload['pod'], payload['metric'], payload['window'])
            if key not in self.fixtures['metrics']:
                raise KeyError('Missing metrics for %s' % (key,))
            return self.fixtures['metrics'][key]

        if tool == 'mcp:k8s.update_resources':
            updates = self.fixtures.setdefault('updates', [])
            entry = {
                'pod': payload['pod'],
                'cpu_request': payload.get('cpu_request'),
                'cpu_limit': payload.get('cpu_limit'),
                'mem_request': payload.get('mem_request'),
                'mem_limit': payload.get('mem_limit'),
            }
            updates.append(entry)
            return {'status': 'updated'}

        if tool == 'mcp:slack.post_message':
            messages = self.fixtures.setdefault('slack_messages', [])
            message = {
                'channel': payload['channel'],
                'text': payload['text'],
                'blocks': payload.get('blocks'),
            }
            messages.append(message)
            return {'ts': '12345.0', 'url': 'https://slack.test/message/12345'}

        if tool == 'mcp:jira.create_issue':
            issues = self.fixtures.setdefault('jira_issues', [])
            body = payload['body']
            if isinstance(body, dict):
                body = json.dumps(body)
            issue = {
                'project': payload['project'],
                'title': payload['title'],
                'body': body,
                'url': 'https://jira.test/browse/TEST-1',
                'issue_id': 'TEST-1',
            }
            issues.append(issue)
            return {'issue_id': issue['issue_id'], 'url': issue['url']}

        raise RuntimeError('Unexpected MCP tool %s' % tool)


@pytest.fixture
def scenario_fixtures():
    return {
        'pods': {
            'default': [
                'checkout-service',
                'idle-service',
                'recommendation-service',
                'auth-service',
            ]
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
            ('recommendation-service', 'cpu', '24h'): {'avg': 18, 'p95': 92},
            ('recommendation-service', 'memory', '24h'): {'avg': 15, 'p95': 93},
            ('auth-service', 'cpu', '24h'): {'avg': 42, 'p95': 55},
            ('auth-service', 'memory', '24h'): {'avg': 47, 'p95': 58},
        },
    }


@pytest.fixture
def dummy_llm():
    responses = {
        'checkout-service': json.dumps({
            'classification': 'overloaded',
            'recommended_action': 'increase_memory_limit',
            'reason': 'Memory pressure and OOM events observed',
        }),
        'idle-service': json.dumps({
            'classification': 'idle',
            'recommended_action': 'decrease_requests',
            'reason': 'Sustained low CPU and memory usage',
        }),
        'recommendation-service': json.dumps({
            'classification': 'inconsistent',
            'recommended_action': 'escalate_inconsistent',
            'reason': 'High percentiles despite low averages',
        }),
        'auth-service': json.dumps({
            'classification': 'healthy',
            'recommended_action': 'skip',
            'reason': 'Balanced utilisation',
        }),
        '__default__': json.dumps({'notice': 'prompt not recognised'}),
    }
    return DummyLLM(responses)


@pytest.fixture(autouse=True)
def patch_mcp_client(monkeypatch, scenario_fixtures):
    def factory(endpoint=None):
        return FakeMCPClient(scenario_fixtures)

    monkeypatch.setattr('k8s_balancer.integrations.k8s_client.MCPClient', factory)
    monkeypatch.setattr('k8s_balancer.integrations.slack_client.MCPClient', factory)
    return scenario_fixtures
