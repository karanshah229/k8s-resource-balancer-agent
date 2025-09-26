"""Convenience entry points used by scripts or notebooks."""

from k8s_balancer.agent.orchestrator import ResourceRebalanceOrchestrator


def create_agent(llm, namespace, slack_channel):
    return ResourceRebalanceOrchestrator(llm, namespace, slack_channel)


def run_once(llm, namespace, slack_channel):
    agent = create_agent(llm, namespace, slack_channel)
    return agent.run()
