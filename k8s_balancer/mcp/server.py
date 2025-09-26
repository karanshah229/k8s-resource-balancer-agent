"""FastMCP server exposing mocked K8s, Slack, and Jira tools for the challenge."""

from fastmcp import FastMCP


def create_server(fixtures=None):
    server = FastMCP('k8s-balancer')

    @server.tool('mcp:k8s.list_pods')
    def list_pods(namespace):
        if fixtures and 'pods' in fixtures:
            return {'items': fixtures['pods'].get(namespace, [])}
        raise NotImplementedError('Provide pod fixtures for namespace %s' % namespace)

    @server.tool('mcp:k8s.metrics.query')
    def metrics_query(pod, metric, window):
        if fixtures and 'metrics' in fixtures:
            return fixtures['metrics'].get((pod, metric, window))
        raise NotImplementedError('Provide metrics fixture for %s' % pod)

    @server.tool('mcp:k8s.describe')
    def describe(pod):
        if fixtures and 'descriptions' in fixtures:
            return fixtures['descriptions'].get(pod)
        raise NotImplementedError('Provide description fixture for %s' % pod)

    @server.tool('mcp:k8s.update_resources')
    def update_resources(pod, cpu_request=None, cpu_limit=None, mem_request=None, mem_limit=None):
        if fixtures is not None:
            updates = fixtures.setdefault('updates', [])
            updates.append({
                'pod': pod,
                'cpu_request': cpu_request,
                'cpu_limit': cpu_limit,
                'mem_request': mem_request,
                'mem_limit': mem_limit,
            })
            return {'status': 'updated'}
        raise NotImplementedError('Implement update logic')

    @server.tool('mcp:slack.post_message')
    def post_message(channel, text, blocks=None):
        if fixtures is not None:
            messages = fixtures.setdefault('slack_messages', [])
            messages.append({'channel': channel, 'text': text, 'blocks': blocks})
            return {'ts': '0', 'url': 'https://slack.test/message/0'}
        raise NotImplementedError('Implement Slack posting logic')

    @server.tool('mcp:jira.create_issue')
    def create_issue(project, title, body):
        if fixtures is not None:
            issues = fixtures.setdefault('jira_issues', [])
            issues.append({'project': project, 'title': title, 'body': body})
            return {'issue_id': 'TEST-1', 'url': 'https://jira.test/browse/TEST-1'}
        raise NotImplementedError('Implement Jira issue creation')

    return server
