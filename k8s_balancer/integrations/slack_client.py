from mcp_use import MCPClient


class SlackMCPClient:
    """Handles Slack notifications through the MCP bridge."""

    def __init__(self, channel, endpoint=None):
        self.channel = channel
        self.client = MCPClient(endpoint)

    def post_summary(self, text, blocks=None):
        body = {'channel': self.channel, 'text': text}
        if blocks is not None:
            body['blocks'] = blocks
        return self.client.call('mcp:slack.post_message', body)
