import json

from k8s_balancer.core.summary_builder import SummaryBuilder


def test_summary_builder_produces_required_json(dummy_llm):
    builder = SummaryBuilder(dummy_llm)
    run_outcome = {
        'namespace': 'default',
        'pods_scanned': 4,
        'pods_rebalanced': [{'name': 'checkout-service'}],
        'pods_escalated': [],
        'pods_skipped': [{'name': 'auth-service'}],
    }

    summary = builder.build_summary(run_outcome)

    parsed = json.loads(summary)
    assert parsed['namespace'] == run_outcome['namespace']
    assert parsed['pods_scanned'] == run_outcome['pods_scanned']
    assert parsed['pods_rebalanced'] == run_outcome['pods_rebalanced']
    assert parsed['pods_skipped'] == run_outcome['pods_skipped']
    assert 'pods_escalated' in parsed
