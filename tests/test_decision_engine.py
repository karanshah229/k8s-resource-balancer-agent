import json

import pytest

from k8s_balancer.core.decision_engine import DecisionEngine


def test_decision_engine_returns_structured_response(dummy_llm):
    engine = DecisionEngine(dummy_llm)
    snapshot = {
        'name': 'checkout-service',
        'metrics': {'memory': {'avg': 95, 'p95': 98}},
        'description': {'mem_limit': '1Gi'},
    }

    result = engine.analyze_pod(snapshot)

    assert isinstance(result, dict)
    assert result['recommended_action'] == 'increase_memory_limit'
    assert result['classification'] == 'overloaded'
    assert result['reason']


@pytest.mark.parametrize('pod,expected_action', [
    ('idle-service', 'decrease_requests'),
    ('recommendation-service', 'escalate_inconsistent'),
    ('auth-service', 'skip'),
])
def test_decision_engine_supports_all_actions(dummy_llm, pod, expected_action):
    engine = DecisionEngine(dummy_llm)
    snapshot = {'name': pod}

    result = engine.analyze_pod(snapshot)

    assert result['recommended_action'] == expected_action
    assert result['reason']
