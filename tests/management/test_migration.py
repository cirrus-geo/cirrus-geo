from __future__ import annotations

import io
import json

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

import boto3
import moto
import pytest

from botocore.exceptions import ClientError
from pytest_mock import MockerFixture

from cirrus.lib.statedb import StateDB
from cirrus.lib.utils import get_client
from cirrus.management.migration import DbUpdatePlan, MigrationRecord, Migrator
from tests.conftest import MOCK_REGION

TABLE_NAME = "cirrus-test-state"
PAYLOADS_BUCKET = "payloads"
BAD_ARN_VALUE = (
    "arn:aws:states:us-east-1:123456789012:execution:test-workflow1:does-not-exist"
)


# ---------------------------------------------------------------------------
# Module-local stepfunctions fixture with real ASL execution
# ---------------------------------------------------------------------------
# This file needs moto to actually execute step function state machines so
# that describe_execution returns real output for Step C of the migration.
# Enabling this flag globally in tests/conftest.py causes unrelated tests
# to fail because moto deep-copies the state machine (which contains an
# unpicklable RLock) on start_execution. Keep it scoped to this file only.


@pytest.fixture
def stepfunctions():
    with moto.mock_aws(config={"stepfunctions": {"execute_state_machine": True}}):
        yield get_client("stepfunctions", region=MOCK_REGION)


# ---------------------------------------------------------------------------
# Section A: MigrationRecord unit tests (no AWS, no fixtures)
# ---------------------------------------------------------------------------


def _make_item(**overrides):
    item = {
        "collections_workflow": "sar-test-panda_test",
        "itemids": "completed-0",
        "state_updated": "SUCCEEDED_2026-04-07T12:00:00+00:00",
        "executions": [
            "arn:aws:states:us-east-1:123456789012:execution:wf:exec-id",
        ],
        "updated": "2026-04-07T12:00:00+00:00",
    }
    item.update(overrides)
    return item


def test_record_basic_fields():
    item = _make_item()
    rec = MigrationRecord(item)
    assert rec.payload_id == "sar-test-panda/workflow-test/completed-0"
    assert rec.key == {
        "collections_workflow": "sar-test-panda_test",
        "itemids": "completed-0",
    }
    assert rec.original_state == "SUCCEEDED"
    assert rec.executions == [
        "arn:aws:states:us-east-1:123456789012:execution:wf:exec-id",
    ]
    assert (
        rec.last_execution_arn
        == "arn:aws:states:us-east-1:123456789012:execution:wf:exec-id"
    )
    assert rec.execution_id == "exec-id"


def test_record_missing_state_updated():
    item = _make_item()
    item["state_updated"] = ""
    rec = MigrationRecord(item)
    assert rec.state_updated == ""
    assert rec.original_state == ""


def test_record_missing_executions():
    item = _make_item()
    item["executions"] = []
    rec = MigrationRecord(item)
    assert rec.executions == []
    assert rec.last_execution_arn is None
    assert rec.execution_id is None


def test_record_completed_no_underscore():
    item = _make_item(state_updated="COMPLETED")
    rec = MigrationRecord(item)
    assert rec.original_state == "COMPLETED"


def test_record_updated_dt_iso_with_tz():
    item = _make_item(updated="2026-04-07T12:00:00+00:00")
    rec = MigrationRecord(item)
    expected = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
    assert rec.updated_dt == expected


def test_record_updated_dt_naive_iso():
    item = _make_item(updated="2026-04-07T12:00:00")
    rec = MigrationRecord(item)
    assert rec.updated_dt == datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)


def test_record_updated_dt_invalid_string():
    item = _make_item(updated="not-a-date")
    rec = MigrationRecord(item)
    assert rec.updated_dt is None


def test_record_updated_dt_missing():
    item = _make_item()
    del item["updated"]
    rec = MigrationRecord(item)
    assert rec.updated_dt is None


def test_record_state_timestamp_present():
    rec = MigrationRecord(_make_item())
    assert rec.state_timestamp == "2026-04-07T12:00:00+00:00"


def test_record_state_timestamp_no_underscore():
    rec = MigrationRecord(_make_item(state_updated="COMPLETED"))
    assert rec.state_timestamp == ""


def test_record_state_timestamp_empty():
    rec = MigrationRecord(_make_item(state_updated=""))
    assert rec.state_timestamp == ""


def test_record_already_migrated_true():
    rec = MigrationRecord(_make_item(claimed_at="2026-04-07T12:00:00+00:00"))
    assert rec.already_migrated is True


def test_record_already_migrated_false():
    rec = MigrationRecord(_make_item())
    assert rec.already_migrated is False


# ---------------------------------------------------------------------------
# DbUpdatePlan unit tests
# ---------------------------------------------------------------------------


def test_db_update_plan_expression_set_only():
    plan = DbUpdatePlan(
        key={"k": "v"},
        set_parts=("a = :a", "b = :b"),
        remove_parts=(),
        attr_values={":a": 1, ":b": 2},
    )
    assert plan.expression == "SET a = :a, b = :b"
    assert plan.is_noop() is False


def test_db_update_plan_expression_remove_only():
    plan = DbUpdatePlan(
        key={"k": "v"},
        set_parts=(),
        remove_parts=("x", "y"),
        attr_values={},
    )
    assert plan.expression == "REMOVE x, y"
    assert plan.is_noop() is False


