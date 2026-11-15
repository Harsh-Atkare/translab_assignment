def test_liveness(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readiness_reports_checks(client):
    r = client.get("/readyz")
    assert r.status_code == 200

    body = r.json()
    assert body["checks"]["vector_store"] is True
    assert body["checks"]["api_key"] is True


def test_metrics_exposes_our_custom_series(client):
    body = client.get("/metrics").text
    assert "kb_query_duration_seconds" in body
    assert "kb_ingest_duration_seconds" in body
    assert "http_requests_total" in body


def test_index_page_served(client):
    from app.main import ui_dir

    r = client.get("/")

    if ui_dir() is None:
        assert r.status_code == 503
        assert "make ui" in r.json()["detail"]
    else:
        assert r.status_code == 200
        assert "Knowledge Assistant" in r.text


def test_api_works_without_a_frontend_build(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/documents").status_code == 200
    assert client.get("/docs").status_code == 200


def test_info_exposes_the_settings_worth_checking(client):
    body = client.get("/api/info").json()

    for key in (
        "chat_model",
        "embed_model",
        "thinking_budget",
        "max_output_tokens",
        "request_timeout",
        "top_k",
    ):
        assert key in body, key


def test_info_never_leaks_the_api_key(client):
    body = client.get("/api/info").json()

    assert body["api_key_set"] is True
    assert "test-key" not in str(body)
    assert not any("api_key" == k or k.endswith("_key") for k in body if k != "api_key_set")
