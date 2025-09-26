import json

from langchain.prompts import PromptTemplate

from k8s_balancer.core.prompt_loader import load_prompt_text


class SummaryBuilder:
    """Responsible for transforming run results into a Slack JSON summary."""

    def __init__(self, llm):
        template = load_prompt_text('slack_summary_prompt.txt')
        self.prompt = PromptTemplate.from_template(template)
        self.llm = llm
        self.sequence = self.prompt | self.llm

    def build_summary(self, run_outcome):
        """Return a deterministic JSON summary for Slack notifications."""
        context = json.dumps(run_outcome)
        llm_output = None
        try:
            llm_output = self.sequence.invoke({'run_outcome': context})
        except Exception:
            llm_output = None

        if llm_output:
            candidate = llm_output.strip()
            try:
                parsed = json.loads(candidate)
                required = {'namespace', 'pods_scanned', 'pods_rebalanced', 'pods_escalated', 'pods_skipped'}
                if isinstance(parsed, dict) and required.issubset(parsed.keys()):
                    return candidate
            except Exception:
                pass

        summary = {
            'namespace': run_outcome.get('namespace'),
            'pods_scanned': run_outcome.get('pods_scanned', 0),
            'pods_rebalanced': run_outcome.get('pods_rebalanced', []),
            'pods_escalated': run_outcome.get('pods_escalated', []),
            'pods_skipped': run_outcome.get('pods_skipped', []),
        }
        return json.dumps(summary)
