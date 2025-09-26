"""Convenience entry points used by scripts or notebooks."""

from k8s_balancer.agent.orchestrator import ResourceRebalanceOrchestrator


def create_agent(llm, namespace, slack_channel, fixtures=None, agent_runner_cls=None):
    return ResourceRebalanceOrchestrator(llm, namespace, slack_channel, fixtures=fixtures, agent_runner_cls=agent_runner_cls)


def run_once(llm, namespace, slack_channel, fixtures=None, agent_runner_cls=None):
    agent = create_agent(llm, namespace, slack_channel, fixtures=fixtures, agent_runner_cls=agent_runner_cls)
    return agent.run()
