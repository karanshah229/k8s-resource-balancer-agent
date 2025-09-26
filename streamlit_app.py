"""Streamlit UI for running targeted scenario checks."""

import json
from pathlib import Path

import streamlit as st

from scripts.run_agent import build_llm
from k8s_balancer.mcp.server import default_fixtures
from k8s_balancer.runner import create_agent


PROJECT_ROOT = Path(__file__).resolve().parent


def parse_quantity(value):
    if value is None:
        return None
    value = value.strip()
    if value.endswith('Gi'):
        return float(value[:-2]) * 1024
    if value.endswith('Mi'):
        return float(value[:-2])
    if value.endswith('Ki'):
        return float(value[:-2]) / 1024
    if value.endswith('m'):
        return float(value[:-1])
    return float(value)


def build_fixture_for_scenario(name):
    fixtures = default_fixtures()
    fixtures['updates'] = []
    fixtures['slack_messages'] = []
    fixtures['jira_issues'] = []

    mapping = {
        'Out of Memory Killed Pod': 'checkout-service',
        'Idle Pod': 'idle-service',
        'Inconsistent Metrics Pod': 'recommendation-service',
        'Healthy Pod': 'auth-service',
    }
    target = mapping[name]

    fixtures['pods']['default'] = [target]
    fixtures['descriptions'] = {target: fixtures['descriptions'][target]}

    fixtures['metrics'] = {
        (target, 'cpu', '24h'): {'avg': 40, 'p95': 60},
        (target, 'memory', '24h'): {'avg': 45, 'p95': 65},
        (target, 'oom_kills', '24h'): {'avg': 0, 'p95': 0},
    }

    if name == 'Out of Memory Killed Pod':
        fixtures['metrics'][(target, 'memory', '24h')] = {'avg': 95, 'p95': 99}
        fixtures['metrics'][(target, 'oom_kills', '24h')] = {'avg': 4, 'p95': 4}
    elif name == 'Idle Pod':
        fixtures['metrics'][(target, 'cpu', '24h')] = {'avg': 10, 'p95': 18}
        fixtures['metrics'][(target, 'memory', '24h')] = {'avg': 12, 'p95': 19}
    elif name == 'Inconsistent Metrics Pod':
        fixtures['metrics'][(target, 'cpu', '24h')] = {'avg': 18, 'p95': 92}
        fixtures['metrics'][(target, 'memory', '24h')] = {'avg': 15, 'p95': 93}
    elif name == 'Healthy Pod':
        fixtures['metrics'][(target, 'cpu', '24h')] = {'avg': 45, 'p95': 55}
        fixtures['metrics'][(target, 'memory', '24h')] = {'avg': 48, 'p95': 60}

    return fixtures


def run_agent_once(scenario_name):
    fixtures = build_fixture_for_scenario(scenario_name)
    llm = build_llm()
    agent = create_agent(llm, 'default', '#platform-notifications', fixtures=fixtures)
    summary = agent.run()
    state = agent.latest_outcome.state if agent.latest_outcome else {}
    slack_text = agent.latest_outcome.slack_message if agent.latest_outcome else ''
    return summary, state, slack_text, fixtures


def scenario_oom(summary, state, baseline):
    entry = next(item for item in summary['pods_rebalanced'] if item['name'] == 'checkout-service')
    original = parse_quantity(baseline['descriptions']['checkout-service']['mem_limit'])
    new = parse_quantity(entry['mem_limit'])
    passed = abs(new - original * 1.25) <= original * 0.05
    detail = f"Mem limit scaled from {baseline['descriptions']['checkout-service']['mem_limit']} to {entry['mem_limit']}"
    return passed, detail


def scenario_idle(summary, state, baseline):
    entry = next(item for item in summary['pods_rebalanced'] if item['name'] == 'idle-service')
    original_cpu = parse_quantity(baseline['descriptions']['idle-service']['cpu_request'])
    original_mem = parse_quantity(baseline['descriptions']['idle-service']['mem_request'])
    new_cpu = parse_quantity(entry['cpu_request'])
    new_mem = parse_quantity(entry['mem_request'])
    passed = (
        abs(new_cpu - original_cpu * 0.8) <= max(original_cpu * 0.05, 1)
        and abs(new_mem - original_mem * 0.8) <= original_mem * 0.05
    )
    detail = f"CPU {entry['cpu_request']} / Memory {entry['mem_request']}"
    return passed, detail


