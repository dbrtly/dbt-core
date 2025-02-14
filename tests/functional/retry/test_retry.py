import pytest

from dbt.contracts.results import RunStatus, TestStatus
from dbt.exceptions import DbtRuntimeError, TargetNotFoundError
from dbt.tests.util import run_dbt, write_file, rm_file
from tests.functional.retry.fixtures import (
    models__sample_model,
    models__union_model,
    schema_yml,
    models__second_model,
    macros__alter_timezone_sql,
)


class TestRetry:
    @pytest.fixture(scope="class")
    def models(self):
        return {
            "sample_model.sql": models__sample_model,
            "second_model.sql": models__second_model,
            "union_model.sql": models__union_model,
            "schema.yml": schema_yml,
        }

    @pytest.fixture(scope="class")
    def macros(self):
        return {"alter_timezone.sql": macros__alter_timezone_sql}

    def test_no_previous_run(self, project):
        with pytest.raises(
            DbtRuntimeError, match="Could not find previous run in 'target' target directory"
        ):
            run_dbt(["retry"])

        with pytest.raises(
            DbtRuntimeError, match="Could not find previous run in 'walmart' target directory"
        ):
            run_dbt(["retry", "--state", "walmart"])

    def test_previous_run(self, project):
        # Regular build
        results = run_dbt(["build"], expect_pass=False)

        expected_statuses = {
            "sample_model": RunStatus.Error,
            "second_model": RunStatus.Success,
            "union_model": RunStatus.Skipped,
            "accepted_values_sample_model_foo__False__3": RunStatus.Skipped,
            "accepted_values_second_model_bar__False__3": TestStatus.Warn,
            "accepted_values_union_model_sum3__False__3": RunStatus.Skipped,
        }

        assert {n.node.name: n.status for n in results.results} == expected_statuses

        # Ignore second_model which succeeded
        results = run_dbt(["retry"], expect_pass=False)

        expected_statuses = {
            "sample_model": RunStatus.Error,
            "union_model": RunStatus.Skipped,
            "accepted_values_union_model_sum3__False__3": RunStatus.Skipped,
            "accepted_values_sample_model_foo__False__3": RunStatus.Skipped,
        }

        assert {n.node.name: n.status for n in results.results} == expected_statuses

        # Fix sample model and retry, everything should pass
        fixed_sql = "select 1 as id, 1 as foo"
        write_file(fixed_sql, "models", "sample_model.sql")

        results = run_dbt(["retry"])

        expected_statuses = {
            "sample_model": RunStatus.Success,
            "union_model": RunStatus.Success,
            "accepted_values_union_model_sum3__False__3": TestStatus.Pass,
            "accepted_values_sample_model_foo__False__3": TestStatus.Warn,
        }

        assert {n.node.name: n.status for n in results.results} == expected_statuses

        # No failures in previous run, nothing to retry
        results = run_dbt(["retry"])
        expected_statuses = {}
        assert {n.node.name: n.status for n in results.results} == expected_statuses

        write_file(models__sample_model, "models", "sample_model.sql")

    def test_warn_error(self, project):
        # Regular build
        results = run_dbt(["--warn-error", "build", "--select", "second_model"], expect_pass=False)

        expected_statuses = {
            "second_model": RunStatus.Success,
            "accepted_values_second_model_bar__False__3": TestStatus.Fail,
        }

        assert {n.node.name: n.status for n in results.results} == expected_statuses

        # Retry regular, should pass
        run_dbt(["retry"])

        # Retry with --warn-error, should fail
        run_dbt(["--warn-error", "retry"], expect_pass=False)

    @pytest.mark.skip(
        "Issue #7831: This test fails intermittently. Further details in issue notes."
    )
    def test_custom_target(self, project):
        run_dbt(["build", "--select", "second_model"])
        run_dbt(
            ["build", "--select", "sample_model", "--target-path", "target2"], expect_pass=False
        )

        # Regular retry
        results = run_dbt(["retry"])
        expected_statuses = {"accepted_values_second_model_bar__False__3": TestStatus.Warn}
        assert {n.node.name: n.status for n in results.results} == expected_statuses

        # Retry with custom target
        fixed_sql = "select 1 as id, 1 as foo"
        write_file(fixed_sql, "models", "sample_model.sql")

        results = run_dbt(["retry", "--state", "target2"])
        expected_statuses = {
            "sample_model": RunStatus.Success,
            "accepted_values_sample_model_foo__False__3": TestStatus.Warn,
        }

        assert {n.node.name: n.status for n in results.results} == expected_statuses

        write_file(models__sample_model, "models", "sample_model.sql")

    def test_run_operation(self, project):
        results = run_dbt(
            ["run-operation", "alter_timezone", "--args", "{timezone: abc}"], expect_pass=False
        )

        expected_statuses = {
            "macro.test.alter_timezone": RunStatus.Error,
        }

        assert {n.unique_id: n.status for n in results.results} == expected_statuses

        results = run_dbt(["retry"], expect_pass=False)
        assert {n.unique_id: n.status for n in results.results} == expected_statuses

    def test_fail_fast(self, project):
        result = run_dbt(["--warn-error", "build", "--fail-fast"], expect_pass=False)

        assert result.status == RunStatus.Error
        assert result.node.name == "sample_model"

        results = run_dbt(["retry"], expect_pass=False)

        assert len(results.results) == 1
        assert results.results[0].status == RunStatus.Error
        assert results.results[0].node.name == "sample_model"

        result = run_dbt(["retry", "--fail-fast"], expect_pass=False)
        assert result.status == RunStatus.Error
        assert result.node.name == "sample_model"

    def test_removed_file(self, project):
        run_dbt(["build"], expect_pass=False)

        rm_file("models", "sample_model.sql")

        with pytest.raises(
            TargetNotFoundError, match="depends on a node named 'sample_model' which was not found"
        ):
            run_dbt(["retry"], expect_pass=False)

        write_file(models__sample_model, "models", "sample_model.sql")

    def test_removed_file_leaf_node(self, project):
        write_file(models__sample_model, "models", "third_model.sql")
        run_dbt(["build"], expect_pass=False)

        rm_file("models", "third_model.sql")
        with pytest.raises(ValueError, match="Couldn't find model 'model.test.third_model'"):
            run_dbt(["retry"], expect_pass=False)
