import json
import math

from k8s_balancer.agent.orchestrator import ResourceRebalanceOrchestrator


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


def find_update(updates, pod):
    for entry in updates:
        if entry['pod'] == pod:
            return entry
    raise AssertionError('Missing update for %s' % pod)


def extract_json_from_code_block(text):
    start = text.index('```') + 3
    end = text.rindex('```')
    return text[start:end]


def test_orchestrator_rebalances_and_notifies(dummy_llm, scenario_fixtures):
    orchestrator = ResourceRebalanceOrchestrator(dummy_llm, 'default', '#platform-notifications')

    summary = orchestrator.run()

    calls = scenario_fixtures['mcp_calls']
    assert ('mcp:k8s.list_pods', {'namespace': 'default'}) in calls
    memory_query = ('mcp:k8s.metrics.query', {'pod': 'checkout-service', 'metric': 'memory', 'window': '24h'})
    cpu_query = ('mcp:k8s.metrics.query', {'pod': 'idle-service', 'metric': 'cpu', 'window': '24h'})
    assert memory_query in calls
    assert cpu_query in calls
    update_payloads = [payload for tool, payload in calls if tool == 'mcp:k8s.update_resources']
    assert any(payload['pod'] == 'checkout-service' for payload in update_payloads)
    assert any(payload['pod'] == 'idle-service' for payload in update_payloads)
    escalation_calls = [payload for tool, payload in calls if tool == 'mcp:jira.create_issue']
    assert escalation_calls
    slack_calls = [payload for tool, payload in calls if tool == 'mcp:slack.post_message']
    assert slack_calls

    updates = scenario_fixtures.get('updates', [])
    assert len(updates) == 2

    overloaded_update = find_update(updates, 'checkout-service')
    idle_update = find_update(updates, 'idle-service')

    original_mem_limit = parse_quantity(scenario_fixtures['descriptions']['checkout-service']['mem_limit'])
    new_mem_limit = parse_quantity(overloaded_update['mem_limit'])
    assert math.isclose(new_mem_limit, original_mem_limit * 1.25, rel_tol=0.05)

    original_idle_cpu = parse_quantity(scenario_fixtures['descriptions']['idle-service']['cpu_request'])
    new_idle_cpu = parse_quantity(idle_update['cpu_request'])
    assert math.isclose(new_idle_cpu, original_idle_cpu * 0.8, rel_tol=0.05)

    original_idle_mem = parse_quantity(scenario_fixtures['descriptions']['idle-service']['mem_request'])
    new_idle_mem = parse_quantity(idle_update['mem_request'])
    assert math.isclose(new_idle_mem, original_idle_mem * 0.8, rel_tol=0.05)

    issues = scenario_fixtures.get('jira_issues', [])
    assert len(issues) == 1
    assert 'recommendation-service' in issues[0]['title']

    messages = scenario_fixtures.get('slack_messages', [])
    assert len(messages) == 1
    text = messages[0]['text']
    assert '✅ Resource Rebalance Completed' in text
    assert issues[0]['url'] in text

    summary_json = extract_json_from_code_block(text)
    parsed = json.loads(summary_json)

    assert parsed['namespace'] == 'default'
    assert parsed['pods_scanned'] == 4
    assert sorted(pod['name'] for pod in parsed['pods_rebalanced']) == ['checkout-service', 'idle-service']

    checkout_entry = next(item for item in parsed['pods_rebalanced'] if item['name'] == 'checkout-service')
    idle_entry = next(item for item in parsed['pods_rebalanced'] if item['name'] == 'idle-service')

    assert math.isclose(parse_quantity(checkout_entry['mem_limit']), new_mem_limit, rel_tol=0.05)
    assert math.isclose(parse_quantity(idle_entry['cpu_request']), new_idle_cpu, rel_tol=0.05)
    assert math.isclose(parse_quantity(idle_entry['mem_request']), new_idle_mem, rel_tol=0.05)

    assert parsed['pods_escalated']
    escalation = parsed['pods_escalated'][0]
    assert escalation['name'] == 'recommendation-service'
    assert escalation['url'] == issues[0]['url']
    assert 'inconsistent' in escalation['reason'].lower()

    assert parsed['pods_skipped']
    skipped = parsed['pods_skipped'][0]
    assert skipped['name'] == 'auth-service'
    assert skipped['reason'] == 'healthy'

    assert summary == parsed