def scenario_inconsistent(summary, state, baseline):
    entry = next(item for item in summary['pods_escalated'] if item['name'] == 'recommendation-service')
    issues = state.get('jira_issues', [])
    passed = bool(issues) and entry['url'] == issues[0]['url']
    detail = entry['reason']
    return passed, detail


def scenario_healthy(summary, state, baseline):
    entry = next(item for item in summary['pods_skipped'] if item['name'] == 'auth-service')
    passed = entry['reason'] == 'healthy'
    detail = 'Pod marked healthy and skipped'
    return passed, detail


SCENARIOS = {
    'Out of Memory Killed Pod': scenario_oom,
    'Idle Pod': scenario_idle,
    'Inconsistent Metrics Pod': scenario_inconsistent,
    'Healthy Pod': scenario_healthy,
}


def render_slack_message(slack_text):
    if not slack_text:
        st.write('No Slack message captured.')
        return

    lines = slack_text.strip().split('\n')
    header = lines[0]
    link = next((line for line in lines if line.startswith('http')), '')
    code_block = slack_text.split('```')
    json_payload = code_block[1] if len(code_block) > 1 else '{}'

    st.subheader('Slack Summary')
    st.markdown(f"**{header}**")
    try:
        parsed = json.loads(json_payload)
        st.json(parsed, expanded=False)
    except json.JSONDecodeError:
        st.code(json_payload, language='json')

    if link:
        st.markdown(f"[View escalation]({link})")


def inject_styles():
    st.markdown(
        """
        <style>
        :root {
            color-scheme: dark;
        }
        [data-testid="stAppViewContainer"] {
            background: #0b1120;
            color: #e2e8f0;
        }
        [data-testid="stHeader"] {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.05) 0%, rgba(16, 185, 129, 0.05) 100%) !important;
            color: #e2e8f0;
            border-bottom: 1px solid rgba(148, 163, 184, 0.2);
        }
        /* Hide ONLY the header toolbar, not the entire first div */
        header[data-testid="stHeader"] {
            display: none !important;
        }
        
        /* Hide toolbar elements */
        [data-testid="stToolbar"] {
            display: none !important;
        }
        [data-testid="stDeployButton"],
        [data-testid="stStopButton"] {
            display: none !important;
        }
        h1, h2, h3, h4, h5, h6, label, p, span {
            color: #e2e8f0 !important;
        }
        .css-16idsys p {
            color: #e2e8f0 !important;
        }
        .stSelectbox>div>div>label {
            color: #cbd5f5 !important;
            font-weight: 600;
        }
        .stSelectbox [data-baseweb="select"] > div {
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(148, 163, 184, 0.3);
            color: #e2e8f0;
        }
        .stSelectbox [data-baseweb="select"] svg {
            color: #94a3b8;
        }
        .stButton>button {
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
            color: #f8fafc !important;
            border: none;
            border-radius: 999px;
            padding: 0.6rem 1.6rem;
            font-weight: 600;
            box-shadow: 0 10px 25px rgba(37, 99, 235, 0.35);
        }
        .stButton>button:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 30px rgba(37, 99, 235, 0.45);
        }
        .stSuccess, .stError {
            border-radius: 0.75rem;
            padding: 1rem;
        }
        .stSuccess {
            background: rgba(16, 185, 129, 0.16) !important;
            color: #34d399 !important;
        }
        .stError {
            background: rgba(248, 113, 113, 0.12) !important;
            color: #fca5a5 !important;
        }
        .stSpinner>div {
            color: #38bdf8 !important;
        }
        .stJson, .stJson > div {
            background: rgba(15, 23, 42, 0.8) !important;
            border-radius: 0.75rem !important;
        }
        .stCode>div {
            background: rgba(15, 23, 42, 0.8) !important;
            border-radius: 0.75rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(page_title="K8s Resource Rebalancer Tests", layout="centered")
    inject_styles()
    st.title("Kubernetes Resource Rebalancer – Test Runner")

    st.markdown("Choose a scenario to verify its behaviour and preview the Slack summary generated by the agent.")

    scenario_names = list(SCENARIOS.keys())
    selected = st.selectbox("Scenario", scenario_names, index=0)

    if st.button("Run Test", type="primary"):
        with st.spinner(f"Running `{selected}` scenario..."):
            summary, state, slack_text, baseline = run_agent_once(selected)
            checker = SCENARIOS[selected]
            passed, detail = checker(summary, state, baseline)

        if passed:
            st.success(detail)
        else:
            st.error(detail)

        render_slack_message(slack_text)


if __name__ == "__main__":
    main()
