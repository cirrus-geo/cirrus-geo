import pytest

from cirrus.lib.errors import UndefinedPayloadBucketError
from cirrus.lib.payload_bucket import (
    DEFAULT_ROOT_PREFIX,
    INPUT_KEY,
    OUTPUT_KEY,
    PayloadBucket,
)

PAYLOAD_ID = "test-collection/workflow-test-workflow/test-item"
EXECUTION_ID = "abc-123-def"


@pytest.fixture
def payload():
    return {
        "id": PAYLOAD_ID,
        "type": "FeatureCollection",
        "features": [],
        "process": [{"workflow": "test-workflow"}],
    }


def test_bucket_name_from_explicit_arg():
    pb = PayloadBucket(bucket_name="my-bucket")
    assert pb.bucket_name == "my-bucket"


def test_bucket_name_from_env_var(monkeypatch):
    monkeypatch.setenv("CIRRUS_PAYLOAD_BUCKET", "env-bucket")
    pb = PayloadBucket.from_env()
    assert pb.bucket_name == "env-bucket"


def test_bucket_name_raises_when_undefined(monkeypatch):
    monkeypatch.delenv("CIRRUS_PAYLOAD_BUCKET", raising=False)
    with pytest.raises(UndefinedPayloadBucketError):
        PayloadBucket.from_env()


def test_default_root_prefix():
    pb = PayloadBucket(bucket_name="b")
    assert pb.root_prefix == DEFAULT_ROOT_PREFIX
    assert pb.prefix_tmp == "cirrus/tmp"
    assert pb.prefix_batch == "cirrus/tmp/batch"
    assert pb.prefix_invalid == "cirrus/tmp/invalid"
    assert pb.prefix_oversized == "cirrus/tmp/oversized"
    assert pb.prefix_execs == "cirrus/executions"


def test_root_prefix_from_env_var(monkeypatch):
    monkeypatch.setenv("CIRRUS_PAYLOAD_BUCKET", "b")
    monkeypatch.setenv("CIRRUS_PAYLOAD_ROOT_PREFIX", "custom")
    pb = PayloadBucket.from_env()
    assert pb.root_prefix == "custom"
    assert pb.prefix_tmp == "custom/tmp"
    assert pb.prefix_batch == "custom/tmp/batch"
    assert pb.prefix_invalid == "custom/tmp/invalid"
    assert pb.prefix_oversized == "custom/tmp/oversized"
    assert pb.prefix_execs == "custom/executions"


def test_explicit_root_prefix():
    pb = PayloadBucket(bucket_name="b", root_prefix="myprefix")
    assert pb.root_prefix == "myprefix"
    assert pb.prefix_tmp == "myprefix/tmp"
    assert pb.prefix_execs == "myprefix/executions"


def test_explicit_root_prefix_overrides_default():
    pb = PayloadBucket("b", root_prefix="explicit")
    assert pb.root_prefix == "explicit"


def test_upload_oversize_payload(payload_bucket, payload):
    url = payload_bucket.upload_oversize_payload(payload)
    assert url.startswith(
        f"s3://{payload_bucket.bucket_name}/{payload_bucket.prefix_oversized}/",
    )
    assert url.endswith(".json")


def test_upload_oversize_payload_custom_prefix(payload_bucket, payload):
    pb = PayloadBucket(payload_bucket.bucket_name, root_prefix="custom")
    url = pb.upload_oversize_payload(payload)
    assert url.startswith(f"s3://{payload_bucket.bucket_name}/custom/tmp/oversized/")
    assert url.endswith(".json")


def test_upload_batch_payload(payload_bucket, payload):
    url = payload_bucket.upload_batch_payload(payload)
    assert url.startswith(
        f"s3://{payload_bucket.bucket_name}/{payload_bucket.prefix_batch}/{PAYLOAD_ID}/",
    )
    assert url.endswith(".json")


def test_upload_batch_payload_with_existing_url(payload_bucket, payload):
    payload["url"] = "s3://other-bucket/some/key.json"
    url = payload_bucket.upload_batch_payload(payload)
    # copy_from_url=False means if "url" is present, just return it
    assert url == "s3://other-bucket/some/key.json"


def test_upload_invalid_payload(payload_bucket, payload):
    url = payload_bucket.upload_invalid_payload(payload)
    assert url.startswith(
        f"s3://{payload_bucket.bucket_name}/{payload_bucket.prefix_invalid}/",
    )
    assert url.endswith(".json")


def test_exec_payload_prefix():
    pb = PayloadBucket(bucket_name="b")
    prefix = pb.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert prefix == f"{pb.prefix_execs}/{PAYLOAD_ID}/{EXECUTION_ID}"


def test_exec_payload_prefix_custom_root():
    pb = PayloadBucket(bucket_name="b", root_prefix="custom")
    prefix = pb.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert prefix == f"custom/executions/{PAYLOAD_ID}/{EXECUTION_ID}"


def test_upload_input_payload(payload_bucket, payload):
    url = payload_bucket.upload_input_payload(payload, PAYLOAD_ID, EXECUTION_ID)
    expected_prefix = payload_bucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert url == f"s3://{payload_bucket.bucket_name}/{expected_prefix}/{INPUT_KEY}"


def test_upload_output_payload(payload_bucket, payload):
    url = payload_bucket.upload_output_payload(payload, PAYLOAD_ID, EXECUTION_ID)
    expected_prefix = payload_bucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert url == f"s3://{payload_bucket.bucket_name}/{expected_prefix}/{OUTPUT_KEY}"


def test_get_input_payload_url(payload_bucket):
    url = payload_bucket.get_input_payload_url(PAYLOAD_ID, EXECUTION_ID)
    expected_prefix = payload_bucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert url == f"s3://{payload_bucket.bucket_name}/{expected_prefix}/{INPUT_KEY}"


def test_get_output_payload_url(payload_bucket):
    url = payload_bucket.get_output_payload_url(PAYLOAD_ID, EXECUTION_ID)
    expected_prefix = payload_bucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert url == f"s3://{payload_bucket.bucket_name}/{expected_prefix}/{OUTPUT_KEY}"


def test_parse_url():
    url = "s3://my-bucket/some/prefix/file.json"
    bucket, key = PayloadBucket.parse_url(url)
    assert bucket == "my-bucket"
    assert key == "some/prefix/file.json"
