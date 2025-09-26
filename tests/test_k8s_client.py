from k8s_balancer.integrations.k8s_client import KubernetesMCPClient


def test_list_pods_fetches_names(scenario_fixtures):
    client = KubernetesMCPClient()

    pods = client.list_pods('default')

    assert pods == scenario_fixtures['pods']['default']
    assert scenario_fixtures['mcp_calls'][0] == (
        'mcp:k8s.list_pods',
        {'namespace': 'default'},
    )
