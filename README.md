# Kubernetes Resource Rebalancer Agent — Challenge Brief

You are a developer in a product-based company operating microservices on Kubernetes. You want to develop a AI Agent that rebalances kuberenetes pods based on certain conditions to make your work easy.

## Problem Statement

Some pods are overloaded (frequent OOMKills) while others stay underutilised. Manually tweaking requests/limits is slow, inconsistent, and often introduces new incidents. You need an autonomous agent that:

-   Detects problematic pods.
-   Decides whether to rebalance automatically or raise an escalation.
-   Acts on the cluster through Kubernetes MCP tools.
-   Notifies the team in Slack with a structured summary of everything that happened.

## Deterministic Goal

A single run is considered successful when:

1. Every pod in the target namespace is scanned.
2. Each problematic pod is either rebalanced (via resource updates) or escalated (via Jira).
3. A Slack message is posted with a JSON summary covering all actions taken, escalations created, and healthy pods that were skipped.

## MCP Tools

You must rely on the mocked MCP interface provided by the FastMCP server. Relevant tools:

-   `mcp:k8s.metrics.query(pod, metric, window)` → `{"avg": number, "p95": number}`
-   `mcp:k8s.describe(pod)` → `{"cpu_request": string, "cpu_limit": string, "mem_request": string, "mem_limit": string}`
-   `mcp:k8s.update_resources(...)` → `{"status": "updated" | "failed"}`
-   `mcp:slack.post_message(channel, text, blocks?)` → `{"ts": string, "url": string}`
-   `mcp:jira.create_issue(project, title, body)` → `{"issue_id": string, "url": string}`

## Decision Rules

Implement the deterministic playbook exactly as follows:

-   `OOMKilled ≥ 3` in the last 24 h **or** memory average > 90 % of the limit → increase the memory **limit** by +25 % using `mcp:k8s.update_resources`.
-   CPU and memory averages < 20 % over 24 h → decrease both requests by –20 % using `mcp:k8s.update_resources`.
-   Inconsistent metrics (averages low but p95 high) → escalate via `mcp:jira.create_issue` and reference the escalation in the Slack summary.
-   Otherwise mark the pod as healthy and do nothing.

## Expected Slack Notification

The run finishes by calling `mcp:slack.post_message` with:

1. Header text `✅ Resource Rebalance Completed`.
2. A code block containing JSON in this shape:

```
{
  "namespace": "default",
  "pods_scanned": 5,
  "pods_rebalanced": [
    {"name": "checkout-service", "cpu_limit": "600m", "mem_limit": "1.2Gi"}
  ],
  "pods_escalated": [
    {"name": "recommendation-service", "reason": "inconsistent metrics"}
  ],
  "pods_skipped": [
    {"name": "auth-service", "reason": "healthy"}
  ]
}
```

3. Any Jira URLs appended under the code block when escalations occur.

## What you need to code

The following files contain `# TODO(candidate)` markers and must be completed:

| Area              | File                                     | What you need to supply                                                                                |
| ----------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| System prompt     | `prompts/orchestrator_system_prompt.txt` | Write the deterministic “playbook” instructions the LLM must follow.                                   |
| User prompt       | `prompts/orchestrator_user_prompt.txt`   | Provide the run-time instructions (namespace, Slack channel, completion signal).                       |
| Orchestrator flow | `k8s_balancer/agent/orchestrator.py`     | Dispatch the MCP-enabled agent, capture the latest outcome, and return a summary for downstream tests. |

Until you replace those placeholders the agent raises `NotImplementedError` and **no tests will pass**. Filling the prompts and orchestrator logic is the minimum work required to make the checks go green.

## Environment Expectations

-   Python 3.11+
-   Dependencies installed via `pip install -r requirements.text`
-   LangChain is mandatory for LLM calls—do not talk to the OpenAI SDK directly.
-   The MCP stack uses FastMCP (server) and `mcp-use` (client). Leave that wiring intact.
-   Keep all prompts in the `prompts/` directory and avoid adding type hints.

## Repository Layout

```
README.md
requirements.text
prompts/
  orchestrator_system_prompt.txt
  orchestrator_user_prompt.txt
  slack_summary_prompt.txt
k8s_balancer/
  agent/
    agent_runner.py
    orchestrator.py
  core/
    prompt_loader.py
    summary_builder.py
  integrations/
    k8s_client.py
  mcp/
    server.py
  runner.py
scripts/
  run_agent.py
tests/
  test_agent_integration.py
```
