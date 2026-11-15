def test_upload_then_list_then_delete(client, sample_pdf):
    r = client.post(
        "/api/documents",
        files={"file": ("contract.pdf", sample_pdf, "application/pdf")},
    )
    assert r.status_code == 201

    body = r.json()
    assert body["pages"] == 2
    assert body["chunks"] > 0
    doc_id = body["doc_id"]

    listed = client.get("/api/documents").json()
    assert any(d["doc_id"] == doc_id for d in listed["documents"])

    removed = client.delete(f"/api/documents/{doc_id}")
    assert removed.status_code == 200
    assert removed.json()["chunks_removed"] == body["chunks"]


def test_non_pdf_is_rejected(client):
    r = client.post(
        "/api/documents", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


def test_empty_file_is_rejected(client):
    r = client.post(
        "/api/documents", files={"file": ("empty.pdf", b"", "application/pdf")}
    )
    assert r.status_code == 400


def test_deleting_unknown_document_is_404(client):
    assert client.delete("/api/documents/doesnotexist").status_code == 404


def test_ask_returns_answer_and_sources(client, sample_pdf):
    client.post(
        "/api/documents",
        files={"file": ("contract.pdf", sample_pdf, "application/pdf")},
    )

    r = client.post("/api/ask", json={"question": "What is the notice period?"})
    assert r.status_code == 200

    body = r.json()
    assert "answer" in body
    assert isinstance(body["sources"], list)
    assert body["seconds"] >= 0


def test_question_must_be_long_enough(client):
    r = client.post("/api/ask", json={"question": "hi"})
    assert r.status_code == 422 


def test_info_endpoint_reports_config(client):
    body = client.get("/api/info").json()
    assert body["chat_model"]
    assert body["chunk_size"] > 0


def test_request_id_is_echoed_back(client):
    r = client.get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
