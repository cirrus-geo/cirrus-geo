from cirrus.lib.logging import CirrusLoggerAdapter


def test_cirrus_logger_adapter_filters_payload_keys():
    """Test that only id and stac_version from payload are included in log extra."""
    payload = {
        "id": "test-collection/workflow-test/test-item",
        "stac_version": "1.0.0",
        "features": [{"type": "Feature"}],
        "process": [{"workflow": "test"}],
    }

    logger = CirrusLoggerAdapter("test.logger", payload=payload)

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" in processed_kwargs
    assert processed_kwargs["extra"]["id"] == "test-collection/workflow-test/test-item"
    assert processed_kwargs["extra"]["stac_version"] == "1.0.0"
    assert "features" not in processed_kwargs["extra"]
    assert "process" not in processed_kwargs["extra"]


def test_cirrus_logger_adapter_with_aws_request_id():
    """Test that aws_request_id is added to log extra when provided."""
    payload = {
        "id": "test-collection/workflow-test/test-item",
        "stac_version": "1.0.0",
    }
    request_id = "abc123-def456-ghi789"

    logger = CirrusLoggerAdapter(
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


def test_cirrus_logger_adapter_with_empty_payload_and_aws_request_id():
    """Test that aws_request_id is added even with no payload."""
    request_id = "abc123-def456-ghi789"

    logger = CirrusLoggerAdapter(
        "test.logger",
        aws_request_id=request_id,
    )

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" in processed_kwargs
    assert processed_kwargs["extra"]["aws_request_id"] == request_id


def test_cirrus_logger_adapter_missing_stac_version():
    """Test that logger handles payload missing stac_version."""
    payload = {
        "id": "test-collection/workflow-test/test-item",
    }

    logger = CirrusLoggerAdapter("test.logger", payload=payload)

    msg = "test message"
    kwargs = {}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert "extra" in processed_kwargs
    assert processed_kwargs["extra"]["id"] == "test-collection/workflow-test/test-item"
    assert "stac_version" not in processed_kwargs["extra"]


def test_process_merges_existing_kwargs_extra():
    """Test that process() merges caller-provided extra with adapter's extra."""
    payload = {
        "id": "test-item",
        "stac_version": "1.0.0",
    }

    logger = CirrusLoggerAdapter("test.logger", payload=payload)

    msg = "test message"
    caller_extra = {"custom_key": "custom_value", "request_id": "req-123"}
    kwargs = {"extra": caller_extra}
    processed_msg, processed_kwargs = logger.process(msg, kwargs)

    assert processed_msg == msg
    assert processed_kwargs["extra"]["id"] == "test-item"
    assert processed_kwargs["extra"]["stac_version"] == "1.0.0"
    assert processed_kwargs["extra"]["custom_key"] == "custom_value"
    assert processed_kwargs["extra"]["request_id"] == "req-123"


def test_cirrus_logger_adapter_propagate_disabled_for_cirrus_loggers():
    """Test that propagate is disabled for cirrus loggers to prevent double-logging."""
    payload = {"id": "test-item"}

    logger = CirrusLoggerAdapter("cirrus.lib.test", payload=payload)

    # cirrus.lib is in config["loggers"], so propagate should be False
    assert logger.logger.parent is not None
    assert logger.logger.parent.propagate is False


def test_cirrus_logger_adapter_propagate_not_disabled_for_non_cirrus_loggers():
    """Test that propagate is not modified for loggers outside cirrus config."""
    payload = {"id": "test-item"}

    logger = CirrusLoggerAdapter("external.logger", payload=payload)

    # external.logger is not in config["loggers"], so propagate should remain True
    assert logger.logger.parent is not None
    assert logger.logger.parent.propagate is True
