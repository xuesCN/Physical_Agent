from physical_agent.application.plan_compiler import compile_agent_output
from physical_agent.cli import _result_actions
from physical_agent.protocol.schemas import Action


def test_cli_reads_actions_from_agent_output_not_compatibility_field():
    canonical = Action(
        id="act_canonical",
        robot="arm_1",
        capability="observe",
    )
    output = compile_agent_output(
        [canonical],
        status="waiting_execution",
        decision="propose",
        lifecycle="submitted",
        message="Canonical proposal.",
    )

    actions = _result_actions(
        {
            "actions": [{"id": "stale_compatibility_action"}],
            "agent_output": output.model_dump(mode="json", by_alias=True),
        }
    )

    assert [action.id for action in actions] == ["act_canonical"]
