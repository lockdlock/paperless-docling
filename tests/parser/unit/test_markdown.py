import pytest
from docling_core.types.doc import DocItemLabel, DoclingDocument
from paperless_docling.markdown import export_markdown


def build_document(*, with_picture_text: bool) -> DoclingDocument:
    document = DoclingDocument(name="sample")
    document.add_heading("Heading")
    document.add_text(DocItemLabel.TEXT, "Body A")
    picture = document.add_picture()
    if with_picture_text:
        document.add_text(DocItemLabel.TEXT, "Receipt", parent=picture)
        document.add_text(DocItemLabel.TEXT, "Inside text", parent=picture)
    document.add_picture()
    document.add_text(DocItemLabel.TEXT, "Body B")
    return document


def test_disabled_matches_native_export():
    document = build_document(with_picture_text=True)

    assert export_markdown(document, traverse_pictures=False) == (
        document.export_to_markdown()
    )


def test_enabled_outputs_picture_text_without_placeholder_for_that_picture():
    document = build_document(with_picture_text=True)

    markdown = export_markdown(document, traverse_pictures=True)

    assert "Receipt" in markdown
    assert "Inside text" in markdown
    # 子のテキストがない picture のプレースホルダーだけが残る
    assert markdown.count("<!-- image -->") == 1


def test_enabled_without_picture_text_matches_native_export():
    document = build_document(with_picture_text=False)

    assert export_markdown(document, traverse_pictures=True) == (
        document.export_to_markdown()
    )


def test_enabled_falls_back_when_serializer_internals_change(monkeypatch):
    import paperless_docling.markdown as markdown_module

    def broken(_document):
        raise AttributeError("serializer internals changed")

    monkeypatch.setattr(markdown_module, "_export_without_placeholder", broken)
    document = build_document(with_picture_text=True)

    markdown = export_markdown(document, traverse_pictures=True)

    # 退避時もピクチャ内のテキストは出力される（プレースホルダーは残る）
    assert "Receipt" in markdown
    assert "<!-- image -->" in markdown


@pytest.mark.parametrize("flag", [True, False])
def test_export_returns_text(flag):
    document = build_document(with_picture_text=True)

    assert isinstance(export_markdown(document, traverse_pictures=flag), str)
