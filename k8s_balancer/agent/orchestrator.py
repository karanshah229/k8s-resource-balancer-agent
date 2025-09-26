import json

from k8s_balancer.core.decision_engine import DecisionEngine
from k8s_balancer.core.summary_builder import SummaryBuilder
from k8s_balancer.integrations.k8s_client import KubernetesMCPClient
from k8s_balancer.integrations.slack_client import SlackMCPClient


def _format_float(value):
    if value is None:
        return None
    rounded = round(value, 2)
    text = ('%.2f' % rounded).rstrip('0').rstrip('.')
    return text if text else '0'


def _scale_cpu(value, factor):
    if not value:
        return None
    value = value.strip()
    if value.endswith('m'):
        number = float(value[:-1])
        scaled = max(number * factor, 1)
        return '%dm' % int(round(scaled))
    number = float(value)
    scaled = number * factor
    text = _format_float(scaled)
    return text


def _scale_memory(value, factor):
    if not value:
        return None
    value = value.strip()
    if value.endswith('Gi'):
        number = float(value[:-2])
        scaled = number * factor
        return '%sGi' % _format_float(scaled)
    if value.endswith('Mi'):
        number = float(value[:-2])
        scaled = number * factor
        return '%sMi' % _format_float(scaled)
    if value.endswith('Ki'):
        number = float(value[:-2])
        scaled = number * factor
        return '%sKi' % _format_float(scaled)
    number = float(value)
    scaled = number * factor
    return _format_float(scaled)


class ResourceRebalanceOrchestrator:
    """Coordinates scan, decision, action, and notification for the challenge run."""

    def __init__(self, llm, namespace, slack_channel):
        self.k8s = KubernetesMCPClient()
        self.slack = SlackMCPClient(slack_channel)
        self.namespace = namespace
        self.decision_engine = DecisionEngine(llm)
        self.summary_builder = SummaryBuilder(llm)

    def run(self):
        pods = self.k8s.list_pods(self.namespace)

        rebalanced = []
        escalated = []
        skipped = []
        issues = []

        for pod in pods:
            description = self.k8s.describe_pod(pod)
            metrics = {}
            for metric in ['cpu', 'memory']:
                metrics[metric] = self.k8s.query_metrics(pod, metric, '24h')
            try:
                metrics['oom_kills'] = self.k8s.query_metrics(pod, 'oom_kills', '24h')
            except Exception:
                metrics['oom_kills'] = {'avg': 0, 'p95': 0}

            snapshot = {
                'name': pod,
                'description': description,
                'metrics': metrics,
            }

            decision = self.decision_engine.analyze_pod(snapshot)
            action = decision.get('recommended_action')
            reason = decision.get('reason')

            if action == 'increase_memory_limit':
                new_mem_limit = _scale_memory(description.get('mem_limit'), 1.25)
                update_payload = {'mem_limit': new_mem_limit}
                self.k8s.update_resources(pod, update_payload)
                rebalanced.append({
                    'name': pod,
                    'mem_limit': new_mem_limit,
                })
                continue

            if action == 'decrease_requests':
                new_cpu_request = _scale_cpu(description.get('cpu_request'), 0.8)
                new_mem_request = _scale_memory(description.get('mem_request'), 0.8)
                update_payload = {}
                if new_cpu_request is not None:
                    update_payload['cpu_request'] = new_cpu_request
                if new_mem_request is not None:
                    update_payload['mem_request'] = new_mem_request
                self.k8s.update_resources(pod, update_payload)
                rebalanced.append({
                    'name': pod,
                    'cpu_request': new_cpu_request,
                    'mem_request': new_mem_request,
                })
                continue

            if action == 'escalate_inconsistent':
                title = '%s metrics inconsistent' % pod
                body = {
                    'pod': pod,
                    'metrics': metrics,
                    'reason': reason,
                }
                issue = self.k8s.create_escalation(title, json.dumps(body))
                issues.append(issue)
                escalated.append({
                    'name': pod,
                    'reason': reason,
                    'url': issue.get('url'),
                })
                continue

            skipped.append({
                'name': pod,
                'reason': reason,
            })

        summary_data = {
            'namespace': self.namespace,
            'pods_scanned': len(pods),
            'pods_rebalanced': rebalanced,
            'pods_escalated': escalated,
            'pods_skipped': skipped,
        }

        summary_json = self.summary_builder.build_summary(summary_data)
        try:
            parsed_summary = json.loads(summary_json)
        except Exception:
            parsed_summary = summary_data

        slack_text = '✅ Resource Rebalance Completed\n```%s```' % summary_json
        if issues:
            links = [issue.get('url') for issue in issues if issue.get('url')]
            if links:
                slack_text += '\n' + '\n'.join(links)
        self.slack.post_summary(slack_text)

        return parsed_summary
