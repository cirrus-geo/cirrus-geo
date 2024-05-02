import pytest

DEPLYOMENT_NAME = "test-deployment"


@pytest.fixture()
def deployments(invoke):
    def _deployments(cmd):
        return invoke("deployments " + cmd)

    return _deployments


def test_deployments(deployments):
    result = deployments("")
    assert result.exit_code == 0


def test_deployments_show_no_project(deployments):
    result = deployments("show")
    assert result.exit_code == 1


def test_deployments_show_no_deployments(deployments, project):
    result = deployments("show")
    assert result.exit_code == 0
    assert len(result.stdout) == 0


def test_deployments_add(deployments, project, mock_lambda_get_conf):
    result = deployments(f"add {DEPLYOMENT_NAME}")
    assert result.exit_code == 0


def test_deployments_show(deployments, project):
    result = deployments("show")
    assert result.exit_code == 0
    assert result.stdout.strip() == DEPLYOMENT_NAME


def test_deployments_rm(deployments, project):
    result = deployments(f"rm {DEPLYOMENT_NAME}")
    assert result.exit_code == 0
    result = deployments("show")
    assert result.exit_code == 0
    assert len(result.stdout) == 0


def test_deployments_rm_missing(deployments, project):
    result = deployments(f"rm {DEPLYOMENT_NAME}")
    assert result.exit_code == 0
