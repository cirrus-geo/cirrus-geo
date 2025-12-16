from cirrus.lib.logging import get_task_logger


def test_get_task_logger_filters_payload_keys():
    """Test that only id and stac_version from payload are included in log extra."""
    payload = {
        "id": "test-collection/workflow-test/test-item",
        "stac_version": "1.0.0",
        "features": [{"type": "Feature"}],
        "process": [{"workflow": "test"}],
    }

    logger = get_task_logger("test.logger", payload=payload)

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" in processed_kwargs
    assert processed_kwargs["extra"]["id"] == "test-collection/workflow-test/test-item"
    assert processed_kwargs["extra"]["stac_version"] == "1.0.0"
    assert "features" not in processed_kwargs["extra"]
    assert "process" not in processed_kwargs["extra"]


def test_get_task_logger_with_aws_request_id():
    """Test that aws_request_id is added to log extra when provided."""
    payload = {
        "id": "test-collection/workflow-test/test-item",
        "stac_version": "1.0.0",
    }
    request_id = "abc123-def456-ghi789"

    logger = get_task_logger(
        "test.logger",
        payload=payload,
        aws_request_id=request_id,
    )

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" in processed_kwargs
    assert processed_kwargs["extra"]["id"] == "test-collection/workflow-test/test-item"
    assert processed_kwargs["extra"]["stac_version"] == "1.0.0"
    assert processed_kwargs["extra"]["aws_request_id"] == request_id


def test_get_task_logger_without_aws_request_id():
    """Test that aws_request_id is not in extra when not provided."""
    payload = {
        "id": "test-collection/workflow-test/test-item",
        "stac_version": "1.0.0",
    }

    logger = get_task_logger("test.logger", payload=payload)

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" in processed_kwargs
    assert "aws_request_id" not in processed_kwargs["extra"]


def test_get_task_logger_with_empty_payload():
    """Test that logger works with empty payload."""
    logger = get_task_logger("test.logger", payload={})

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" not in processed_kwargs or processed_kwargs["extra"] == {}


def test_get_task_logger_with_empty_payload_and_aws_request_id():
    """Test that aws_request_id is added even with empty payload."""
    request_id = "abc123-def456-ghi789"

    logger = get_task_logger(
        "test.logger",
        payload={},
        aws_request_id=request_id,
    )

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" in processed_kwargs
    assert processed_kwargs["extra"]["aws_request_id"] == request_id


def test_get_task_logger_missing_stac_version():
    """Test that logger handles payload missing stac_version."""
    payload = {
        "id": "test-collection/workflow-test/test-item",
    }

    logger = get_task_logger("test.logger", payload=payload)

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" in processed_kwargs
    assert processed_kwargs["extra"]["id"] == "test-collection/workflow-test/test-item"
    assert "stac_version" not in processed_kwargs["extra"]
