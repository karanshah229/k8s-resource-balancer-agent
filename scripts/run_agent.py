#!/usr/bin/env python3

"""Command line launcher for the Kubernetes Resource Rebalancer Agent."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from k8s_balancer.mcp.server import default_fixtures
from k8s_balancer.runner import create_agent
from langchain_openai import ChatOpenAI


def install_demo_mcp_fixtures():
    return default_fixtures()


def build_llm():
    """Create and return the LangChain LLM instance used by the agent."""
    load_dotenv()
    api_key = os.getenv('OPENAI_API_KEY')
    base_url = os.getenv('OPENAI_API_BASE')

    if not api_key:
        raise ValueError('OPENAI_API_KEY environment variable is not set')

    kwargs = {
        'api_key': api_key,
        'model': 'gpt-4o-mini',
        'temperature': 0,
    }
    if base_url:
        kwargs['base_url'] = base_url

    return ChatOpenAI(**kwargs)


def main():
    namespace = os.environ.get('TARGET_NAMESPACE', 'default')
    slack_channel = os.environ.get('SLACK_CHANNEL', '#platform-notifications')
    llm = build_llm()
    fixtures = install_demo_mcp_fixtures()
    agent = create_agent(llm, namespace, slack_channel, fixtures=fixtures)
    summary = agent.run()
    print('Run complete. Slack summary message:')
    if agent.latest_outcome and agent.latest_outcome.slack_message:
        print(agent.latest_outcome.slack_message)
    else:
        print(summary)


if __name__ == '__main__':
    main()