def test_db_update_plan_expression_set_and_remove():
    plan = DbUpdatePlan(
        key={"k": "v"},
        set_parts=("a = :a",),
        remove_parts=("x",),
        attr_values={":a": 1},
    )
    assert plan.expression == "SET a = :a REMOVE x"
    assert plan.is_noop() is False


def test_db_update_plan_is_noop():
    plan = DbUpdatePlan(
        key={"k": "v"},
        set_parts=(),
        remove_parts=(),
        attr_values={},
    )
    assert plan.is_noop() is True
    assert plan.expression == ""


def test_db_update_plan_to_update_item_kwargs_with_attr_values():
    plan = DbUpdatePlan(
        key={"collections_workflow": "cw", "itemids": "i"},
        set_parts=("a = :a",),
        remove_parts=("x",),
        attr_values={":a": 1},
    )
    assert plan.to_update_item_kwargs() == {
        "Key": {"collections_workflow": "cw", "itemids": "i"},
        "UpdateExpression": "SET a = :a REMOVE x",
        "ExpressionAttributeValues": {":a": 1},
    }


def test_db_update_plan_to_update_item_kwargs_remove_only():
    """REMOVE-only plans have no attr_values, so the key is omitted."""
    plan = DbUpdatePlan(
        key={"collections_workflow": "cw", "itemids": "i"},
        set_parts=(),
        remove_parts=("last_error",),
        attr_values={},
    )
    kwargs = plan.to_update_item_kwargs()
    assert kwargs == {
        "Key": {"collections_workflow": "cw", "itemids": "i"},
        "UpdateExpression": "REMOVE last_error",
    }
    assert "ExpressionAttributeValues" not in kwargs


# ---------------------------------------------------------------------------
# MigrationRecord.build_db_update_plan unit tests
# ---------------------------------------------------------------------------


def test_build_plan_completed_renames_to_succeeded():
    rec = MigrationRecord(
        _make_item(
            state_updated="COMPLETED_2026-04-07T12:00:00+00:00",
            created="2026-04-07T11:00:00+00:00",
        ),
    )
    plan = rec.build_db_update_plan()
    assert "state_updated = :su" in plan.set_parts
    assert plan.attr_values[":su"] == "SUCCEEDED_2026-04-07T12:00:00+00:00"
    # Renamed to SUCCEEDED, so outputs are NOT removed
    assert "outputs" not in plan.remove_parts


def test_build_plan_completed_no_timestamp():
    rec = MigrationRecord(_make_item(state_updated="COMPLETED"))
    plan = rec.build_db_update_plan()
    assert plan.attr_values[":su"] == "SUCCEEDED"


def test_build_plan_sets_claimed_at_from_created():
    rec = MigrationRecord(_make_item(created="2026-04-07T11:00:00+00:00"))
    plan = rec.build_db_update_plan()
    assert "claimed_at = :ca" in plan.set_parts
    assert plan.attr_values[":ca"] == "2026-04-07T11:00:00+00:00"


def test_build_plan_skips_claimed_at_when_already_present():
    rec = MigrationRecord(
        _make_item(
            created="2026-04-07T11:00:00+00:00",
            claimed_at="2026-04-07T11:30:00+00:00",
        ),
    )
    plan = rec.build_db_update_plan()
    assert "claimed_at = :ca" not in plan.set_parts
    assert ":ca" not in plan.attr_values


def test_build_plan_removes_last_error_from_non_failed():
    rec = MigrationRecord(_make_item(last_error="oops"))
    plan = rec.build_db_update_plan()
    assert "last_error" in plan.remove_parts


def test_build_plan_keeps_last_error_on_failed():
    rec = MigrationRecord(
        _make_item(
            state_updated="FAILED_2026-04-07T12:00:00+00:00",
            last_error="oops",
        ),
    )
    plan = rec.build_db_update_plan()
    assert "last_error" not in plan.remove_parts


def test_build_plan_removes_outputs_from_non_succeeded():
    rec = MigrationRecord(
        _make_item(
            state_updated="FAILED_2026-04-07T12:00:00+00:00",
            outputs=["s3://x/y"],
        ),
    )
    plan = rec.build_db_update_plan()
    assert "outputs" in plan.remove_parts


def test_build_plan_keeps_outputs_on_succeeded():
    rec = MigrationRecord(_make_item(outputs=["s3://x/y"]))
    plan = rec.build_db_update_plan()
    assert "outputs" not in plan.remove_parts


def test_build_plan_keeps_outputs_after_completed_rename():
    """COMPLETED -> SUCCEEDED rename means outputs should NOT be removed."""
    rec = MigrationRecord(
        _make_item(
            state_updated="COMPLETED_2026-04-07T12:00:00+00:00",
            outputs=["s3://x/y"],
        ),
    )
    plan = rec.build_db_update_plan()
    assert "outputs" not in plan.remove_parts


def test_build_plan_noop_when_nothing_to_change():
    """A SUCCEEDED record with claimed_at and no last_error/outputs is a no-op."""
    rec = MigrationRecord(
        _make_item(claimed_at="2026-04-07T11:30:00+00:00"),
    )
    plan = rec.build_db_update_plan()
    assert plan.is_noop() is True


