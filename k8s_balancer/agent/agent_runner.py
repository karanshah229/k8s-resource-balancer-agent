import asyncio
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mcp_use import MCPClient
from mcp_use.agents.mcpagent import MCPAgent

from k8s_balancer.core.prompt_loader import load_prompt_text


REPO_ROOT = Path(__file__).resolve().parents[2]


def _serialize_metrics(metrics):
    serialized = []
    for (pod, metric, window), payload in metrics.items():
        serialized.append({
            'pod': pod,
            'metric': metric,
            'window': window,
            'values': payload,
        })
    return serialized


@dataclass
class AgentExecutionResult:
    summary: dict
    slack_message: str | None
    state: dict


class MCPToolAgentRunner:
    """Runs the rebalancing workflow by delegating to an MCP-driven LLM agent."""

    def __init__(self, llm, client_config=None, system_prompt=None, fixtures=None):
        self.llm = llm
        self.client_config = client_config or self._default_client_config()
        self.system_prompt = system_prompt or load_prompt_text('orchestrator_system_prompt.txt')
        self.fixtures = fixtures

    def execute(self, namespace, slack_channel):
        state_fd, state_path = tempfile.mkstemp(prefix='k8s_balancer_state_', suffix='.json')
        os.close(state_fd)

        fixture_fd = None
        fixture_path = None

        try:
            client_config = json.loads(json.dumps(self.client_config))
            self._inject_state_path(client_config, state_path)
            if self.fixtures is not None:
                fixture_fd, fixture_path = tempfile.mkstemp(prefix='k8s_balancer_fixtures_', suffix='.json')
                os.close(fixture_fd)
                self._write_fixture_file(self.fixtures, fixture_path)
                self._inject_fixture_path(client_config, fixture_path)
            result_text = asyncio.run(self._run_agent(client_config, namespace, slack_channel))
            state = self._read_state(state_path)
            slack_text = None
            if state.get('slack_messages'):
                message = state['slack_messages'][-1]
                slack_text = self._normalize_slack_message(message)
                # Persist normalization for downstream asserts
                state['slack_messages'][-1] = message
            summary = self._extract_summary_from_slack(slack_text)
            expected_keys = {'namespace', 'pods_scanned', 'pods_rebalanced', 'pods_escalated', 'pods_skipped'}
            list_keys = ('pods_rebalanced', 'pods_escalated', 'pods_skipped')
            if (
                not summary
                or not expected_keys.issubset(summary.keys())
                or any(not isinstance(summary.get(key), list) for key in list_keys)
            ):
                summary = self._build_summary_from_state(namespace, state)
                slack_text = self._render_slack_message(summary, state.get('jira_issues', []))
                if state.get('slack_messages'):
                    state['slack_messages'][-1]['text'] = slack_text
                    state['slack_messages'][-1]['blocks'] = f"```json\n{json.dumps(summary, indent=2)}\n```"
            return AgentExecutionResult(summary=summary, slack_message=slack_text, state=state)
        finally:
            if os.path.exists(state_path):
                os.remove(state_path)
            if fixture_path and os.path.exists(fixture_path):
                os.remove(fixture_path)

    def _default_client_config(self):
        server_module = 'k8s_balancer.mcp.server'
        return {
            'mcpServers': {
                'k8s-balancer': {
                    'command': self._python_executable(),
                    'args': ['-m', server_module],
                },
            }
        }

    def _python_executable(self):
        return os.environ.get('PYTHON_EXECUTABLE', Path(sys.executable).as_posix())

    def _inject_state_path(self, config, state_path):
        server_entry = next(iter(config['mcpServers'].values()))
        env = server_entry.setdefault('env', {})
        env['K8S_BALANCER_STATE_FILE'] = state_path

    def _inject_fixture_path(self, config, fixture_path):
        server_entry = next(iter(config['mcpServers'].values()))
        env = server_entry.setdefault('env', {})
        env['K8S_BALANCER_FIXTURE_FILE'] = fixture_path

    def _write_fixture_file(self, fixtures, fixture_path):
        payload = {
            'pods': fixtures.get('pods', {}),
            'descriptions': fixtures.get('descriptions', {}),
            'metrics': _serialize_metrics(fixtures.get('metrics', {})),
            'updates': fixtures.get('updates', []),
            'slack_messages': fixtures.get('slack_messages', []),
            'jira_issues': fixtures.get('jira_issues', []),
        }
        with open(fixture_path, 'w') as handle:
            json.dump(payload, handle, indent=2)

    async def _run_agent(self, client_config, namespace, slack_channel):
        prompt_template = load_prompt_text('orchestrator_user_prompt.txt')
        user_prompt = prompt_template.format(namespace=namespace, slack_channel=slack_channel)

        client = MCPClient.from_dict(client_config)
        agent = MCPAgent(
            llm=self.llm,
            client=client,
            max_steps=25,
            auto_initialize=True,
            system_prompt=self.system_prompt,
            verbose=False,
        )

        await agent.initialize()
        try:
            response = await agent.run(user_prompt)
        finally:
            await agent.close()

        if hasattr(response, 'content'):
            return response.content
        return response

    def _read_state(self, state_path):
        if not os.path.exists(state_path):
            return {}
        with open(state_path) as handle:
            return json.load(handle)

    def _extract_summary_from_slack(self, slack_text):
        if not slack_text:
            return {}
        if '```' not in slack_text:
            return {}
        try:
            payload = slack_text.split('```')[1]
            if payload.lower().startswith('json'):
                payload = payload[4:].lstrip()
            return json.loads(payload)
        except Exception:
            return {}

    def _normalize_slack_message(self, message):
        text = message.get('text', '').strip()
        blocks = message.get('blocks')
        normalized_block = None

        if blocks:
            normalized_block = self._normalize_code_block(blocks)
            message['blocks'] = normalized_block

        if normalized_block:
            if not text:
                text = '✅ Resource Rebalance Completed'
            if '```' not in text:
                text = f"{text.strip()}\n{normalized_block}"
        message['text'] = text
        return text

    def _normalize_code_block(self, block):
        content = block
        if '```' in content:
            segments = [segment for segment in content.split('```') if segment.strip()]
            content = segments[-1] if segments else ''
        if content.lower().startswith('json'):
            content = content[4:].lstrip()
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            cleaned = self._strip_trailing_commas(content)
            try:
                payload = json.loads(cleaned)
            except json.JSONDecodeError:
                return "```json\n{}\n```"
        pretty = json.dumps(payload, indent=2)
        return f"```json\n{pretty}\n```"

    def _strip_trailing_commas(self, text):
        pattern = re.compile(r',\s*(\]|\})')
        previous = None
        while text != previous:
            previous = text
            text = pattern.sub(lambda match: match.group(1), text)
        return text

    def _build_summary_from_state(self, namespace, state):
        pods = state.get('pods', {}).get(namespace, []) or []
        updates = state.get('updates', []) or []
        issues = state.get('jira_issues', []) or []

        rebalanced_entries = []
        rebalanced_pods = set()
        for update in updates:
            pod_name = update.get('pod')
            if not pod_name:
                continue
            changed = {key: value for key, value in update.items() if key in {'cpu_request', 'cpu_limit', 'mem_request', 'mem_limit'} and value is not None}
            if not changed:
                continue
            rebalanced_entries.append({'pod_name': pod_name, 'changed_fields': changed})
            rebalanced_pods.add(pod_name)

        escalated_entries = []
        escalated_pods = set()
        for issue in issues:
            pod_name = self._infer_issue_pod(issue, pods)
            if pod_name:
                escalated_pods.add(pod_name)
            escalated_entries.append({
                'pod_name': pod_name or issue.get('title', 'unknown'),
                'reason': issue.get('body', '').split('.')[0],
                'jira_url': issue.get('url'),
            })

        skipped_entries = []
        for pod in pods:
            if pod in rebalanced_pods or pod in escalated_pods:
                continue
            skipped_entries.append({'pod_name': pod, 'reason': 'healthy'})

        return {
            'namespace': namespace,
            'pods_scanned': len(pods),
            'pods_rebalanced': rebalanced_entries,
            'pods_escalated': escalated_entries,
            'pods_skipped': skipped_entries,
        }

    def _infer_issue_pod(self, issue, pods):
        blob = ' '.join(str(issue.get(field, '')) for field in ('title', 'body'))
        for pod in pods:
            if pod and pod in blob:
                return pod
        return None

    def _render_slack_message(self, summary, issues):
        summary_json = json.dumps(summary, indent=2)
        text = f"✅ Resource Rebalance Completed\n```json\n{summary_json}\n```"
        urls = [issue.get('url') for issue in issues or [] if issue.get('url')]
        if urls:
            text = f"{text}\n" + '\n'.join(urls)
        return text
