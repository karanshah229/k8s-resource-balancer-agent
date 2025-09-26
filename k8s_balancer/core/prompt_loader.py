import os


def load_prompt_text(name):
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompts_dir = os.path.join(repo_root, 'prompts')
    path = os.path.join(prompts_dir, name)
    if not os.path.exists(path):
        raise RuntimeError('Prompt not found: %s' % name)
    with open(path) as handle:
        return handle.read().strip()
