"""High level orchestrator that delegates to an MCP-driven LLM workflow."""

import copy

from k8s_balancer.agent.agent_runner import MCPToolAgentRunner


class ResourceRebalanceOrchestrator:
    """Coordinates the run by invoking an MCP-aware LLM agent."""

    def __init__(self, llm, namespace, slack_channel, fixtures=None, agent_runner_cls=None):
        self.llm = llm
        self.namespace = namespace
        self.slack_channel = slack_channel
        self.fixtures = copy.deepcopy(fixtures) if fixtures is not None else None
        self.agent_runner_cls = agent_runner_cls or MCPToolAgentRunner
        self.latest_outcome = None

    def run(self):
        runner = self.agent_runner_cls(self.llm, fixtures=copy.deepcopy(self.fixtures))
        outcome = runner.execute(self.namespace, self.slack_channel)
        self.latest_outcome = outcome
        return outcome.summary
