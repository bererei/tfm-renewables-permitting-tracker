import ast
import json
from dataclasses import asdict
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

import renewables_permitting.extraction.documents as documents_module
from renewables_permitting.extraction.documents import (
    DOCUMENT_PROMPT_TEMPLATE,
    MAX_DOCUMENT_CHARS,
    MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX,
    _required_date,
    _required_text,
    _source_document_hash,
    build_document_prompt,
    build_source_document,
    select_document_text,
)
from renewables_permitting.extraction.models import BOESourceDocument


def _document(
    *,
    boe_id: str = "BOE-A-2026-10001",
    publication_date: date = date(2026, 1, 2),
    title: str = "Autorización de la planta fotovoltaica Aurora.",
    text: str = "Texto documental de la planta Aurora.",
) -> BOESourceDocument:
    return BOESourceDocument(
        boe_id=boe_id,
        publication_date=publication_date,
        title=title,
        text=text,
        source_document_sha256=_source_document_hash(
            boe_id=boe_id,
            publication_date=publication_date,
            title=title,
            text=text,
        ),
    )


@pytest.mark.parametrize(
    ("value", "strip_value", "expected"),
    [
        ("texto válido", True, "texto válido"),
        ("  texto con espacios  ", True, "texto con espacios"),
        ("  texto conservado  ", False, "  texto conservado  "),
    ],
)
def test_required_text_returns_exact_string(
    value: str,
    strip_value: bool,
    expected: str,
) -> None:
    result = _required_text(
        value,
        field_name="campo",
        strip_value=strip_value,
    )

    assert result == expected
    assert type(result) is str


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_required_text_rejects_empty_strings(value: str) -> None:
    with pytest.raises(ValueError) as exc_info:
        _required_text(value, field_name="titulo")

    assert str(exc_info.value) == "titulo no puede estar vacío."


@pytest.mark.parametrize("value", [None, pd.NA, float("nan")])
def test_required_text_rejects_null_values(value: object) -> None:
    with pytest.raises(ValueError) as exc_info:
        _required_text(value, field_name="texto_limpio")

    assert str(exc_info.value) == "texto_limpio no puede ser nulo."


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 1, 2), date(2026, 1, 2)),
        (datetime(2026, 1, 2, 3, 4, 5), date(2026, 1, 2)),
        (pd.Timestamp("2026-01-02 03:04:05"), date(2026, 1, 2)),
        ("2026-01-02", date(2026, 1, 2)),
    ],
)
def test_required_date_accepts_notebook_inputs(
    value: object,
    expected: date,
) -> None:
    result = _required_date(value, field_name="fecha_publicacion")

    assert result == expected
    assert type(result) is date


@pytest.mark.parametrize("value", ["no-es-fecha", None, pd.NaT])
def test_required_date_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError) as exc_info:
        _required_date(value, field_name="fecha_publicacion")

    assert (
        str(exc_info.value)
        == "fecha_publicacion no contiene una fecha válida."
    )


def test_build_source_document_preserves_values_hash_and_input_row() -> None:
    row = pd.Series({
        "identificador": "  BOE-A-2026-10001  ",
        "fecha_publicacion": pd.Timestamp("2026-01-02 10:30:00"),
        "titulo": "  Autorización de Aurora  ",
        "texto_limpio": "  Texto con espacios exteriores.  ",
        "historical_column": "preservada",
    })
    original = row.copy(deep=True)
    expected_hash = sha256(
        (
            "BOE-A-2026-10001\n"
            "2026-01-02\n"
            "Autorización de Aurora\n"
            "  Texto con espacios exteriores.  "
        ).encode("utf-8")
    ).hexdigest()

    document = build_source_document(row)

    assert document.boe_id == "BOE-A-2026-10001"
    assert document.publication_date == date(2026, 1, 2)
    assert type(document.publication_date) is date
    assert document.title == "Autorización de Aurora"
    assert document.text == "  Texto con espacios exteriores.  "
    assert document.source_document_sha256 == expected_hash
    assert build_source_document(row).source_document_sha256 == expected_hash
    pd.testing.assert_series_equal(row, original)


