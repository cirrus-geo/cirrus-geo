import pytest

from cirrus.lib.errors import UndefinedPayloadBucketError
from cirrus.lib.payload_bucket import (
    INPUT_KEY,
    OUTPUT_KEY,
    PREFIX_BATCH,
    PREFIX_EXECS,
    PREFIX_INVALID,
    PREFIX_OVERSIZED,
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


def test_name_from_explicit_bucket():
    pb = PayloadBucket(bucket_name="my-bucket")
    assert pb.name() == "my-bucket"


def test_name_from_env_var(monkeypatch):
    monkeypatch.setenv("CIRRUS_PAYLOAD_BUCKET", "env-bucket")
    pb = PayloadBucket()
    assert pb.name() == "env-bucket"


def test_name_raises_when_undefined(monkeypatch):
    monkeypatch.delenv("CIRRUS_PAYLOAD_BUCKET", raising=False)
    pb = PayloadBucket()
    with pytest.raises(UndefinedPayloadBucketError):
        pb.name()


def test_upload_oversize_payload(payloads, payload):
    pb = PayloadBucket(bucket_name=payloads)
    url = pb.upload_oversize_payload(payload)
    assert url.startswith(f"s3://{payloads}/{PREFIX_OVERSIZED}/")
    assert url.endswith(".json")


def test_upload_batch_payload(payloads, payload):
    pb = PayloadBucket(bucket_name=payloads)
    url = pb.upload_batch_payload(payload)
    assert url.startswith(f"s3://{payloads}/{PREFIX_BATCH}/{PAYLOAD_ID}/")
    assert url.endswith(".json")


def test_upload_batch_payload_with_existing_url(payloads, payload):
    pb = PayloadBucket(bucket_name=payloads)
    payload["url"] = "s3://other-bucket/some/key.json"
    url = pb.upload_batch_payload(payload)
    # copy_from_url=False means if "url" is present, just return it
    assert url == "s3://other-bucket/some/key.json"


def test_upload_invalid_payload(payloads, payload):
    pb = PayloadBucket(bucket_name=payloads)
    url = pb.upload_invalid_payload(payload)
    assert url.startswith(f"s3://{payloads}/{PREFIX_INVALID}/")
    assert url.endswith(".json")


def test_exec_payload_prefix():
    prefix = PayloadBucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert prefix == f"{PREFIX_EXECS}/{PAYLOAD_ID}/{EXECUTION_ID}"


def test_upload_input_payload(payloads, payload):
    pb = PayloadBucket(bucket_name=payloads)
    url = pb.upload_input_payload(payload, PAYLOAD_ID, EXECUTION_ID)
    expected_prefix = PayloadBucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert url == f"s3://{payloads}/{expected_prefix}/{INPUT_KEY}"


def test_upload_output_payload(payloads, payload):
    pb = PayloadBucket(bucket_name=payloads)
    url = pb.upload_output_payload(payload, PAYLOAD_ID, EXECUTION_ID)
    expected_prefix = PayloadBucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert url == f"s3://{payloads}/{expected_prefix}/{OUTPUT_KEY}"


def test_get_input_payload_url(payloads):
    pb = PayloadBucket(bucket_name=payloads)
    url = pb.get_input_payload_url(PAYLOAD_ID, EXECUTION_ID)
    expected_prefix = PayloadBucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert url == f"s3://{payloads}/{expected_prefix}/{INPUT_KEY}"


def test_get_output_payload_url(payloads):
    pb = PayloadBucket(bucket_name=payloads)
    url = pb.get_output_payload_url(PAYLOAD_ID, EXECUTION_ID)
    expected_prefix = PayloadBucket.exec_payload_prefix(PAYLOAD_ID, EXECUTION_ID)
    assert url == f"s3://{payloads}/{expected_prefix}/{OUTPUT_KEY}"


def test_parse_url():
    url = "s3://my-bucket/some/prefix/file.json"
    bucket, key = PayloadBucket.parse_url(url)
    assert bucket == "my-bucket"
    assert key == "some/prefix/file.json"