def test_build_plan_does_not_mutate_record():
    item = _make_item(
        state_updated="COMPLETED_2026-04-07T12:00:00+00:00",
        created="2026-04-07T11:00:00+00:00",
        last_error="oops",
    )
    rec = MigrationRecord(item)
    rec.build_db_update_plan()
    # original_state remains COMPLETED — the rename is in the plan, not on rec
    assert rec.original_state == "COMPLETED"
    assert rec.state_updated == "COMPLETED_2026-04-07T12:00:00+00:00"
    # item itself is untouched
    assert item["state_updated"] == "COMPLETED_2026-04-07T12:00:00+00:00"
    assert "claimed_at" not in item


def test_build_plan_key_matches_record_key():
    rec = MigrationRecord(_make_item(created="2026-04-07T11:00:00+00:00"))
    plan = rec.build_db_update_plan()
    assert plan.key == rec.key


# ---------------------------------------------------------------------------
# Section B: Scenario-driven integration tests
# ---------------------------------------------------------------------------
#
# Each integration test case is a MigrationScenario. The runner seeds the
# declared records, instantiates Migrator directly (no CLI), runs it, and
# checks counters + DynamoDB state + S3 state against the declared
# expectations. CLI wiring is covered by a single smoke test at the end.


# ---- time anchors ---------------------------------------------------------


_NOW = datetime.now(UTC)
RECENT_ISO = (_NOW - timedelta(days=1)).isoformat()
OLDER_ISO = (_NOW - timedelta(days=2)).isoformat()
VERY_OLD_ISO = (_NOW - timedelta(days=100)).isoformat()


# ---- scenario dataclasses -------------------------------------------------


# Sentinel for RecordSpec.executions that the seeder swaps for a real moto
# execution arn produced by the st_func_execution_arn fixture.
REAL_ARN = "<<REAL_ARN>>"


@dataclass(frozen=True)
class RecordSpec:
    label: str
    payload_id: str
    state_updated: str
    created: str | None = None
    updated: str | None = None
    claimed_at: str | None = None
    executions: tuple[str, ...] = ()
    outputs: tuple[str, ...] | None = None
    last_error: str | None = None
    seed_input_body: bytes | None = None


@dataclass(frozen=True)
class DBExpectation:
    state_updated_starts_with: str | None = None
    state_updated_equals: str | None = None
    has_keys: tuple[str, ...] = ()
    missing_keys: tuple[str, ...] = ()
    field_equals: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class S3Expectation:
    label: str
    kind: Literal["input", "output"]
    present: bool
    body_equals: bytes | None = None
    body_json_equals: dict | None = None


@dataclass(frozen=True)
class MigrationScenario:
    id: str
    records: tuple[RecordSpec, ...]
    since_days: int = 90
    dry_run: bool = False
    expected_counts: dict[str, int] = field(default_factory=dict)
    expected_db: dict[str, DBExpectation] = field(default_factory=dict)
    expected_s3: tuple[S3Expectation, ...] = ()
    apply_mocks: Callable[[MockerFixture, dict[str, RecordSpec]], None] | None = None
    assert_bucket_unchanged: bool = False
    assert_table_unchanged: bool = False


# ---- seed helpers ---------------------------------------------------------


def _default_input_body(payload_id: str) -> bytes:
    return json.dumps({"payload_id": payload_id, "v": "input"}).encode()


def _seed_record(dynamo, *, payload_id, state_updated, **fields):
    key = StateDB.payload_id_to_key(payload_id)
    item = {
        "collections_workflow": key["collections_workflow"],
        "itemids": key["itemids"],
        "state_updated": state_updated,
        **fields,
    }
    boto3.resource("dynamodb", region_name=MOCK_REGION).Table(TABLE_NAME).put_item(
        Item=item,
    )


def _put_input_payload(s3, payload_id, body):
    s3.put_object(
        Bucket=PAYLOADS_BUCKET,
        Key=f"{payload_id}/input.json",
        Body=body,
        ContentType="application/json",
    )


def _get_dynamo_item(dynamo, payload_id):
    key = StateDB.payload_id_to_key(payload_id)
    resp = dynamo.get_item(
        TableName=TABLE_NAME,
        Key={
            "collections_workflow": {"S": key["collections_workflow"]},
            "itemids": {"S": key["itemids"]},
        },
    )
    return resp.get("Item")


def _s3_object_exists(s3, key) -> bool:
    try:
        s3.head_object(Bucket=PAYLOADS_BUCKET, Key=key)
    except ClientError:
        return False
    return True


