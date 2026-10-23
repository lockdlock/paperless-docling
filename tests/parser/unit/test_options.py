import pytest
from paperless_docling.config import PluginConfig
from paperless_docling.errors import ConfigurationError
from paperless_docling.options import build_options

from tests.parser.unit.test_config import valid_env

OPTIONAL_VARIABLES = [
    "PAPERLESS_DOCLING_VLM_PIPELINE_PRESET",
    "PAPERLESS_DOCLING_LAYOUT_PRESET",
    "PAPERLESS_DOCLING_TABLE_STRUCTURE_PRESET",
    "PAPERLESS_DOCLING_CODE_FORMULA_PRESET",
    "PAPERLESS_DOCLING_CHART_EXTRACTION_PRESET",
    "PAPERLESS_DOCLING_PICTURE_CLASSIFICATION_PRESET",
    "PAPERLESS_DOCLING_PICTURE_DESCRIPTION_PRESET",
    "PAPERLESS_DOCLING_DO_CODE_ENRICHMENT",
    "PAPERLESS_DOCLING_DO_FORMULA_ENRICHMENT",
    "PAPERLESS_DOCLING_DO_CHART_EXTRACTION",
    "PAPERLESS_DOCLING_DO_PICTURE_CLASSIFICATION",
    "PAPERLESS_DOCLING_DO_PICTURE_DESCRIPTION",
    "PAPERLESS_DOCLING_ABORT_ON_ERROR",
    "PAPERLESS_DOCLING_DOCUMENT_TIMEOUT_SECONDS",
    "PAPERLESS_DOCLING_EXTRA_OPTIONS",
]


def sent_fields(tmp_path, **overrides):
    config = PluginConfig.from_environment(valid_env(tmp_path, **overrides))
    return build_options(config).model_fields_set


def test_optional_settings_are_not_sent_when_unset(tmp_path):
    fields = sent_fields(tmp_path)

    assert fields.isdisjoint(
        {
            "vlm_pipeline_preset",
            "layout_preset",
            "table_structure_preset",
            "code_formula_preset",
            "do_code_enrichment",
            "document_timeout",
        },
    )


def test_blank_optional_settings_are_treated_as_unset(tmp_path):
    blanks = {variable: "" for variable in OPTIONAL_VARIABLES}

    assert sent_fields(tmp_path, **blanks) == sent_fields(tmp_path)


def test_presets_booleans_and_timeout_are_sent_when_set(tmp_path):
    config = PluginConfig.from_environment(
        valid_env(
            tmp_path,
            PAPERLESS_DOCLING_TABLE_STRUCTURE_PRESET="tableformer_v2",
            PAPERLESS_DOCLING_LAYOUT_PRESET="heron",
            PAPERLESS_DOCLING_DO_FORMULA_ENRICHMENT="true",
            PAPERLESS_DOCLING_DOCUMENT_TIMEOUT_SECONDS="120",
        ),
    )

    options = build_options(config)

    assert options.table_structure_preset == "tableformer_v2"
    assert options.layout_preset == "heron"
    assert options.do_formula_enrichment is True
    assert options.document_timeout == 120.0


def test_extra_options_override_named_settings(tmp_path):
    config = PluginConfig.from_environment(
        valid_env(
            tmp_path,
            PAPERLESS_DOCLING_LAYOUT_PRESET="heron",
            PAPERLESS_DOCLING_EXTRA_OPTIONS='{"layout_preset": "other", "page_range": [1, 3]}',
        ),
    )

    options = build_options(config)

    assert options.layout_preset == "other"
    assert tuple(options.page_range) == (1, 3)


@pytest.mark.parametrize(
    "value",
    ["not json", "[1, 2]", '{"no_such_option": true}'],
)
def test_extra_options_reject_invalid_values(tmp_path, value):
    with pytest.raises(ConfigurationError, match="PAPERLESS_DOCLING_EXTRA_OPTIONS"):
        PluginConfig.from_environment(
            valid_env(tmp_path, PAPERLESS_DOCLING_EXTRA_OPTIONS=value),
        )


def test_invalid_optional_boolean_is_rejected(tmp_path):
    with pytest.raises(ConfigurationError, match="PAPERLESS_DOCLING_DO_CODE_ENRICHMENT"):
        PluginConfig.from_environment(
            valid_env(tmp_path, PAPERLESS_DOCLING_DO_CODE_ENRICHMENT="maybe"),
        )