def test_source_document_hash_matches_notebook_and_changes_per_source_field() -> None:
    values = {
        "boe_id": "BOE-A-2026-10001",
        "publication_date": date(2026, 1, 2),
        "title": "Título",
        "text": "Texto",
    }
    expected = sha256(
        "BOE-A-2026-10001\n2026-01-02\nTítulo\nTexto".encode("utf-8")
    ).hexdigest()

    baseline = _source_document_hash(**values)

    assert baseline == expected
    assert _source_document_hash(**values) == baseline
    for field_name, changed_value in {
        "boe_id": "BOE-B-2026-10001",
        "publication_date": date(2026, 1, 3),
        "title": "Otro título",
        "text": "Otro texto",
    }.items():
        changed = {**values, field_name: changed_value}
        assert _source_document_hash(**changed) != baseline


@pytest.mark.parametrize(
    "missing_column",
    ["identificador", "fecha_publicacion", "titulo", "texto_limpio"],
)
def test_build_source_document_missing_columns_raise_key_error(
    missing_column: str,
) -> None:
    row = pd.Series({
        "identificador": "BOE-A-2026-10001",
        "fecha_publicacion": "2026-01-02",
        "titulo": "Título",
        "texto_limpio": "Texto",
    }).drop(labels=[missing_column])

    with pytest.raises(KeyError) as exc_info:
        build_source_document(row)

    assert exc_info.value.args == (missing_column,)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("identificador", None, "identificador no puede ser nulo."),
        (
            "fecha_publicacion",
            None,
            "fecha_publicacion no contiene una fecha válida.",
        ),
        ("titulo", pd.NA, "titulo no puede ser nulo."),
        ("texto_limpio", float("nan"), "texto_limpio no puede ser nulo."),
        ("titulo", "  ", "titulo no puede estar vacío."),
        ("texto_limpio", " \t ", "texto_limpio no puede estar vacío."),
    ],
)
def test_build_source_document_rejects_invalid_required_values(
    column: str,
    value: object,
    message: str,
) -> None:
    row = pd.Series({
        "identificador": "BOE-A-2026-10001",
        "fecha_publicacion": "2026-01-02",
        "titulo": "Título",
        "texto_limpio": "Texto",
    })
    row[column] = value

    with pytest.raises(ValueError) as exc_info:
        build_source_document(row)

    assert str(exc_info.value) == message


def test_build_source_document_rejects_invalid_boe_id() -> None:
    row = pd.Series({
        "identificador": "BOE-C-2026-10001",
        "fecha_publicacion": "2026-01-02",
        "titulo": "Título",
        "texto_limpio": "Texto",
    })

    with pytest.raises(ValidationError):
        build_source_document(row)


def test_select_short_document_returns_exact_full_text_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "Documento breve.\nSegunda línea."
    expected_hash = sha256(text.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        documents_module,
        "MAX_DOCUMENT_CHARS",
        len(text) + 1,
    )

    selected = select_document_text(text)

    assert selected.text == text
    assert selected.strategy == "full_text"
    assert selected.marker is None
    assert selected.excluded_chars == 0
    assert selected.text_sha256 == expected_hash
    assert asdict(select_document_text(text)) == asdict(selected)


def test_select_document_exactly_at_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "x" * 20
    monkeypatch.setattr(documents_module, "MAX_DOCUMENT_CHARS", 20)

    selected = select_document_text(text)

    assert selected.text == text
    assert len(selected.text) == 20
    assert selected.strategy == "full_text"
    assert selected.excluded_chars == 0


def test_select_document_over_limit_without_annex_raises_exact_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "x" * 21
    monkeypatch.setattr(documents_module, "MAX_DOCUMENT_CHARS", 20)

    with pytest.raises(ValueError) as exc_info:
        select_document_text(text)

    assert str(exc_info.value) == (
        "El documento contiene 21 caracteres y supera "
        "MAX_DOCUMENT_CHARS=20; no se truncará."
    )


def test_select_document_over_limit_with_late_annex_uses_selected_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    substantive = "A" * MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX
    heading = "ANEXO II: RELACIÓN DE BIENES Y DERECHOS AFECTADOS"
    excluded = f"\n{heading}\nContenido excluido."
    text = substantive + excluded
    monkeypatch.setattr(
        documents_module,
        "MAX_DOCUMENT_CHARS",
        len(substantive),
    )

    selected = select_document_text(text)

    assert len(text) > documents_module.MAX_DOCUMENT_CHARS
    assert selected.text == substantive
    assert selected.strategy == "before_affected_assets_annex"
    assert selected.marker == heading
    assert selected.excluded_chars == len(excluded)
    assert selected.text_sha256 == sha256(
        substantive.encode("utf-8")
    ).hexdigest()


