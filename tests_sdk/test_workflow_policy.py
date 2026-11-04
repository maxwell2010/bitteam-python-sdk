"""Offline workflow policy checks; no Actions runs, cancellations or builds."""
from fnmatch import fnmatchcase
from pathlib import Path
import re

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/sdk.yml"


def workflow():
    # BaseLoader preserves the GitHub YAML key 'on' rather than YAML 1.1 bools.
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def triggers(config, event, *, branch="main", tag=None):
    events = config["on"]
    if event not in events:
        return False
    if event != "push":
        return True
    options = events[event] or {}
    if tag is not None:
        return not options.get("branches") and not options.get("branches-ignore")
    return (not options.get("branches") or any(fnmatchcase(branch, rule) for rule in options["branches"]))


def value(expression, context):
    expression = expression.strip()
    if expression in ("true", "false"):
        return expression == "true"
    if expression == "success()":
        return True
    if expression.startswith("'") and expression.endswith("'"):
        return expression[1:-1]
    result = context
    for part in expression.split("."):
        result = result.get(part) if isinstance(result, dict) else None
    return result


def condition(expression, context):
    """Evaluate only the workflow's simple AND/OR/equality policy grammar."""
    expression = expression.removeprefix("${{").removesuffix("}}").strip()
    if "||" in expression:
        return any(condition(part, context) for part in expression.split("||"))
    if "&&" in expression:
        return all(condition(part, context) for part in expression.split("&&"))
    if "==" in expression:
        left, right = expression.split("==", 1)
        return value(left, context) == value(right, context)
    return bool(value(expression, context))


def group(config, *, event="pull_request", number=1, ref="refs/pull/1/merge", name="SDK tests and distributions", sha="head-a", run_id=100):
    expression = config["concurrency"]["group"]
    context = {"github": {"workflow": name, "event_name": event,
        "event": {"pull_request": {"number": number}}, "ref": ref, "sha": sha, "run_id": run_id}}
    def expand(match):
        alternatives = match.group(1).split("||")
        return str(next((value(item, context) for item in alternatives if value(item, context)), ""))
    return re.sub(r"\$\{\{(.*?)\}\}", expand, expression)


@pytest.mark.parametrize("event,branch,tag,expected", [
    ("push", "main", None, True),
    ("push", "feature/change", None, False),
    ("push", "fix/cloud-lifecycle-timeouts", None, False),
    ("push", "main", "v-unreleased", False),
    ("pull_request", "feature/change", None, True),
    ("workflow_dispatch", "main", None, True),
])
def test_feature_push_cannot_duplicate_pr_matrix_but_main_and_pr_checks_remain(event, branch, tag, expected):
    assert triggers(workflow(), event, branch=branch, tag=tag) is expected


def test_superseded_pr_runs_share_group_without_colliding_with_other_prs_or_events():
    config = workflow()
    assert config["concurrency"]["cancel-in-progress"] == "true"
    assert group(config, sha="older", run_id=100) == group(config, sha="newer", run_id=101)
    assert group(config, number=1) != group(config, number=2, ref="refs/pull/2/merge")
    assert group(config, name="unrelated workflow") != group(config)
    push = group(config, event="push", number=None, ref="refs/heads/main")
    assert push == group(config, event="push", number=None, ref="refs/heads/main", sha="newer")
    assert push != group(config)
    assert push != group(config, event="workflow_dispatch", number=None, ref="refs/heads/main")


def test_all_eight_platform_checks_and_skip_audit_remain_unconditional():
    config = workflow()
    assert config["permissions"] == {"contents": "read"}
    job = config["jobs"]["sdk"]
    assert job["strategy"]["fail-fast"] == "false"
    assert job["strategy"]["matrix"] == {
        "os": ["ubuntu-latest", "windows-latest"],
        "python": ["3.10", "3.11", "3.12", "3.13"],
    }
    for name in ("Run offline SDK tests", "Verify only the native DPAPI test can skip"):
        step = next(step for step in job["steps"] if step.get("name") == name)
        assert "if" not in step


@pytest.mark.parametrize("event,verify,allowed", [
    ("push", False, False), ("push", True, False),
    ("pull_request", False, False), ("pull_request", True, False),
    ("workflow_dispatch", False, False), ("workflow_dispatch", True, True),
])
def test_distributions_cannot_build_smoke_or_upload_on_push_or_pr(event, verify, allowed):
    config = workflow()
    context = {"github": {"event_name": event}, "inputs": {"verify_distribution": verify}}
    steps = config["jobs"]["sdk"]["steps"]
    for name in ("Build wheel and source distribution", "Test installed wheel in an isolated environment",
                 "Archive explicitly requested distribution checks"):
        step = next(step for step in steps if step.get("name") == name)
        assert condition(step["if"], context) is allowed
    assert config["on"]["workflow_dispatch"]["inputs"]["verify_distribution"]["default"] == "false"


def test_postgres_runtime_is_an_independent_isolated_service_check_without_builds():
    config = workflow()
    job = config["jobs"]["postgres-runtime"]
    assert job["runs-on"] == "ubuntu-latest"
    assert "if" not in job and "needs" not in job and "permissions" not in job
    service = job["services"]["postgres"]
    assert service["image"] == "postgres:16"
    assert service["ports"] == ["127.0.0.1:5432:5432"]
    assert service["env"] == {"POSTGRES_USER": "sdk_test", "POSTGRES_PASSWORD": "synthetic-ci-only",
                               "POSTGRES_DB": "sdk_runtime"}
    assert "pg_isready" in service["options"]
    script = next(step for step in job["steps"] if step.get("name") == "Run isolated PostgreSQL integration")
    assert "if" not in script
    assert script["run"].startswith("python scripts_sdk/check_storage_runtime.py --postgres-dsn ")
    assert script["run"].endswith("@127.0.0.1:5432/sdk_runtime")
    for step in job["steps"]:
        command = step.get("run", "")
        assert not any(forbidden in command for forbidden in ("python -m build", "check_wheel", "twine", "pip install ."))
        assert "${{ secrets." not in command


def test_core_source_smoke_uses_fresh_core_only_venv_and_explicit_isolated_source():
    job = workflow()["jobs"]["core-source"]
    assert job["runs-on"] == "ubuntu-latest"
    assert "if" not in job and "needs" not in job and "permissions" not in job
    steps = job["steps"]
    create = next(step for step in steps if step.get("name") == "Create a fresh core-only environment")
    install = next(step for step in steps if step.get("name") == "Install only core dependencies")
    check = next(step for step in steps if step.get("name") == "Check exact source checkout without optional extras")
    assert create["run"] == 'python -m venv "$RUNNER_TEMP/bitteam-core"'
    assert install["run"] == '"$RUNNER_TEMP/bitteam-core/bin/python" -I -m pip --isolated install -r requirements-sdk.txt'
    assert check["run"] == '"$RUNNER_TEMP/bitteam-core/bin/python" -I scripts_sdk/check_core_source.py --source-root "$GITHUB_WORKSPACE"'
    assert "if" not in check
    for step in steps:
        command = step.get("run", "")
        assert not any(forbidden in command for forbidden in (
            "python -m build", "check_wheel", "pip install .", "requirements-sdk-dev", "[charts]", "[postgres]", "[sqlite]"))
        assert "${{ secrets." not in command
