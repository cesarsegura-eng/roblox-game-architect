import json
import re
from decimal import Decimal

import pytest

from core.budget import IterationBudget, SpendBudget
from core.llm.types import CostQuote, GenerationResponse, Usage
from core.studio_building import StudioBlockoutAgent, StudioBlockoutError
from sandbox.action_policy import validate_action


class _Provider:
    name = "test"

    def __init__(self, *, part_name="Floor", size=None):
        self.quoted_requests = []
        self.generated_requests = []
        self.part_name = part_name
        self.size = size or {"x": 20, "y": 1, "z": 20}

    def quote_max_cost(self, request):
        self.quoted_requests.append(request)
        return CostQuote(Decimal(0))

    def generate(self, request):
        self.generated_requests.append(request)
        trusted = "\n".join(item.text for item in request.instructions)
        action_id = re.search(r"Action ID: ([^\n]+)", trusted).group(1)
        root = re.search(r"Root Model name: ([^\n]+)", trusted).group(1)
        part = self.part_name
        part_path = ["Workspace", root, part]
        operations = [
            {
                "op": "create_instance",
                "op_id": "root",
                "parent": {"path": ["Workspace"], "expect_class": "Workspace"},
                "name": root,
                "class_name": "Model",
            },
            {
                "op": "create_instance",
                "op_id": "part",
                "parent": {"path": ["Workspace", root], "expect_class": "Model"},
                "name": part,
                "class_name": "Part",
            },
        ]
        values = {
            "Size": self.size,
            "Position": {"x": 0, "y": 0, "z": 0},
            "Color": {"r": 0.2, "g": 0.4, "b": 0.2},
            "Material": {"enum": "Material", "item": "Grass"},
            "Anchored": True,
            "CanCollide": True,
        }
        for index, (property_name, value) in enumerate(values.items()):
            operations.append(
                {
                    "op": "set_property",
                    "op_id": f"set-{index}",
                    "target": {"path": part_path, "expect_class": "Part"},
                    "property": property_name,
                    "value": value,
                }
            )
        payload = {
            "type": "edit.action",
            "action_id": action_id,
            "declared_scope": [{"path": ["Workspace", root], "extent": "subtree"}],
            "operations": operations,
        }
        text = json.dumps(payload)
        return GenerationResponse(text, self.name, "test", Usage(1, 1, Decimal(0)))


def test_agent_returns_a_sandbox_validated_blockout():
    action = StudioBlockoutAgent(
        _Provider(),
        validator=validate_action,
        iterations=IterationBudget(2),
        spend=SpendBudget(Decimal(0)),
    ).generate("A grassy clearing with a lookout.")
    validate_action(action)
    assert action["action_id"].startswith("generated-")
    assert sum(op.get("class_name") == "Part" for op in action["operations"]) == 1


def test_agent_rejects_empty_briefs_before_calling_provider():
    agent = StudioBlockoutAgent(_Provider(), validator=validate_action)
    with pytest.raises(StudioBlockoutError):
        agent.generate("  ")


def test_studio_agent_quotes_the_matching_first_call_without_spending():
    provider = _Provider()
    spend = SpendBudget(Decimal("0.25"))
    agent = StudioBlockoutAgent(
        provider,
        validator=validate_action,
        iterations=IterationBudget(1),
        spend=spend,
    )

    quote = agent.quote_next_call("A grassy clearing with a lookout.")
    agent.generate("A grassy clearing with a lookout.")

    assert quote == CostQuote(Decimal(0))
    quoted = provider.quoted_requests[0]
    generated = provider.generated_requests[0]
    quote_instructions = "\n".join(item.text for item in quoted.instructions)
    generation_instructions = "\n".join(item.text for item in generated.instructions)
    assert "RGA Blockout f f f f f f f f" in quote_instructions
    assert "Action ID: generated-f f f f f f f f f f f f f f f f" in quote_instructions
    assert "world-environments" in quote_instructions
    assert "A grassy clearing with a lookout." in quoted.untrusted[0].text
    assert "Action ID:" in generation_instructions
    assert spend.spent == 0
    assert spend.reserved == 0


def test_studio_blockout_requires_a_named_flat_elongated_route_part():
    agent = StudioBlockoutAgent(
        _Provider(part_name="Forest trail", size={"x": 4, "y": 0.5, "z": 40}),
        validator=validate_action,
        iterations=IterationBudget(1),
        spend=SpendBudget(Decimal(0)),
    )

    action = agent.generate("Create a forest trail with a lookout.")

    assert any(
        op.get("class_name") == "Part" and op["name"] == "Forest trail"
        for op in action["operations"]
    )


def test_studio_blockout_retries_when_requested_route_name_is_missing():
    provider = _Provider(part_name="Forest floor")
    agent = StudioBlockoutAgent(
        provider,
        validator=validate_action,
        iterations=IterationBudget(2),
        spend=SpendBudget(Decimal(0)),
    )

    with pytest.raises(StudioBlockoutError, match="no policy-valid Studio blockout"):
        agent.generate("Create a forest trail with a lookout.")

    assert len(provider.generated_requests) == 2
    assert (
        "missing named requested features: path"
        in provider.generated_requests[1].untrusted[-1].text
    )


def test_studio_blockout_retries_when_named_route_is_not_walkable_geometry():
    provider = _Provider(part_name="Forest trail")
    agent = StudioBlockoutAgent(
        provider,
        validator=validate_action,
        iterations=IterationBudget(2),
        spend=SpendBudget(Decimal(0)),
    )

    with pytest.raises(StudioBlockoutError, match="no policy-valid Studio blockout"):
        agent.generate("Create a forest trail.")

    assert "flat footprint" in provider.generated_requests[1].untrusted[-1].text


def test_studio_blockout_retries_when_house_features_are_not_named():
    provider = _Provider(part_name="Exterior wall")
    agent = StudioBlockoutAgent(
        provider,
        validator=validate_action,
        iterations=IterationBudget(2),
        spend=SpendBudget(Decimal(0)),
    )

    with pytest.raises(StudioBlockoutError, match="no policy-valid Studio blockout"):
        agent.generate("Build a house with an interior room and doorway.")

    feedback = provider.generated_requests[1].untrusted[-1].text
    assert "entry" in feedback
    assert "interior" in feedback
    assert "roof" in feedback


def test_house_interior_only_blockout_does_not_require_exterior_parts():
    agent = StudioBlockoutAgent(
        _Provider(part_name="Interior room"),
        validator=validate_action,
        iterations=IterationBudget(1),
        spend=SpendBudget(Decimal(0)),
    )

    action = agent.generate("Design the interior only of a house.")

    assert action["type"] == "edit.action"


def test_spanish_house_interior_only_scope_is_recognized():
    agent = StudioBlockoutAgent(
        _Provider(part_name="Habitación interior"),
        validator=validate_action,
        iterations=IterationBudget(1),
        spend=SpendBudget(Decimal(0)),
    )

    action = agent.generate("Diseña solo el interior de una casa.")

    assert action["type"] == "edit.action"
