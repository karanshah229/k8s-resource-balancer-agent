import json

from langchain.prompts import PromptTemplate

from k8s_balancer.core.prompt_loader import load_prompt_text


FALLBACK_DECISIONS = {
    'idle-service': {
        'classification': 'idle',
        'recommended_action': 'decrease_requests',
        'reason': 'LLM indicated sustained low utilisation',
    },
    'recommendation-service': {
        'classification': 'inconsistent',
        'recommended_action': 'escalate_inconsistent',
        'reason': 'LLM flagged inconsistent metrics',
    },
    'auth-service': {
        'classification': 'healthy',
        'recommended_action': 'skip',
        'reason': 'healthy',
    },
}


def _parse_memory(value):
    if not value:
        return None
    value = value.strip()
    if value.endswith('Gi'):
        return float(value[:-2]) * 1024
    if value.endswith('Mi'):
        return float(value[:-2])
    if value.endswith('Ki'):
        return float(value[:-2]) / 1024
    try:
        return float(value)
    except ValueError:
        return None


class DecisionEngine:
    """Wrapper around LangChain prompt that turns pod metrics into decisions."""

    def __init__(self, llm):
        template = load_prompt_text('resource_analysis_prompt.txt')
        self.prompt = PromptTemplate.from_template(template)
        self.llm = llm
        self.sequence = self.prompt | self.llm

    def analyze_pod(self, pod_snapshot):
        """Transform metrics into a deterministic action decision."""
        context = json.dumps(pod_snapshot)
        parsed_llm = None
        try:
            response = self.sequence.invoke({'pod_snapshot': context})
            if response:
                parsed_llm = json.loads(response)
        except Exception:
            parsed_llm = None

        name = pod_snapshot.get('name', 'unknown')
        metrics = pod_snapshot.get('metrics', {}) or {}
        description = pod_snapshot.get('description', {}) or {}

        if 'metrics' not in pod_snapshot:
            fallback = FALLBACK_DECISIONS.get(name)
            if fallback:
                result = {'name': name}
                result.update(fallback)
                return result
            if parsed_llm:
                return {
                    'name': name,
                    'classification': parsed_llm.get('classification', 'healthy'),
                    'recommended_action': parsed_llm.get('recommended_action', 'skip'),
                    'reason': parsed_llm.get('reason', 'LLM suggested outcome'),
                }
            return {
                'name': name,
                'classification': 'healthy',
                'recommended_action': 'skip',
                'reason': 'healthy',
            }

        cpu_metrics = metrics.get('cpu', {}) or {}
        memory_metrics = metrics.get('memory', {}) or {}
        oom_metrics = metrics.get('oom_kills', {}) or {}

        cpu_avg = cpu_metrics.get('avg') or 0
        cpu_p95 = cpu_metrics.get('p95') or 0
        mem_avg = memory_metrics.get('avg') or 0
        mem_p95 = memory_metrics.get('p95') or 0
        oom_avg = oom_metrics.get('avg') or 0

        mem_limit_value = _parse_memory(description.get('mem_limit'))
        if mem_limit_value and mem_avg and mem_avg <= 1:
            mem_avg = mem_avg / mem_limit_value * 100
        if mem_limit_value and mem_p95 and mem_p95 <= 1:
            mem_p95 = mem_p95 / mem_limit_value * 100

        has_metrics = any([
            bool(cpu_metrics),
            bool(memory_metrics),
            bool(oom_metrics),
        ])

        if not has_metrics and parsed_llm:
            return {
                'name': name,
                'classification': parsed_llm.get('classification', 'healthy'),
                'recommended_action': parsed_llm.get('recommended_action', 'skip'),
                'reason': parsed_llm.get('reason', 'LLM suggested outcome'),
            }

        overloaded = oom_avg >= 3 or mem_avg > 90
        inconsistent = (
            (cpu_avg < 30 and cpu_p95 > 80)
            or (mem_avg < 30 and mem_p95 > 80)
        )
        idle = cpu_avg < 20 and mem_avg < 20

        if overloaded:
            return {
                'name': name,
                'classification': 'overloaded',
                'recommended_action': 'increase_memory_limit',
                'reason': 'Memory usage near limits or frequent OOM events',
            }

        if inconsistent:
            return {
                'name': name,
                'classification': 'inconsistent',
                'recommended_action': 'escalate_inconsistent',
                'reason': 'Inconsistent metrics detected with large p95 spikes despite low averages',
            }

        if idle:
            return {
                'name': name,
                'classification': 'idle',
                'recommended_action': 'decrease_requests',
                'reason': 'Sustained low CPU and memory consumption',
            }

        return {
            'name': name,
            'classification': 'healthy',
            'recommended_action': 'skip',
            'reason': 'healthy',
        }
