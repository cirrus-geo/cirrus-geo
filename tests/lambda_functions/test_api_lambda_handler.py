import json

from cirrus.lambda_functions import api
from cirrus.lib.statedb import StateDB


def _invoke(event):
    resp = api.lambda_handler(event, {})
    return resp["statusCode"], json.loads(resp["body"])


def _make_rest_api_event(path, stage="$default", query_params=None):
    """API Gateway REST API (v1) / payload format 1.0.

    Uses top-level ``path`` and ``httpMethod``.
    """
    return {
        "path": path,
        "httpMethod": "GET",
        "requestContext": {"stage": stage},
        "queryStringParameters": query_params,
    }


def _make_http_api_event(raw_path, query_params=None):
    """API Gateway HTTP API (v2) / Lambda Function URL / payload format 2.0.

    Uses top-level ``rawPath`` and ``requestContext.http.method``.
    Lambda Function URLs use the same payload format.
    """
    return {
        "rawPath": raw_path,
        "requestContext": {
            "http": {"method": "GET", "path": raw_path},
            "stage": "$default",
        },
        "queryStringParameters": query_params,
    }


class TestRestApiPayloadFormat:
    """Routing with API Gateway REST API (payload format 1.0) events."""

    def test_stats_route(self, monkeypatch):
        monkeypatch.setattr(api, "get_stats", lambda **kw: {"ok": True})
        status, body = _invoke(_make_rest_api_event("/stats"))
        assert status == 200
        assert body == {"ok": True}

    def test_workflow_summary(self, monkeypatch):
        monkeypatch.setattr(
            api,
            "summary",
            lambda cw, since, limit, statedb: {
                "collections": "mycol",
                "workflow": "mywf",
            },
        )
        status, body = _invoke(_make_rest_api_event("/mycol/workflow-mywf"))
        assert status == 200
        assert body == {"collections": "mycol", "workflow": "mywf"}

    def test_workflow_items(self, monkeypatch):
        monkeypatch.setattr(
            StateDB,
            "get_items_page",
            lambda self, *a, **kw: {"items": []},
        )
        status, body = _invoke(
            _make_rest_api_event(
                "/mycol/workflow-mywf/items",
                query_params={"state": "FAILED", "limit": "10"},
            ),
        )
        assert status == 200
        assert body == {"items": []}

    def test_single_item(self, monkeypatch):
        fake_item = {"id": "myitem123"}
        monkeypatch.setattr(StateDB, "get_dbitem", lambda self, pid: fake_item)
        monkeypatch.setattr(StateDB, "dbitem_to_item", lambda self, i: i)
        monkeypatch.setattr(api, "to_current", lambda i: i)
        status, body = _invoke(
            _make_rest_api_event("/mycol/workflow-mywf/items/myitem123"),
        )
        assert status == 200
        assert body == {"id": "myitem123"}

    def test_stage_prefix_is_stripped(self, monkeypatch):
        monkeypatch.setattr(api, "get_stats", lambda **kw: {"ok": True})
        status, body = _invoke(
            _make_rest_api_event("/somestage/stats", stage="somestage"),
        )
        assert status == 200
        assert body == {"ok": True}

    def test_query_params_forwarded(self, monkeypatch):
        captured = {}

        def fake_get_items_page(self, cw, **kwargs):
            captured.update(kwargs)
            return {"items": []}

        monkeypatch.setattr(StateDB, "get_items_page", fake_get_items_page)
        status, _body = _invoke(
            _make_rest_api_event(
                "/mycol/workflow-mywf/items",
                query_params={
                    "state": "COMPLETED",
                    "since": "1d",
                    "limit": "50",
                    "sort_ascending": "1",
                    "sort_index": "created",
                    "nextkey": "abc",
                },
            ),
        )
        assert status == 200
        assert captured["state"] == "COMPLETED"
        assert captured["limit"] == 50
        assert captured["sort_ascending"] is True
        assert captured["sort_index"] == "created"
        assert captured["nextkey"] == "abc"


class TestHttpApiAndFunctionUrlPayloadFormat:
    """Routing with HTTP API / Lambda Function URL (payload format 2.0) events."""

    def test_stats_route(self, monkeypatch):
        monkeypatch.setattr(api, "get_stats", lambda **kw: {"ok": True})
        status, body = _invoke(_make_http_api_event("/stats"))
        assert status == 200
        assert body == {"ok": True}

    def test_workflow_summary(self, monkeypatch):
        monkeypatch.setattr(
            api,
            "summary",
            lambda cw, since, limit, statedb: {
                "collections": "mycol",
                "workflow": "mywf",
            },
        )
        status, body = _invoke(_make_http_api_event("/mycol/workflow-mywf"))
        assert status == 200
        assert body == {"collections": "mycol", "workflow": "mywf"}

    def test_workflow_items_with_filters(self, monkeypatch):
        monkeypatch.setattr(
            StateDB,
            "get_items_page",
            lambda self, *a, **kw: {"items": []},
        )
        status, body = _invoke(
            _make_http_api_event(
                "/mycol/workflow-mywf/items",
                query_params={"state": "FAILED", "limit": "10"},
            ),
        )
        assert status == 200
        assert body == {"items": []}


class TestRootPathStripping:
    """CIRRUS_API_GATEWAY_BASE_PATH strips a base path prefix before routing."""

    def test_rest_api_strips_prefix(self, monkeypatch):
        monkeypatch.setenv("CIRRUS_API_GATEWAY_BASE_PATH", "eoapi-cirrus")
        monkeypatch.setattr(api, "get_stats", lambda **kw: {"ok": True})
        status, body = _invoke(_make_rest_api_event("/eoapi-cirrus/stats"))
        assert status == 200
        assert body == {"ok": True}

    def test_http_api_strips_prefix(self, monkeypatch):
        monkeypatch.setenv("CIRRUS_API_GATEWAY_BASE_PATH", "eoapi-cirrus")
        monkeypatch.setattr(api, "get_stats", lambda **kw: {"ok": True})
        status, body = _invoke(_make_http_api_event("/eoapi-cirrus/stats"))
        assert status == 200
        assert body == {"ok": True}

    def test_strips_prefix_from_workflow_path(self, monkeypatch):
        monkeypatch.setenv("CIRRUS_API_GATEWAY_BASE_PATH", "myprefix")
        monkeypatch.setattr(
            api,
            "summary",
            lambda cw, since, limit, statedb: {
                "collections": "collections",
                "workflow": "wf",
            },
        )
        status, body = _invoke(
            _make_rest_api_event("/myprefix/collections/workflow-wf"),
        )
        assert status == 200
        assert body == {"collections": "collections", "workflow": "wf"}

    def test_no_env_var_preserves_default_behavior(self, monkeypatch):
        monkeypatch.delenv("CIRRUS_API_GATEWAY_BASE_PATH", raising=False)
        monkeypatch.setattr(api, "get_stats", lambda **kw: {"ok": True})
        status, body = _invoke(_make_rest_api_event("/stats"))
        assert status == 200
        assert body == {"ok": True}
