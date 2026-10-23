"""Markdown export with optional picture-text handling.

docling-serve が返した DoclingDocument は、paperless 側でこのモジュールを通して
Markdown にする。既定の export_to_markdown() は、picture の子要素（レイアウトが
画像と誤判定した領域のテキストなど）を出力せず、``<!-- image -->`` に置き換える。

``traverse_pictures=True`` のとき:
- picture の子のテキストを出力する
- 子のテキストがある picture では、画像のプレースホルダーを出さない
- 子のテキストがない picture は、従来どおりプレースホルダーを出す

``traverse_pictures=False``（既定）は、従来の export_to_markdown() そのまま。
docling-core の内部名が変わって差し替えに失敗した場合は、
``export_to_markdown(traverse_pictures=True)`` に切り替える（プレースホルダーは残る）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docling_core.types.doc.base import ImageRefMode

if TYPE_CHECKING:
    from docling_core.types.doc import DoclingDocument

_LOGGER = logging.getLogger(__name__)


def export_markdown(
    document: DoclingDocument,
    *,
    traverse_pictures: bool,
    image_mode: ImageRefMode = ImageRefMode.PLACEHOLDER,
    page_break_placeholder: str | None = None,
    compact_tables: bool = False,
) -> str:
    # 設定値（既定値と同じなら、従来の出力と同じ）
    native = {
        "image_mode": image_mode,
        "page_break_placeholder": page_break_placeholder or None,
        "compact_tables": compact_tables,
    }

    if not traverse_pictures:
        return document.export_to_markdown(**native)

    try:
        return _export_without_placeholder(document, native)
    except Exception:  # docling-core の内部構造が変わった場合の退避
        _LOGGER.warning(
            "Falling back to export_to_markdown(traverse_pictures=True); "
            "picture placeholders will remain.",
            exc_info=True,
        )
        return document.export_to_markdown(traverse_pictures=True, **native)


def _export_without_placeholder(document: DoclingDocument, native: dict) -> str:
    from docling_core.transforms.serializer.common import create_ser_result
    from docling_core.transforms.serializer.markdown import (
        MarkdownDocSerializer,
        MarkdownParams,
        MarkdownPictureSerializer,
    )
    from docling_core.types.doc.document import (
        DEFAULT_CONTENT_LAYERS,
        DOCUMENT_TOKENS_EXPORT_LABELS,
        TextItem,
    )

    if not hasattr(MarkdownPictureSerializer, "_serialize_image_part"):
        raise AttributeError("MarkdownPictureSerializer._serialize_image_part")

    class _PictureSerializer(MarkdownPictureSerializer):
        def _serialize_image_part(self, item, doc, *args, **kwargs):  # type: ignore[no-untyped-def]
            if _has_text_children(item, doc, TextItem):
                return create_ser_result(text="", span_source=item)
            return super()._serialize_image_part(item, doc, *args, **kwargs)

    serializer = MarkdownDocSerializer(
        doc=document,
        picture_serializer=_PictureSerializer(),
        params=MarkdownParams(
            labels=DOCUMENT_TOKENS_EXPORT_LABELS,
            layers=DEFAULT_CONTENT_LAYERS,
            traverse_pictures=True,
            image_mode=native["image_mode"],
            page_break_placeholder=native["page_break_placeholder"],
            compact_tables=native["compact_tables"],
        ),
    )
    return serializer.serialize().text


def _has_text_children(item, doc, text_item_type) -> bool:  # type: ignore[no-untyped-def]
    for child in getattr(item, "children", None) or []:
        try:
            if isinstance(child.resolve(doc), text_item_type):
                return True
        except Exception:
            continue
    return False
