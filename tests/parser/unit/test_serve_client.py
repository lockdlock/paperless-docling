import httpx
from paperless_docling import serve_client
import pytest
from docling.datamodel.service.options import ConvertDocumentsOptions
from paperless_docling.serve_client import (
    DoclingServeError,
    convert_to_markdown,
    encode_options,
)


def make_options(**values):
    return ConvertDocumentsOptions(**values)


def run(tmp_path, handler, **overrides):
    document = tmp_path / "input.pdf"
    document.write_bytes(b"%PDF-1.4 test")
    arguments = {
        "serve_url": "http://docling.test/",
        "document_path": document,
        "options": make_options(do_ocr=True),
        "token": None,
        "poll_interval": 0.01,
        "deadline": 5.0,
        "transport": httpx.MockTransport(handler),
    }
    arguments.update(overrides)
    return convert_to_markdown(**arguments)


def serve_handler(*, statuses=("pending", "success"), result=None, seen=None):
    queue = list(statuses)
    result = result or {"status": "success", "document": {"md_content": "# Title"}}

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.method == "POST" and request.url.path == "/v1/convert/file/async":
            return httpx.Response(200, json={"task_id": "t1", "task_status": "pending"})
        if request.url.path == "/v1/status/poll/t1":
            status = queue.pop(0) if len(queue) > 1 else queue[0]
            return httpx.Response(200, json={"task_id": "t1", "task_status": status})
        if request.url.path == "/v1/result/t1":
            return httpx.Response(200, json=result)
        return httpx.Response(404)

    return handler


def test_returns_the_markdown_made_by_the_server(tmp_path):
    assert run(tmp_path, serve_handler()) == "# Title"


def test_token_is_sent_as_api_key_header(tmp_path):
    seen: list[httpx.Request] = []

    run(tmp_path, serve_handler(seen=seen), token="secret-token")

    assert seen
    assert all(request.headers["x-api-key"] == "secret-token" for request in seen)


def test_no_api_key_header_without_a_token(tmp_path):
    seen: list[httpx.Request] = []

    run(tmp_path, serve_handler(seen=seen))

    assert all("x-api-key" not in request.headers for request in seen)


def test_submit_sends_options_and_requests_markdown(tmp_path):
    seen: list[httpx.Request] = []

    run(tmp_path, serve_handler(seen=seen))

    body = seen[0].read().decode("latin-1")
    assert 'name="do_ocr"' in body
    assert 'name="to_formats"' in body
    assert "md" in body


def test_encode_options_only_includes_set_options_and_adds_markdown():
    form = encode_options(make_options(do_ocr=True, to_formats=["json"]))

    keys = [key for key, _ in form]
    assert ("to_formats", "json") in form
    assert ("to_formats", "md") in form
    assert ("do_ocr", "true") in form
    assert "force_ocr" not in keys
    assert "layout_preset" not in keys


def test_encode_options_keeps_markdown_once():
    form = encode_options(make_options(to_formats=["md"]))

    assert form.count(("to_formats", "md")) == 1


def test_failure_status_raises_with_the_server_message(tmp_path):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "t1"})
        return httpx.Response(
            200,
            json={"task_status": "failure", "error_message": "boom"},
        )

    with pytest.raises(DoclingServeError, match="boom"):
        run(tmp_path, handler)


def test_http_error_raises_without_leaking_the_token(tmp_path):
    def handler(request):
        return httpx.Response(401, text="invalid key secret-token")

    with pytest.raises(DoclingServeError) as error:
        run(tmp_path, handler, token="secret-token")

    assert "401" in str(error.value)
    assert "secret-token" not in str(error.value)


def test_missing_markdown_raises(tmp_path):
    handler = serve_handler(result={"status": "success", "document": {}})

    with pytest.raises(DoclingServeError, match="md_content"):
        run(tmp_path, handler)


def test_conversion_failure_in_result_raises(tmp_path):
    handler = serve_handler(
        result={"status": "failure", "errors": [{"message": "bad pdf"}], "document": {}},
    )

    with pytest.raises(DoclingServeError, match="failed to convert"):
        run(tmp_path, handler)


def test_deadline_is_enforced(tmp_path):
    handler = serve_handler(statuses=("pending",))

    with pytest.raises(DoclingServeError, match="deadline"):
        run(tmp_path, handler, deadline=0.05, poll_interval=0.01)


def test_connection_error_is_wrapped(tmp_path):
    def handler(request):
        raise httpx.ConnectError("refused http://docling.test secret-token")

    with pytest.raises(DoclingServeError) as error:
        run(tmp_path, handler, token="secret-token")

    assert "secret-token" not in str(error.value)


def test_polling_pauses_when_the_server_answers_immediately(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(serve_client.time, "sleep", sleeps.append)
    monkeypatch.setattr(serve_client, "MIN_POLL_PAUSE", 0.5)
    handler = serve_handler(statuses=("pending", "pending", "success"))
    run(tmp_path, handler, poll_interval=2.0)
    # 即答の pending が 2 回 → 2 回待つ。success のあとは待たない
    assert len(sleeps) == 2
    assert all(0 < pause <= 0.5 for pause in sleeps)
