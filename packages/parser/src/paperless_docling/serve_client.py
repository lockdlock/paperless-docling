"""Docling Serve の非同期 API で変換し、サーバーが作った Markdown を取得する。

Docling Serve の docling.service_client は、サーバーが作った Markdown（md_content）を
捨てて JSON の文書だけを返す。そのため paperless 側で Markdown を作り直すことになり、
サーバー側の設定（出力形式の補正など）が反映されない。
このモジュールは、サーバーの md_content をそのまま返す。

使うエンドポイント（Docling Serve v1）:
- POST /v1/convert/file/async
- GET  /v1/status/poll/{task_id}?wait=
- GET  /v1/result/{task_id}
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from docling.datamodel.base_models import OutputFormat

if TYPE_CHECKING:
    from docling.datamodel.service.options import ConvertDocumentsOptions

SUBMIT_PATH = "/v1/convert/file/async"
POLL_PATH = "/v1/status/poll/{task_id}"
RESULT_PATH = "/v1/result/{task_id}"

SUCCESS_STATUSES = {"success"}
FAILURE_STATUSES = {"failure"}
CONVERT_FAILURE_STATUSES = {"failure"}

# サーバーが wait の間ブロックせず即答する場合でも、短時間に大量のポーリングをしないための最小間隔（秒）
MIN_POLL_PAUSE = 0.5


class DoclingServeError(RuntimeError):
    """Docling Serve との通信または変換の失敗。"""


def convert_to_markdown(
    *,
    serve_url: str,
    document_path: Path,
    options: ConvertDocumentsOptions,
    token: str | None,
    poll_interval: float,
    deadline: float,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """文書を変換し、Docling Serve が作った Markdown を返す。"""
    base_url = serve_url.rstrip("/")
    headers = {"X-Api-Key": token} if token else {}
    form = encode_options(options)
    started_at = time.monotonic()

    with httpx.Client(
        base_url=base_url,
        headers=headers,
        timeout=httpx.Timeout(30.0, read=max(30.0, poll_interval + 30.0)),
        transport=transport,
    ) as client:
        task_id = _submit(client, document_path, form)
        _wait(client, task_id, poll_interval, deadline, started_at)
        return _fetch_markdown(client, task_id)


def encode_options(options: ConvertDocumentsOptions) -> list[tuple[str, str]]:
    """設定されたオプションだけを multipart のフォーム項目にする。"""
    dumped: dict[str, Any] = options.model_dump(
        mode="json",
        exclude_unset=True,
        exclude_none=True,
    )

    # Markdown はサーバーの md_content を使うので、md は必ず要求する
    formats = list(dumped.get("to_formats") or [])
    if OutputFormat.MARKDOWN.value not in formats:
        formats.append(OutputFormat.MARKDOWN.value)
    dumped["to_formats"] = formats

    form: list[tuple[str, str]] = []
    for key, value in dumped.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            form.append((key, _form_value(item)))
    return form


def _as_multipart_fields(form: list[tuple[str, str]]) -> dict[str, list[str]]:
    # 同名の項目を繰り返す形（from_formats など）にする
    fields: dict[str, list[str]] = {}
    for key, value in form:
        fields.setdefault(key, []).append(value)
    return fields


def _form_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        import json

        return json.dumps(value)
    return str(value)


def _submit(
    client: httpx.Client,
    document_path: Path,
    form: list[tuple[str, str]],
) -> str:
    try:
        with document_path.open("rb") as handle:
            response = client.post(
                SUBMIT_PATH,
                data=_as_multipart_fields(form),
                files={"files": (document_path.name, handle)},
            )
    except httpx.HTTPError as error:
        raise DoclingServeError(
            f"Could not submit the document to Docling Serve: {type(error).__name__}.",
        ) from None

    _raise_for_status(response, "submit")
    task_id = _json(response).get("task_id")
    if not task_id:
        raise DoclingServeError("Docling Serve did not return a task id.")
    return str(task_id)


def _wait(
    client: httpx.Client,
    task_id: str,
    poll_interval: float,
    deadline: float,
    started_at: float,
) -> None:
    while True:
        remaining = deadline - (time.monotonic() - started_at)
        if remaining <= 0:
            raise DoclingServeError(
                "Docling Serve did not finish before the configured deadline.",
            )

        poll_started = time.monotonic()
        try:
            response = client.get(
                POLL_PATH.format(task_id=task_id),
                params={"wait": min(poll_interval, remaining)},
            )
        except httpx.HTTPError as error:
            raise DoclingServeError(
                f"Could not poll Docling Serve: {type(error).__name__}.",
            ) from None

        _raise_for_status(response, "poll")
        body = _json(response)
        status = str(body.get("task_status", "")).lower()

        if status in SUCCESS_STATUSES:
            return
        if status in FAILURE_STATUSES:
            message = body.get("error_message") or "no error message"
            raise DoclingServeError(f"Docling Serve reported a failure: {message}")

        # 即答された場合だけ、最小間隔になるまで待つ（wait で待たされた場合は追加で待たない）
        pause = min(MIN_POLL_PAUSE, poll_interval) - (time.monotonic() - poll_started)
        remaining = deadline - (time.monotonic() - started_at)
        if pause > 0 and remaining > 0:
            time.sleep(min(pause, remaining))


def _fetch_markdown(client: httpx.Client, task_id: str) -> str:
    try:
        response = client.get(RESULT_PATH.format(task_id=task_id))
    except httpx.HTTPError as error:
        raise DoclingServeError(
            f"Could not fetch the Docling Serve result: {type(error).__name__}.",
        ) from None

    _raise_for_status(response, "result")
    body = _json(response)

    status = str(body.get("status", "")).lower()
    if status in CONVERT_FAILURE_STATUSES:
        errors = body.get("errors") or "no details"
        raise DoclingServeError(f"Docling Serve failed to convert the document: {errors}")

    document = body.get("document")
    markdown = document.get("md_content") if isinstance(document, dict) else None
    if markdown is None:
        raise DoclingServeError(
            "Docling Serve returned no Markdown (md_content). "
            "Check that 'md' is included in the requested output formats.",
        )
    return str(markdown)


def _raise_for_status(response: httpx.Response, step: str) -> None:
    if response.is_success:
        return
    raise DoclingServeError(
        f"Docling Serve returned HTTP {response.status_code} during {step}.",
    )


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        raise DoclingServeError("Docling Serve returned a non-JSON response.") from None
    if not isinstance(body, dict):
        raise DoclingServeError("Docling Serve returned an unexpected response.")
    return body
