"""PluginConfig から Docling Serve への変換オプションを組み立てる。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docling.datamodel.service.options import ConvertDocumentsOptions

if TYPE_CHECKING:
    from paperless_docling.config import PluginConfig


def build_options(config: PluginConfig) -> ConvertDocumentsOptions:
    # 必須設定は常に送る。任意設定は、設定されたものだけ送る。
    # PAPERLESS_DOCLING_EXTRA_OPTIONS は、同名の項目を上書きする。
    values = {
        "from_formats": list(config.from_formats),
        "to_formats": list(config.to_formats),
        "pipeline": config.pipeline,
        "do_ocr": config.do_ocr,
        "force_ocr": config.force_ocr,
        "ocr_preset": config.ocr_preset,
        "ocr_lang": list(config.ocr_lang),
        "include_images": config.include_images,
        "include_page_images": config.include_page_images,
        "images_scale": config.images_scale,
        "do_table_structure": config.do_table_structure,
        "table_mode": config.table_mode,
        "table_cell_matching": config.table_cell_matching,
        "do_pdf_heading_hierarchy": config.do_pdf_heading_hierarchy,
        "image_export_mode": config.image_export_mode,
        "md_page_break_placeholder": config.md_page_break_placeholder,
        "md_compact_tables": config.md_compact_tables,
    }
    values.update(config.optional_request_options)
    return ConvertDocumentsOptions(**values)
