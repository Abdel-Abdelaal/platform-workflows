import json
from pathlib import Path

import pytest

from tools.ai_contract import Analysis


@pytest.mark.parametrize("name", ["review", "audit", "fix", "standards-review"])
def test_prompt_example_is_valid_contract_json(name: str) -> None:
    prompt = (Path(__file__).parents[1] / "prompts" / f"{name}.md").read_text(
        encoding="utf-8"
    )
    start = prompt.index('{"summary":')
    example, _ = json.JSONDecoder().raw_decode(prompt[start:])
    Analysis.model_validate(example)