def _scan_table(dynamo) -> list[dict]:
    items: list[dict] = []
    kwargs: dict = {}
    while True:
        resp = dynamo.scan(TableName=TABLE_NAME, **kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def _bucket_snapshot(s3) -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    token = None
    while True:
        kw: dict = {"Bucket": PAYLOADS_BUCKET}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for obj in resp.get("Contents", []) or []:
            snap[obj["Key"]] = s3.get_object(
                Bucket=PAYLOADS_BUCKET,
                Key=obj["Key"],
            )["Body"].read()
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return snap


def _resolve_executions(
    executions: tuple[str, ...],
    real_arn: str,
) -> list[str]:
    return [real_arn if arn == REAL_ARN else arn for arn in executions]


def _seed_records(
    specs: tuple[RecordSpec, ...],
    *,
    dynamo,
    s3,
    real_arn: str,
) -> dict[str, dict]:
    """Insert records + seed S3. Returns label -> metadata mapping."""
    meta: dict[str, dict] = {}
    for spec in specs:
        executions = _resolve_executions(spec.executions, real_arn)
        execution_id = (
            StateDB.execution_id_from_arn(executions[-1]) if executions else None
        )

        fields: dict = {}
        if spec.created is not None:
            fields["created"] = spec.created
        if spec.updated is not None:
            fields["updated"] = spec.updated
        if spec.claimed_at is not None:
            fields["claimed_at"] = spec.claimed_at
        if executions:
            fields["executions"] = executions
        if spec.outputs is not None:
            fields["outputs"] = list(spec.outputs)
        if spec.last_error is not None:
            fields["last_error"] = spec.last_error

        _seed_record(
            dynamo,
            payload_id=spec.payload_id,
            state_updated=spec.state_updated,
            **fields,
        )

        if spec.seed_input_body is not None:
            _put_input_payload(s3, spec.payload_id, spec.seed_input_body)

        meta[spec.label] = {
            "payload_id": spec.payload_id,
            "execution_id": execution_id,
        }

    return meta


def _assert_db_expectation(
    dynamo,
    payload_id: str,
    label: str,
    exp: DBExpectation,
) -> None:
    item = _get_dynamo_item(dynamo, payload_id)
    assert item is not None, f"{label}: DynamoDB item missing"

    if exp.state_updated_starts_with is not None:
        actual = item["state_updated"]["S"]
        assert actual.startswith(exp.state_updated_starts_with), (
            f"{label}: state_updated {actual!r} does not start with"
            f" {exp.state_updated_starts_with!r}"
        )
    if exp.state_updated_equals is not None:
        actual = item["state_updated"]["S"]
        assert actual == exp.state_updated_equals, (
            f"{label}: state_updated {actual!r} != {exp.state_updated_equals!r}"
        )
    for key in exp.has_keys:
        assert key in item, f"{label}: expected key {key!r} in item"
    for key in exp.missing_keys:
        assert key not in item, f"{label}: expected key {key!r} absent from item"
    for key, value in exp.field_equals.items():
        actual = item.get(key, {}).get("S")
        assert actual == value, f"{label}: field {key!r}={actual!r} != {value!r}"


def _assert_s3_expectation(
    s3,
    meta: dict[str, dict],
    exp: S3Expectation,
) -> None:
    rec_meta = meta[exp.label]
    payload_id = rec_meta["payload_id"]
    execution_id = rec_meta["execution_id"]
    assert execution_id is not None, (
        f"{exp.label}: S3Expectation requires an execution_id but record has none"
    )
    key = f"cirrus/executions/{payload_id}/{execution_id}/{exp.kind}.json"
    exists = _s3_object_exists(s3, key)
    if exp.present:
        assert exists, f"{exp.label}: expected s3 key {key!r} to exist"
        body = s3.get_object(Bucket=PAYLOADS_BUCKET, Key=key)["Body"].read()
        if exp.body_equals is not None:
            assert body == exp.body_equals, (
                f"{exp.label}: {exp.kind}.json body mismatch"
            )
        if exp.body_json_equals is not None:
            assert json.loads(body) == exp.body_json_equals, (
                f"{exp.label}: {exp.kind}.json json body mismatch"
            )
    else:
        assert not exists, f"{exp.label}: expected s3 key {key!r} to be absent"


# ---- scenario runner ------------------------------------------------------


@pytest.fixture
def run_scenario(
    deployment,
    dynamo,
    s3,
    st_func_execution_arn,
    mocker,
):
    def _run(scenario: MigrationScenario):
        meta = _seed_records(
            scenario.records,
            dynamo=dynamo,
            s3=s3,
            real_arn=st_func_execution_arn,
        )

        table_snapshot = (
            _scan_table(dynamo) if scenario.assert_table_unchanged else None
        )
        bucket_before = (
            _bucket_snapshot(s3) if scenario.assert_bucket_unchanged else None
        )

        spec_by_label = {spec.label: spec for spec in scenario.records}
        if scenario.apply_mocks is not None:
            scenario.apply_mocks(mocker, spec_by_label)

        migrator = Migrator(
            session=deployment.session,
            table_name=deployment.environment["CIRRUS_STATE_DB"],
            bucket_name=deployment.environment["CIRRUS_PAYLOAD_BUCKET"],
            since_days=scenario.since_days,
            dry_run=scenario.dry_run,
            output=io.StringIO(),
        )
        migrator.run()

        # Counter assertion: any counter not mentioned in expected_counts must
        # be zero. This makes the declared expectations complete.
        expected_counts = dict.fromkeys(migrator.counts, 0)
        expected_counts.update(scenario.expected_counts)
        assert migrator.counts == expected_counts, (
            f"scenario {scenario.id}: counts mismatch\n"
            f"  expected: {expected_counts}\n"
            f"  actual:   {dict(migrator.counts)}"
        )

        for label, db_exp in scenario.expected_db.items():
            _assert_db_expectation(
                dynamo,
                spec_by_label[label].payload_id,
                label,
                db_exp,
            )

        for s3_exp in scenario.expected_s3:
            _assert_s3_expectation(s3, meta, s3_exp)

        if table_snapshot is not None:
            assert _scan_table(dynamo) == table_snapshot, (
                f"scenario {scenario.id}: table mutated unexpectedly"
            )
        if bucket_before is not None:
            assert _bucket_snapshot(s3) == bucket_before, (
                f"scenario {scenario.id}: bucket mutated unexpectedly"
            )

        return migrator, meta

    return _run


# ---- record builders ------------------------------------------------------
#
# Each builder returns a RecordSpec for one "kind" of record under test.
# Builders are cheap data constructors; keep them close to their shared
# expectation tables below.


def _legacy_completed_spec() -> RecordSpec:
    pid = "sar-test-panda/workflow-test/legacy-completed"
    return RecordSpec(
        label="legacy_completed",
        payload_id=pid,
        state_updated=f"COMPLETED_{RECENT_ISO}",
        created=OLDER_ISO,
        updated=RECENT_ISO,
        executions=(REAL_ARN,),
        last_error="stale-pre-migration-error",
        seed_input_body=_default_input_body(pid),
    )


def _legacy_completed_no_ts_spec() -> RecordSpec:
    return RecordSpec(
        label="legacy_completed_no_ts",
        payload_id="sar-test-panda/workflow-test/legacy-completed-no-ts",
        state_updated="COMPLETED",
        created=OLDER_ISO,
    )


def _legacy_completed_old_spec() -> RecordSpec:
    """Legacy COMPLETED record with `updated` outside the default cutoff."""
    pid = "sar-test-panda/workflow-test/legacy-completed-old"
    return RecordSpec(
        label="legacy_completed_old",
        payload_id=pid,
        state_updated=f"COMPLETED_{VERY_OLD_ISO}",
        created=VERY_OLD_ISO,
        updated=VERY_OLD_ISO,
        executions=(REAL_ARN,),
        seed_input_body=_default_input_body(pid),
    )


def _legacy_completed_bad_arn_spec() -> RecordSpec:
    """Legacy COMPLETED record whose execution arn no longer exists in SFN."""
    pid = "sar-test-panda/workflow-test/legacy-completed-bad-arn"
    return RecordSpec(
        label="legacy_completed_bad_arn",
        payload_id=pid,
        state_updated=f"COMPLETED_{RECENT_ISO}",
        created=OLDER_ISO,
        updated=RECENT_ISO,
        executions=(BAD_ARN_VALUE,),
        seed_input_body=_default_input_body(pid),
    )


def _succeeded_recent_spec() -> RecordSpec:
    pid = "sar-test-panda/workflow-test/succeeded-recent"
    return RecordSpec(
        label="succeeded_recent",
        payload_id=pid,
        state_updated=f"SUCCEEDED_{RECENT_ISO}",
        created=OLDER_ISO,
        updated=RECENT_ISO,
        executions=(REAL_ARN,),
        outputs=("s3://other/already-set.json",),
        seed_input_body=_default_input_body(pid),
    )


def _succeeded_old_spec() -> RecordSpec:
    pid = "sar-test-panda/workflow-test/succeeded-old"
    return RecordSpec(
        label="succeeded_old",
        payload_id=pid,
        state_updated=f"SUCCEEDED_{VERY_OLD_ISO}",
        created=VERY_OLD_ISO,
        updated=VERY_OLD_ISO,
        executions=(REAL_ARN,),
        outputs=("s3://other/already-set-old.json",),
        seed_input_body=_default_input_body(pid),
    )


def _failed_with_outputs_spec() -> RecordSpec:
    pid = "sar-test-panda/workflow-test/failed-with-outputs"
    return RecordSpec(
        label="failed_with_outputs",
        payload_id=pid,
        state_updated=f"FAILED_{RECENT_ISO}",
        created=OLDER_ISO,
        updated=RECENT_ISO,
        executions=(REAL_ARN,),
        outputs=("s3://stale/leftover.json",),
        last_error="boom",
        seed_input_body=_default_input_body(pid),
    )


def _succeeded_missing_input_spec() -> RecordSpec:
    """SUCCEEDED record whose input.json has already been deleted from S3."""
    return RecordSpec(
        label="succeeded_missing_input",
        payload_id="sar-test-panda/workflow-test/succeeded-missing-input",
        state_updated=f"SUCCEEDED_{RECENT_ISO}",
        created=OLDER_ISO,
        updated=RECENT_ISO,
        executions=(REAL_ARN,),
    )


def _no_executions_spec() -> RecordSpec:
    return RecordSpec(
        label="no_executions",
        payload_id="sar-test-panda/workflow-test/no-executions",
        state_updated=f"SUCCEEDED_{RECENT_ISO}",
        created=OLDER_ISO,
        updated=RECENT_ISO,
    )


def _already_migrated_spec() -> RecordSpec:
    """Record with claimed_at set: must be short-circuited by the guard."""
    pid = "sar-test-panda/workflow-test/already-migrated"
    return RecordSpec(
        label="already_migrated",
        payload_id=pid,
        state_updated=f"SUCCEEDED_{RECENT_ISO}",
        created=OLDER_ISO,
        updated=RECENT_ISO,
        claimed_at=OLDER_ISO,
        executions=(REAL_ARN,),
        seed_input_body=_default_input_body(pid),
    )


def _all_specs() -> tuple[RecordSpec, ...]:
    return (
        _legacy_completed_spec(),
        _legacy_completed_no_ts_spec(),
        _legacy_completed_bad_arn_spec(),
        _succeeded_recent_spec(),
        _succeeded_old_spec(),
        _failed_with_outputs_spec(),
        _succeeded_missing_input_spec(),
        _no_executions_spec(),
    )


# ---- full-run expectations (shared by full_run / idempotent scenarios) ----
#
# Per-record reasoning:
#   legacy_completed         COMPLETED+recent+arn+input: A rename/claim/drop
#                            last_error, B copies, C fetches.
#   legacy_completed_no_ts   COMPLETED no exec: A rename/claim. B/C skip.
#   legacy_completed_bad_arn COMPLETED+recent+bad arn: A rename/claim, B
#                            copies, C ExecutionDoesNotExist -> skipped++.
#   succeeded_recent         SUCCEEDED+recent+arn+input+outputs: A sets
#                            claimed_at, B copies. C never runs for
#                            SUCCEEDED (new-layout records).
#   succeeded_old            SUCCEEDED outside cutoff: A sets claimed_at,
#                            B copies. C never runs.
#   failed_with_outputs      FAILED+recent+arn+input+outputs+last_error: A
#                            sets claimed_at + removes outputs, B copies.
#                            C skips (not COMPLETED).
#   succeeded_missing_input  SUCCEEDED+recent+arn, no S3 input: A sets
#                            claimed_at, B NoSuchKey -> skipped++. C never
#                            runs for SUCCEEDED.
#   no_executions            SUCCEEDED+recent, no exec: A sets claimed_at.
#                            B/C skip.

_FULL_RUN_COUNTS: dict[str, int] = {
    "processed": 8,
    "db_updated": 8,
    "s3_copied": 5,  # legacy_completed, legacy_completed_bad_arn,
    # succeeded_recent, succeeded_old,
    # failed_with_outputs
    "s3_output_uploaded": 1,  # legacy_completed only
    "skipped": 2,  # legacy_completed_bad_arn (Step C),
    # succeeded_missing_input (Step B)
}


_FULL_RUN_DB_EXPECTATIONS: dict[str, DBExpectation] = {
    "legacy_completed": DBExpectation(
        state_updated_starts_with="SUCCEEDED_",
        has_keys=("claimed_at",),
        missing_keys=("last_error",),
    ),
    "legacy_completed_no_ts": DBExpectation(
        state_updated_equals="SUCCEEDED",
        has_keys=("claimed_at",),
    ),
    "legacy_completed_bad_arn": DBExpectation(
        state_updated_starts_with="SUCCEEDED_",
        has_keys=("claimed_at",),
    ),
    "succeeded_recent": DBExpectation(
        has_keys=("claimed_at", "outputs"),
    ),
    "succeeded_old": DBExpectation(
        has_keys=("claimed_at", "outputs"),
    ),
    "failed_with_outputs": DBExpectation(
        has_keys=("claimed_at",),
        missing_keys=("outputs",),
        field_equals={"last_error": "boom"},
    ),
    "succeeded_missing_input": DBExpectation(
        has_keys=("claimed_at",),
    ),
    "no_executions": DBExpectation(
        has_keys=("claimed_at",),
    ),
}


_FULL_RUN_S3_EXPECTATIONS: tuple[S3Expectation, ...] = (
    # Step B: input copies for every record with executions+input.json.
    S3Expectation(
        label="legacy_completed",
        kind="input",
        present=True,
        body_equals=_default_input_body(
            "sar-test-panda/workflow-test/legacy-completed",
        ),
    ),
    S3Expectation(
        label="legacy_completed_bad_arn",
        kind="input",
        present=True,
    ),
    S3Expectation(
        label="succeeded_recent",
        kind="input",
        present=True,
        body_equals=_default_input_body(
            "sar-test-panda/workflow-test/succeeded-recent",
        ),
    ),
    S3Expectation(
        label="succeeded_old",
        kind="input",
        present=True,
    ),
    S3Expectation(
        label="failed_with_outputs",
        kind="input",
        present=True,
    ),
    # Step C: SFN output uploads. Only legacy_completed produces an output:
    # legacy_completed_bad_arn hits ExecutionDoesNotExist; SUCCEEDED records
    # no longer trigger Step C under the new layout. The Pass state in
    # tests/conftest.py:workflow echoes input to output.
    S3Expectation(
        label="legacy_completed",
        kind="output",
        present=True,
        body_json_equals={"hello": "cirrus"},
    ),
    S3Expectation(
        label="legacy_completed_bad_arn",
        kind="output",
        present=False,
    ),
    S3Expectation(
        label="succeeded_recent",
        kind="output",
        present=False,
    ),
    S3Expectation(
        label="succeeded_old",
        kind="output",
        present=False,
    ),
)


# ---- shared mocks ---------------------------------------------------------


def _db_error_mocks(
    mocker: MockerFixture,
    spec_by_label: dict[str, RecordSpec],
) -> None:
    """Make update_db_record fail for failed_with_outputs only."""
    target_payload_id = spec_by_label["failed_with_outputs"].payload_id
    original = Migrator.update_db_record

    def side_effect(self, rec):
        if rec.payload_id == target_payload_id:
            self.counts["db_errors"] += 1
            return False
        return original(self, rec)

    mocker.patch.object(
        Migrator,
        "update_db_record",
        autospec=True,
        side_effect=side_effect,
    )


# ---- scenario table -------------------------------------------------------


SCENARIOS: tuple[MigrationScenario, ...] = (
    MigrationScenario(
        id="legacy_completed",
        records=(_legacy_completed_spec(),),
        expected_counts={
            "processed": 1,
            "db_updated": 1,
            "s3_copied": 1,
            "s3_output_uploaded": 1,
        },
        expected_db={
            "legacy_completed": DBExpectation(
                state_updated_starts_with="SUCCEEDED_",
                has_keys=("claimed_at",),
                missing_keys=("last_error",),
            ),
        },
        expected_s3=(
            S3Expectation(
                label="legacy_completed",
                kind="input",
                present=True,
                body_equals=_default_input_body(
                    "sar-test-panda/workflow-test/legacy-completed",
                ),
            ),
            S3Expectation(
                label="legacy_completed",
                kind="output",
                present=True,
                body_json_equals={"hello": "cirrus"},
            ),
        ),
    ),
    MigrationScenario(
        id="legacy_completed_no_ts",
        records=(_legacy_completed_no_ts_spec(),),
        expected_counts={"processed": 1, "db_updated": 1},
        expected_db={
            "legacy_completed_no_ts": DBExpectation(
                state_updated_equals="SUCCEEDED",
                has_keys=("claimed_at",),
            ),
        },
    ),
    MigrationScenario(
        id="legacy_completed_bad_arn_step_c_skipped",
        records=(_legacy_completed_bad_arn_spec(),),
        # Step B copies input; Step C hits ExecutionDoesNotExist -> skipped.
        expected_counts={
            "processed": 1,
            "db_updated": 1,
            "s3_copied": 1,
            "skipped": 1,
        },
        expected_db={
            "legacy_completed_bad_arn": DBExpectation(
                state_updated_starts_with="SUCCEEDED_",
                has_keys=("claimed_at",),
            ),
        },
        expected_s3=(
            S3Expectation(
                label="legacy_completed_bad_arn",
                kind="input",
                present=True,
            ),
            S3Expectation(
                label="legacy_completed_bad_arn",
                kind="output",
                present=False,
            ),
        ),
    ),
    MigrationScenario(
        id="succeeded_recent_step_c_never_runs",
        records=(_succeeded_recent_spec(),),
        # SUCCEEDED records were written under the new layout: Step C never
        # runs. Step A still writes claimed_at, Step B still copies input.
        expected_counts={
            "processed": 1,
            "db_updated": 1,
            "s3_copied": 1,
        },
        expected_db={
            "succeeded_recent": DBExpectation(
                state_updated_starts_with="SUCCEEDED_",
                has_keys=("claimed_at", "outputs"),
            ),
        },
        expected_s3=(
            S3Expectation(
                label="succeeded_recent",
                kind="input",
                present=True,
            ),
            S3Expectation(
                label="succeeded_recent",
                kind="output",
                present=False,
            ),
        ),
    ),
    MigrationScenario(
        id="succeeded_old_outside_cutoff",
        records=(_succeeded_old_spec(),),
        expected_counts={
            "processed": 1,
            "db_updated": 1,
            "s3_copied": 1,
        },
        expected_s3=(
            S3Expectation(
                label="succeeded_old",
                kind="input",
                present=True,
            ),
            S3Expectation(
                label="succeeded_old",
                kind="output",
                present=False,
            ),
        ),
    ),
    MigrationScenario(
        id="failed_with_outputs",
        records=(_failed_with_outputs_spec(),),
        expected_counts={
            "processed": 1,
            "db_updated": 1,
            "s3_copied": 1,
        },
        expected_db={
            "failed_with_outputs": DBExpectation(
                state_updated_starts_with="FAILED_",
                has_keys=("claimed_at",),
                missing_keys=("outputs",),
                field_equals={"last_error": "boom"},
            ),
        },
        expected_s3=(
            S3Expectation(
                label="failed_with_outputs",
                kind="input",
                present=True,
            ),
            S3Expectation(
                label="failed_with_outputs",
                kind="output",
                present=False,
            ),
        ),
    ),
    MigrationScenario(
        id="succeeded_missing_input_step_b_noSuchKey",
        records=(_succeeded_missing_input_spec(),),
        # B hits NoSuchKey and increments `skipped`. C never runs because the
        # record is SUCCEEDED. A still updates the DB.
        expected_counts={
            "processed": 1,
            "db_updated": 1,
            "skipped": 1,
        },
        expected_db={
            "succeeded_missing_input": DBExpectation(
                has_keys=("claimed_at",),
            ),
        },
    ),
    MigrationScenario(
        id="no_executions",
        records=(_no_executions_spec(),),
        expected_counts={"processed": 1, "db_updated": 1},
        expected_db={
            "no_executions": DBExpectation(
                has_keys=("claimed_at",),
            ),
        },
    ),
    MigrationScenario(
        id="already_migrated_record_skipped",
        records=(_already_migrated_spec(),),
        # Idempotency guard fires: the record is counted as processed
        # but no other counter increments and table + bucket are untouched.
        expected_counts={"processed": 1},
        assert_table_unchanged=True,
        assert_bucket_unchanged=True,
    ),
    MigrationScenario(
        id="dry_run_all_records",
        records=_all_specs(),
        dry_run=True,
        # Dry run does not probe S3 or describe_execution, so counters are
        # optimistic: every record with executions contributes to s3_copied
        # (regardless of whether input exists), and every COMPLETED+recent+
        # executions record contributes to s3_output_uploaded (regardless of
        # arn validity). skipped stays 0 because the skip paths are never
        # reached.
        expected_counts={
            "processed": 8,
            "db_updated": 8,
            "s3_copied": 6,  # everything with executions
            "s3_output_uploaded": 2,  # legacy_completed + legacy_completed_bad_arn
        },
        assert_table_unchanged=True,
        assert_bucket_unchanged=True,
    ),
    MigrationScenario(
        id="full_run_all_records",
        records=_all_specs(),
        expected_counts=_FULL_RUN_COUNTS,
        expected_db=_FULL_RUN_DB_EXPECTATIONS,
        expected_s3=_FULL_RUN_S3_EXPECTATIONS,
    ),
    MigrationScenario(
        id="since_days_30_cutoff_on_legacy_completed",
        records=(_legacy_completed_spec(), _legacy_completed_old_spec()),
        since_days=30,
        # Both records: Step A renames, Step B copies input. Only the recent
        # one triggers Step C. The old one's `updated` is outside the 30-day
        # cutoff window.
        expected_counts={
            "processed": 2,
            "db_updated": 2,
            "s3_copied": 2,
            "s3_output_uploaded": 1,
        },
        expected_s3=(
            S3Expectation(
                label="legacy_completed",
                kind="output",
                present=True,
                body_json_equals={"hello": "cirrus"},
            ),
            S3Expectation(
                label="legacy_completed_old",
                kind="output",
                present=False,
            ),
        ),
    ),
    MigrationScenario(
        id="db_error_continues_processing_other_records",
        records=_all_specs(),
        apply_mocks=_db_error_mocks,
        # processed counts all 8 scanned records. The targeted record's Step A
        # fails so it does not contribute to db_updated (7 of 8). Step B still
        # ran for failed_with_outputs (B is before A), so s3_copied is 5.
        expected_counts={
            "processed": 8,
            "db_updated": 7,
            "s3_copied": 5,
            "s3_output_uploaded": 1,
            "skipped": 2,
            "db_errors": 1,
        },
        expected_db={
            "failed_with_outputs": DBExpectation(
                state_updated_starts_with="FAILED_",
                has_keys=("outputs",),
                missing_keys=("claimed_at",),
                field_equals={"last_error": "boom"},
            ),
        },
    ),
)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_migrate(scenario, run_scenario):
    run_scenario(scenario)


# ---- idempotency: explicit because it runs Migrator twice -----------------


def test_migrate_idempotent(run_scenario, deployment, dynamo, s3):
    scenario = MigrationScenario(
        id="idempotent_first_pass",
        records=_all_specs(),
        expected_counts=_FULL_RUN_COUNTS,
        expected_db=_FULL_RUN_DB_EXPECTATIONS,
        expected_s3=_FULL_RUN_S3_EXPECTATIONS,
    )
    run_scenario(scenario)

    table_after_first = _scan_table(dynamo)
    bucket_after_first = _bucket_snapshot(s3)

    # Second run: claimed_at is now set on every record, so the guard
    # short-circuits every record and nothing mutates.
    migrator2 = Migrator(
        session=deployment.session,
        table_name=deployment.environment["CIRRUS_STATE_DB"],
        bucket_name=deployment.environment["CIRRUS_PAYLOAD_BUCKET"],
        since_days=90,
        dry_run=False,
        output=io.StringIO(),
    )
    migrator2.run()

    # Second run scans all 8 records but the idempotency guard fires on each,
    # so processed counts them but no other counter increments.
    expected_second_run = dict.fromkeys(migrator2.counts, 0)
    expected_second_run["processed"] = 8
    assert migrator2.counts == expected_second_run
    assert _scan_table(dynamo) == table_after_first
    assert _bucket_snapshot(s3) == bucket_after_first


# ---------------------------------------------------------------------------
# Section C: CLI smoke test (plumbing only)
# ---------------------------------------------------------------------------


def test_cli_migrate_smoke(
    deployment,
    dynamo,
    s3,
    st_func_execution_arn,
    put_parameters,
):
    """Verify the `manage migrate` CLI command is wired up end-to-end.

    Behavioural coverage lives in Section B; this test only asserts the
    command runs, exits 0, and writes the summary block to stderr.
    """
    _seed_records(
        (_legacy_completed_spec(),),
        dynamo=dynamo,
        s3=s3,
        real_arn=st_func_execution_arn,
    )
    result = deployment("migrate --since-days 90")
    assert result.exit_code == 0, result.stderr
    assert "Migration complete." in result.stderr
    assert "Records processed:" in result.stderr
