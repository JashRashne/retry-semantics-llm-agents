import ast
from pathlib import Path


SOURCE = Path(
    "src/retry_semantics/study2/provider_paper_collection.py"
)


def test_h1_constructor_ack_facts_are_unvalidated_before_validator():
    """
    Regression for the first live Sheets primary attempt.

    H1 constructor transport facts must enter
    validate_append_acknowledgement() with acknowledgement_validated=False.
    The validator itself owns the False -> True transition after validating
    the raw provider acknowledgement.
    """
    tree = ast.parse(SOURCE.read_text())

    collect = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "collect_sheets_arm"
    )

    assignments = []

    for node in ast.walk(collect):
        if not isinstance(node, ast.Assign):
            continue

        if not any(
            isinstance(target, ast.Name) and target.id == "post_facts"
            for target in node.targets
        ):
            continue

        if not isinstance(node.value, ast.Call):
            continue

        func = node.value.func

        if not (
            isinstance(func, ast.Name)
            and func.id == "DispatchFacts"
        ):
            continue

        assignments.append(node.value)

    assert len(assignments) == 1

    call = assignments[0]

    assert len(call.args) == 5

    acknowledgement_validated = call.args[3]
    remote_commit_certified = call.args[4]

    assert isinstance(acknowledgement_validated, ast.Constant)
    assert acknowledgement_validated.value is False

    assert isinstance(remote_commit_certified, ast.Constant)
    assert remote_commit_certified.value is False
