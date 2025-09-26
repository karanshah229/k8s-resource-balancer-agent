# Kubernetes Resource Rebalancer Agent Challenge

## Persona
Developer in a product-based company running microservices on Kubernetes.

## Scenario
Some pods in the target namespace suffer from frequent OOMKills while others stay underutilized. Engineers currently tweak resource requests/limits manually, which is slow and error-prone. Your mission is to build an autonomous agent that keeps the namespace balanced.

## Deterministic Goal
A run is successful when:
- Every pod in the namespace is scanned.
- Each problematic pod is either rebalanced automatically or escalated to Jira.
- A Slack message posts a JSON summary of every action.

## MCP Tooling
The FastMCP server must expose mocked tools that behave like the platform services. The agent communicates through `mcp-use`.

```
mcp:k8s.metrics.query(pod, metric, window) -> {"avg": number, "p95": number}
mcp:k8s.describe(pod) -> {"cpu_request": str, "cpu_limit": str, "mem_request": str, "mem_limit": str}
mcp:k8s.update_resources(pod, cpu_request?, cpu_limit?, mem_request?, mem_limit?) -> {"status": "updated" | "failed"}
mcp:slack.post_message(channel, text, blocks?) -> {"ts": str, "url": str}
mcp:jira.create_issue(project, title, body) -> {"issue_id": str, "url": str}
```

Use `metric` values `cpu`, `memory`, and `oom_kills` with a `window` of `24h` when querying metrics so the fixtures line up with the tests.

All tools should return deterministic mock data for the provided fixtures so tests can assert behaviour.

## Decision Rules
- If the pod has `OOMKilled >= 3` in the last 24h **or** `avg memory usage > 90%` of limit: increase memory limit by +25%.
- If `avg CPU < 20%` **and** `avg memory < 20%`: decrease requests by –20%.
- If metrics are inconsistent (averages low but p95 spikes), escalate via Jira and include the escalation in the Slack summary.
- Healthy pods must be listed as skipped.

## Expected Slack Notification
Slack message must include:
1. Header text: `✅ Resource Rebalance Completed`
2. Code block containing JSON shaped as:
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
3. Links to any Jira escalations.

## Project Rules
1. Use `pip` with the provided `requirements.text`. No build tools.
2. Do not add type hints.
3. Interact with models through LangChain (never call an SDK like `openai` directly).
4. Build the MCP server with FastMCP; build the MCP client with `mcp-use`.
5. Store prompts as standalone text files inside the `prompts/` directory.
6. Keep dependencies minimal.
7. Group functionality in separate packages under `k8s_balancer/`.
8. MCP tools must return mock data driven by the test scenario.
9. Automated tests will be added later to validate your implementation.

## Repository Layout
```
README.md
requirements.text
prompts/
  resource_analysis_prompt.txt
  slack_summary_prompt.txt
k8s_balancer/
  agent/
    orchestrator.py
  core/
    decision_engine.py
    prompt_loader.py
    summary_builder.py
  integrations/
    k8s_client.py
    slack_client.py
  mcp/
    server.py
    client_runner.py
  runner.py
scripts/
  run_agent.py
tests/
  README.md
```

## Getting Started
1. Install dependencies: `pip install -r requirements.text`.
2. Implement the FastMCP server mocks in `k8s_balancer/mcp/server.py`.
3. Wire up `mcp-use` in the integration clients.
4. Implement the decision logic and orchestration flow.
5. Build the Slack summary using LangChain prompts.
6. Add tests under `tests/` once the core behaviour is ready.

## Testing Expectations
The final tests will simulate four pods:
- OOMKilled pod -> expect `+25%` memory limit update.
- Idle pod -> expect `-20%` request reduction.
- Inconsistent metrics -> expect Jira escalation and Slack link.
- Healthy pod -> expect skip entry.

Every pod must end up in exactly one of the three result lists. The Slack JSON must be deterministic so assertions can parse it safely.
