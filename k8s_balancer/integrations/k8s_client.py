from mcp_use import MCPClient


class KubernetesMCPClient:
    """Thin wrapper over MCP tools exposed by the FastMCP server."""

    def __init__(self, endpoint=None):
        # Endpoint can be a unix socket or http url depending on FastMCP setup
        self.client = MCPClient(endpoint)

    def list_pods(self, namespace):
        """Return pod names for the namespace. Provide mock data during tests."""
        response = self.client.call('mcp:k8s.list_pods', {'namespace': namespace})
        items = response.get('items') if isinstance(response, dict) else response
        if items is None:
            return []
        return items

    def describe_pod(self, pod_name):
        """Fetch resource configuration for the given pod."""
        return self.client.call('mcp:k8s.describe', {'pod': pod_name})

    def query_metrics(self, pod_name, metric, window):
        """Fetch aggregated metrics for the pod."""
        return self.client.call('mcp:k8s.metrics.query', {
            'pod': pod_name,
            'metric': metric,
            'window': window,
        })

    def update_resources(self, pod_name, payload):
        """Apply resource updates to the pod."""
        request_body = {'pod': pod_name}
        request_body.update(payload)
        return self.client.call('mcp:k8s.update_resources', request_body)

    def create_escalation(self, title, body):
        """Raise a Jira ticket for inconsistent pods."""
        return self.client.call('mcp:jira.create_issue', {
            'project': 'PLAT',
            'title': title,
            'body': body,
        })
