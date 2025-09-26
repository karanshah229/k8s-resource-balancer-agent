#!/usr/bin/env python3

"""Command line launcher for the Kubernetes Resource Rebalancer Agent."""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from k8s_balancer.runner import run_once
from langchain_community.llms import FakeListLLM



class FakeMCPClient:
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


def install_demo_mcp_fixtures():
    fixtures = {
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

    from k8s_balancer.integrations import k8s_client, slack_client

    def factory(endpoint=None):
        return FakeMCPClient(fixtures)

    k8s_client.MCPClient = factory
    slack_client.MCPClient = factory

    return fixtures


def build_llm():
    """Create and return the LangChain LLM instance used by the agent."""
    fallback_responses = ['{}'] * 20
    return FakeListLLM(responses=fallback_responses)


def main():
    namespace = os.environ.get('TARGET_NAMESPACE', 'default')
    slack_channel = os.environ.get('SLACK_CHANNEL', '#platform-notifications')
    llm = build_llm()
    fixtures = install_demo_mcp_fixtures()
    run_once(llm, namespace, slack_channel)
    summary = fixtures.get('slack_messages', [{}])[-1]['text']
    print('Run complete. Slack summary message:')
    print(summary)


if __name__ == '__main__':
    main()