def test_annex_before_minimum_substantive_text_is_ignored() -> None:
    prefix = "A" * (MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX - 2)
    heading = "RELACIÓN DE BIENES Y DERECHOS AFECTADOS"
    text = f"{prefix}\n{heading}\nContenido del anexo."

    selected = select_document_text(text)

    assert selected.text == text
    assert selected.strategy == "full_text"
    assert selected.marker is None
    assert selected.excluded_chars == 0


def test_annex_after_minimum_substantive_text_is_removed_exactly() -> None:
    substantive = "Contenido " * 125
    assert len(substantive) >= MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX
    expected_selected = substantive.rstrip()
    heading = (
        "ANEXO A.- RELACIÓN CONCRETA E INDIVIDUALIZADA "
        "DE BIENES Y DERECHOS AFECTADOS"
    )
    excluded = f"\n{heading}\nParcela 1."
    text = substantive + excluded

    selected = select_document_text(text)

    assert selected.text == expected_selected
    assert selected.strategy == "before_affected_assets_annex"
    assert selected.marker == heading
    assert selected.excluded_chars == len(text) - len(expected_selected)
    assert selected.text_sha256 == sha256(
        expected_selected.encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize(
    "heading",
    [
        "RELACIÓN DE BIENES Y DERECHOS AFECTADOS",
        "RELACION DE BIENES Y DERECHOS AFECTADOS",
        (
            "RELACIÓN CONCRETA E INDIVIDUALIZADA "
            "DE BIENES Y DERECHOS AFECTADOS"
        ),
        "ANEXO II: RELACIÓN DE BIENES Y DERECHOS AFECTADOS",
        "  ANEXO IV.- RELACION DE BIENES Y DERECHOS AFECTADOS",
    ],
)
def test_annex_heading_typographic_variants_are_detected(heading: str) -> None:
    substantive = "A" * MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX
    text = f"{substantive}\n{heading}\nFila del anexo."

    selected = select_document_text(text)

    assert selected.text == substantive
    assert selected.strategy == "before_affected_assets_annex"
    assert selected.marker == heading.strip()
    assert "Fila del anexo." not in selected.text


@pytest.mark.parametrize("text", ["", "   ", "\t\n"])
def test_select_document_text_rejects_empty_or_whitespace(text: str) -> None:
    with pytest.raises(ValueError) as exc_info:
        select_document_text(text)

    assert str(exc_info.value) == "El texto documental no puede estar vacío."


def test_build_document_prompt_is_exact_and_contains_no_agent_instructions() -> None:
    document = _document()
    original = asdict(document)
    expected_prompt = (
        "Analiza exclusivamente la publicación delimitada a continuación.\n"
        "No reproduzcas boe_id ni publication_date en BOEAIExtraction.\n\n"
        "BOE_ID: BOE-A-2026-10001\n"
        "FECHA_PUBLICACION: 2026-01-02\n"
        "TITULO: Autorización de la planta fotovoltaica Aurora.\n"
        "ESTRATEGIA_TEXTO: full_text\n\n"
        "<BOE_DOCUMENT>\n"
        "Texto documental de la planta Aurora.\n"
        "</BOE_DOCUMENT>"
    )

    prepared = build_document_prompt(document)

    assert prepared.prompt == expected_prompt
    assert prepared.input_text_chars == len(document.text)
    assert prepared.input_text_sha256 == sha256(
        document.text.encode("utf-8")
    ).hexdigest()
    assert prepared.input_selection_strategy == "full_text"
    assert prepared.input_selection_marker is None
    assert prepared.input_excluded_chars == 0
    assert asdict(document) == original
    assert "CORE_INSTRUCTIONS" not in prepared.prompt
    assert "TAXONOMY_GUIDANCE" not in prepared.prompt
    assert "AGENT_INSTRUCTIONS" not in prepared.prompt


def test_build_document_prompt_excludes_annex_and_preserves_metadata() -> None:
    substantive = "A" * MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX
    heading = "ANEXO: RELACIÓN DE BIENES Y DERECHOS AFECTADOS"
    excluded = f"\n{heading}\nTexto que no debe llegar al prompt."
    document = _document(text=substantive + excluded)
    original = asdict(document)

    prepared = build_document_prompt(document)

    assert f"<BOE_DOCUMENT>\n{substantive}\n</BOE_DOCUMENT>" in prepared.prompt
    assert heading not in prepared.prompt
    assert "Texto que no debe llegar al prompt." not in prepared.prompt
    assert prepared.input_text_chars == len(substantive)
    assert prepared.input_text_sha256 == sha256(
        substantive.encode("utf-8")
    ).hexdigest()
    assert (
        prepared.input_selection_strategy
        == "before_affected_assets_annex"
    )
    assert prepared.input_selection_marker == heading
    assert prepared.input_excluded_chars == len(excluded)
    assert asdict(document) == original
    assert build_document_prompt(document) == prepared


def _top_level_nodes(source: str) -> dict[str, ast.AST]:
    nodes: dict[str, ast.AST] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            nodes[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            for target in targets:
                if isinstance(target, ast.Name):
                    nodes[target.id] = node
    return nodes


def test_document_functions_numeric_constants_and_regex_match_notebook_ast() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (
            project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb"
        ).read_text(encoding="utf-8")
    )
    notebook_nodes: dict[str, ast.AST] = {}
    for cell_index in (7, 9):
        notebook_nodes.update(
            _top_level_nodes("".join(notebook["cells"][cell_index]["source"]))
        )
    module_source = (
        project_root
        / "src"
        / "renewables_permitting"
        / "extraction"
        / "documents.py"
    ).read_text(encoding="utf-8")
    module_nodes = _top_level_nodes(module_source)
    expected_names = {
        "MAX_DOCUMENT_CHARS",
        "MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX",
        "_AFFECTED_ASSETS_ANNEX_HEADING_RE",
        "_required_text",
        "_required_date",
        "_source_document_hash",
        "build_source_document",
        "select_document_text",
        "build_document_prompt",
    }

    assert expected_names <= notebook_nodes.keys()
    assert expected_names <= module_nodes.keys()
    for name in expected_names:
        assert ast.dump(module_nodes[name], include_attributes=False) == ast.dump(
            notebook_nodes[name],
            include_attributes=False,
        ), name


def test_document_prompt_template_matches_notebook_literally() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (
            project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb"
        ).read_text(encoding="utf-8")
    )
    notebook_source = "".join(notebook["cells"][7]["source"])
    module_source = (
        project_root
        / "src"
        / "renewables_permitting"
        / "extraction"
        / "documents.py"
    ).read_text(encoding="utf-8")
    notebook_node = _top_level_nodes(notebook_source)[
        "DOCUMENT_PROMPT_TEMPLATE"
    ]
    module_node = _top_level_nodes(module_source)["DOCUMENT_PROMPT_TEMPLATE"]

    assert DOCUMENT_PROMPT_TEMPLATE == (
        "Analiza exclusivamente la publicación delimitada a continuación.\n"
        "No reproduzcas boe_id ni publication_date en BOEAIExtraction.\n\n"
        "BOE_ID: {boe_id}\n"
        "FECHA_PUBLICACION: {publication_date}\n"
        "TITULO: {title}\n"
        "ESTRATEGIA_TEXTO: {input_selection_strategy}\n\n"
        "<BOE_DOCUMENT>\n"
        "{document_text}\n"
        "</BOE_DOCUMENT>"
    )
    assert ast.get_source_segment(
        module_source,
        module_node,
    ) == ast.get_source_segment(
        notebook_source,
        notebook_node,
    )


def test_documents_module_has_no_agent_or_forbidden_module_dependencies() -> None:
    module_source = Path(documents_module.__file__).read_text(encoding="utf-8")

    assert "pydantic_ai" not in module_source
    assert "CORE_INSTRUCTIONS" not in module_source
    assert "AGENT_INSTRUCTIONS" not in module_source
    for forbidden_module in (
        "runner",
        "review",
        "paths",
        "persistence",
        "flatten",
    ):
        assert (
            f"renewables_permitting.extraction.{forbidden_module}"
            not in module_source
        )
    assert MAX_DOCUMENT_CHARS is None
