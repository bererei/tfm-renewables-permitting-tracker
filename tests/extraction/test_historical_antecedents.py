import json
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
)
from renewables_permitting.extraction.corrections import (
    load_administrative_action_corrections,
)
from renewables_permitting.extraction.documents import build_source_document
from renewables_permitting.extraction.historical_antecedents import (
    POSSIBLE_HISTORICAL_ANTECEDENT_REASON_CODE,
    detect_possible_historical_antecedents,
    reconcile_historical_antecedent_findings,
)
from renewables_permitting.extraction.historical_antecedent_reviews import (
    HISTORICAL_ANTECEDENT_REVIEW_COLUMNS,
    load_historical_antecedent_reviews,
)
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    BOEProjectExtraction,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationType,
    PublicationEvent,
)
from renewables_permitting.extraction.review import (
    build_quality_metric,
    build_review_queue,
    normalise_ai_extraction_attempts_log,
)
from renewables_permitting.pipeline import (
    ExtractionStageResult,
    PipelineError,
    load_extraction_snapshot,
    recanonicalize_extraction_snapshot,
    run_extraction_stage,
    run_silver_stage,
)


CORRECTIONS_PATH = Path(
    "config/corrections/administrative_action_corrections.csv"
)

_TITLE_17979 = (
    "Resolución de 21 de julio de 2023, de la Dirección General de Política "
    "Energética y Minas, por la que se otorga a Arena Power Solar 33, SLU, "
    "autorización administrativa previa para la planta solar fotovoltaica "
    "Campos del Condado IV, de 57,295 MW de potencia instalada y su "
    "infraestructura de evacuación, en Beas y Trigueros (Huelva)."
)
_TITLE_17939 = (
    "Resolución de 31 de julio de 2026, de la Dirección General de Política "
    "Energética y Minas, por la que se otorga a Urso Solar, SLU, autorización "
    "administrativa previa y autorización administrativa de construcción del "
    "módulo de almacenamiento por baterías «Don Rodrigo II», de 39,6 MW de "
    "potencia instalada, y para su infraestructura de evacuación, para su "
    "hibridación con el parque solar fotovoltaico existente «Don Rodrigo II», "
    "de 45,6 MW de potencia instalada, en Utrera (Sevilla)."
)
_TITLE_30392 = (
    "Anuncio de la Dependencia de Industria y Energía de la Subdelegación del "
    "Gobierno en Cuenca, por el que se somete al trámite de Información "
    "Pública la Solicitud de Autorización Administrativa Previa y la Solicitud "
    "de Autorización Administrativa de Construcción para los módulos de "
    "almacenamiento por baterías: ALM Aspe, ALM Bañuela, ALM Turbón y ALM "
    "Aitana, de 21,69MW cada uno, para su hibridación con los parques "
    "fotovoltaicos existentes y su infraestructura de evacuación, en la "
    "provincia de Cuenca. PFot-ALM-071 AC."
)
_TITLE_26938 = (
    "Resolución del 26 de junio de 2026 de la Delegación Territorial en "
    "Sevilla de Economía, Hacienda, Fondos Europeos y de Industria, Energía y "
    "Minas, por la que se concede a favor de la mercantil Marchena PV, S.L., "
    "la Autorización Administrativa Previa y la Autorización Administrativa "
    "de Construcción para la implantación de la instalación de generación de "
    "energía eléctrica denominada \"FV DONATOS\" con una potencia instalada de "
    "5 MW, ubicada en el término municipal de El Cuervo de Sevilla (Sevilla) "
    "y la Declaración en concreto de Utilidad Pública para la infraestructura "
    "eléctrica de evacuación asociada."
)

_DIA_17979 = (
    "habiendo sido formulada declaración de impacto ambiental favorable, "
    "concretada mediante Resolución de 20 de abril de 2023 de la Dirección "
    "General de Calidad y Evaluación Ambiental del Ministerio para la "
    "Transición Ecológica y el Reto Demográfico"
)
_REQUEST_17939 = (
    "Urso Solar, SLU, en adelante, el promotor, solicitó, con fecha 29 de "
    "septiembre de 2025, subsanada con fecha 28 de noviembre de 2025, "
    "autorización administrativa previa, autorización administrativa de "
    "construcción y evaluación ambiental simplificada para el módulo de "
    "almacenamiento por baterías «Don Rodrigo II»"
)
_REMEDIATION_17939 = "subsanada con fecha 28 de noviembre de 2025"
_ENVIRONMENTAL_REQUEST_17939 = (
    "El promotor solicitó, con fecha 28 de noviembre de 2025, subsanada en "
    "fecha 16 de enero y 20 de febrero de 2026, la exención del procedimiento "
    "de evaluación ambiental simplificada del módulo de almacenamiento por "
    "baterías «Don Rodrigo II»"
)
_PUBLIC_INFO_17939 = (
    "la petición fue sometida a información pública, de conformidad con lo "
    "previsto en el referido Real Decreto 1955/2000, de 1 de diciembre, con "
    "la publicación el 23 de abril de 2026 en el «Boletín Oficial del Estado» "
    "y el 24 de abril de 2026 en el «Boletín Oficial de la Provincia de "
    "Sevilla»."
)
_IIA_30392 = {
    "Aspe": (
        'se formula informe de impacto ambiental del proyecto "Módulos de '
        'almacenamiento de energía por baterías "Aspe" [...] y su '
        "infraestructura de evacuación [...] en el sentido de que no es "
        "necesario el sometimiento al procedimiento de evaluación ambiental "
        "ordinaria de dicho proyecto, ya que no se prevén efectos adversos "
        "significativos sobre el medio ambiente"
    ),
    "Bañuela": (
        'se formula informe de impacto ambiental del proyecto "Módulos de '
        'almacenamiento de energía por baterías [...] "Bañuela" [...] y su '
        "infraestructura de evacuación [...] en el sentido de que no es "
        "necesario el sometimiento al procedimiento de evaluación ambiental "
        "ordinaria de dicho proyecto, ya que no se prevén efectos adversos "
        "significativos sobre el medio ambiente"
    ),
    "Turbón": (
        'se formula informe de impacto ambiental del proyecto "Módulos de '
        'almacenamiento de energía por baterías [...] "Turbón" [...] y su '
        "infraestructura de evacuación [...] en el sentido de que no es "
        "necesario el sometimiento al procedimiento de evaluación ambiental "
        "ordinaria de dicho proyecto, ya que no se prevén efectos adversos "
        "significativos sobre el medio ambiente"
    ),
    "Aitana": (
        'se formula informe de impacto ambiental del proyecto "Módulos de '
        'almacenamiento de energía por baterías [...] "Aitana" [...] y su '
        "infraestructura de evacuación [...] en el sentido de que no es "
        "necesario el sometimiento al procedimiento de evaluación ambiental "
        "ordinaria de dicho proyecto, ya que no se prevén efectos adversos "
        "significativos sobre el medio ambiente"
    ),
}
_ENVIRONMENTAL_QUALIFICATION_26938 = (
    "aporta resolución de calificación ambiental favorable emitida con fecha "
    "18 de Junio de 2026 por el Ayuntamiento de El Cuervo de Sevilla"
)
_TERRITORIAL_REPORT_26938 = (
    "emite informe favorable sobre la incidencia territorial de la actuación "
    "proyectada"
)


def _action(
    action_type: AdministrativeActionType,
    decision: AdministrativeDecision,
    evidence: str,
) -> AdministrativeAction:
    return AdministrativeAction(
        action_type=action_type,
        decision=decision,
        targets=["event"],
        evidence=evidence,
    )


def _event(actions: list[AdministrativeAction], name: str) -> PublicationEvent:
    return PublicationEvent(
        generation_assets=[GenerationAssetMention(
            local_generation_asset_ref="generation_asset_1",
            names_raw=[name],
            generation_type=GenerationType.PHOTOVOLTAIC,
            evidence=name,
        )],
        administrative_actions=actions,
        event_summary=f"Evento de {name}",
    )


def _extraction(
    boe_id: str,
    publication_date: date,
    events: list[PublicationEvent],
) -> BOEProjectExtraction:
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Proyecto de generación identificado.",
        publication_events=events,
        boe_id=boe_id,
        publication_date=publication_date,
    )


def _document_row(
    boe_id: str,
    publication_date: date,
    title: str,
    text: str,
) -> pd.Series:
    return pd.Series({
        "identificador": boe_id,
        "fecha_publicacion": pd.Timestamp(publication_date),
        "titulo": title,
        "xml_status": "ok",
        "texto_limpio": text,
    })


def _replay_documents() -> list[tuple[pd.Series, BOEProjectExtraction]]:
    current_17979 = _action(
        AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
        AdministrativeDecision.AUTHORIZED,
        _TITLE_17979,
    )
    extraction_17979 = _extraction(
        "BOE-A-2023-17979",
        date(2023, 8, 5),
        [_event([
            current_17979,
            _action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
                AdministrativeDecision.FAVORABLE,
                _DIA_17979,
            ),
        ], "Campos del Condado IV")],
    )
    row_17979 = _document_row(
        extraction_17979.boe_id,
        extraction_17979.publication_date,
        _TITLE_17979,
        (
            f"{_TITLE_17979} {_DIA_17979}. Como consecuencia de lo "
            "anteriormente expuesto, esta Dirección General resuelve: Único. "
            "Otorgar autorización administrativa previa."
        ),
    )

    extraction_17939 = _extraction(
        "BOE-A-2026-17939",
        date(2026, 8, 19),
        [_event([
            _action(
                AdministrativeActionType.APPLICATION_SUBMISSION,
                AdministrativeDecision.REQUESTED,
                _REQUEST_17939,
            ),
            _action(
                AdministrativeActionType.DOCUMENTATION_CORRECTION,
                AdministrativeDecision.CORRECTED,
                _REMEDIATION_17939,
            ),
            _action(
                AdministrativeActionType.ENVIRONMENTAL_APPLICATION_SUBMISSION,
                AdministrativeDecision.REQUESTED,
                _ENVIRONMENTAL_REQUEST_17939,
            ),
            _action(
                AdministrativeActionType.PUBLIC_INFORMATION,
                AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                _PUBLIC_INFO_17939,
            ),
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                _TITLE_17939,
            ),
            _action(
                AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                _TITLE_17939,
            ),
        ], "Don Rodrigo II")],
    )
    row_17939 = _document_row(
        extraction_17939.boe_id,
        extraction_17939.publication_date,
        _TITLE_17939,
        " ".join([
            _TITLE_17939,
            _REQUEST_17939,
            _ENVIRONMENTAL_REQUEST_17939,
            _PUBLIC_INFO_17939,
            "Como consecuencia de lo anteriormente expuesto, esta Dirección "
            "General resuelve: Primero. Otorgar autorización administrativa "
            "previa. Segundo. Otorgar autorización administrativa de "
            "construcción.",
        ]),
    )

    current_actions_30392 = [
        _action(
            AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
            AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
            _TITLE_30392,
        ),
        _action(
            AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
            AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
            _TITLE_30392,
        ),
    ]
    events_30392 = [
        _event([
            *deepcopy(current_actions_30392),
            _action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
                AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
                evidence,
            ),
        ], name)
        for name, evidence in _IIA_30392.items()
    ]
    extraction_30392 = _extraction(
        "BOE-B-2025-30392",
        date(2025, 8, 23),
        events_30392,
    )
    row_30392 = _document_row(
        extraction_30392.boe_id,
        extraction_30392.publication_date,
        _TITLE_30392,
        (
            f"{_TITLE_30392} Por resolución de 7 de mayo de 2025 de la "
            "Dirección General de Calidad y Evaluación Ambiental, "
            "se formula informe de impacto ambiental del proyecto \"Módulos "
            "de almacenamiento de energía por baterías \"Aspe\", \"Bañuela\", "
            "\"Turbón\" y \"Aitana\", de 21,89 MW cada una, para su "
            "hibridación con parques fotovoltaicos existentes, y su "
            "infraestructura de evacuación en el término municipal de "
            "Altarejos (Cuenca)\", en el sentido de que no es necesario el "
            "sometimiento al procedimiento de evaluación ambiental ordinaria "
            "de dicho proyecto, ya que no se prevén efectos adversos "
            "significativos sobre el medio ambiente."
        ),
    )

    extraction_26938 = _extraction(
        "BOE-B-2026-26938",
        date(2026, 8, 13),
        [_event([
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                _TITLE_26938,
            ),
            _action(
                AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                _TITLE_26938,
            ),
            _action(
                AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
                AdministrativeDecision.DECLARED,
                _TITLE_26938,
            ),
            _action(
                AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
                AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
                _ENVIRONMENTAL_QUALIFICATION_26938,
            ),
            _action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.FAVORABLE,
                _TERRITORIAL_REPORT_26938,
            ),
        ], "FV DONATOS")],
    )
    row_26938 = _document_row(
        extraction_26938.boe_id,
        extraction_26938.publication_date,
        _TITLE_26938,
        (
            f"{_TITLE_26938} Antecedentes de hecho. Tercero. "
            f"{_ENVIRONMENTAL_QUALIFICATION_26938}. Cuarto. Con fecha 17 de "
            f"enero de 2025 la Delegación {_TERRITORIAL_REPORT_26938}. "
            "Fundamentos de Derecho. Por todo lo expuesto, esta Delegación "
            "resuelve. Primero. Conceder las autorizaciones y declarar la "
            "utilidad pública."
        ),
    )
    return [
        (row_17979, extraction_17979),
        (row_17939, extraction_17939),
        (row_30392, extraction_30392),
        (row_26938, extraction_26938),
    ]


def _negative_controls() -> list[tuple[pd.Series, BOEProjectExtraction]]:
    controls = [
        (
            "BOE-A-2025-13976",
            date(2025, 7, 7),
            "Resolución de 26 de junio de 2025, de la Dirección General de "
            "Calidad y Evaluación Ambiental, por la que se formula declaración "
            "de impacto ambiental del proyecto «Módulo de almacenamiento por "
            "baterías \"Hibridación Zafra\", de 24,04 MW de potencia, para su "
            "hibridación con la planta fotovoltaica existente, \"Hsf Zafra\", "
            "de 49,99 MW de potencia instalada, y para parte de su "
            "infraestructura de evacuación (Sevilla)».",
            AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
            AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
            "Resolución de 26 de junio de 2025, de la Dirección General de "
            "Calidad y Evaluación Ambiental, por la que se formula declaración "
            "de impacto ambiental del proyecto «Módulo de almacenamiento por "
            "baterías \"Hibridación Zafra\" [...] que no es necesario el "
            "sometimiento al procedimiento de evaluación ambiental ordinaria "
            "del proyecto [...] ya que no se prevén efectos adversos "
            "significativos sobre el medio ambiente",
        ),
        (
            "BOE-B-2026-26871",
            date(2026, 8, 12),
            "Resolución de la Delegación Territorial de Economía, Hacienda y "
            "Fondos Europeos y de Industria, Energía y Minas en Granada, por "
            "la que se declara, en concreto, de utilidad pública, el proyecto "
            "denominado «Línea Subterránea L/30 kV CS Cortijo - Molino – SET "
            "Dama de Baza y Planta Solar Fotovoltaica El Cortijo», en el "
            "término municipal de Huéneja (Granada).",
            AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
            AdministrativeDecision.DECLARED,
            "Declarar, en concreto, de utilidad pública, la instalación "
            "eléctrica promovida por la entidad Amapola Desarrollos España, "
            "S.L., denominada «Línea Subterránea L/30 kV CS Cortijo - Molino – "
            "SET Dama de Baza y Planta Solar Fotovoltaica El Cortijo»",
        ),
        (
            "BOE-B-2026-27230",
            date(2026, 8, 17),
            "Acuerdo GOV/202/2026 del Gobierno de la Generalitat de Catalunya, "
            "de 28 de julio, por el que se declara la utilidad pública del "
            "Proyecto del parque eólico Tivissa III y de sus infraestructuras "
            "de evacuación, y su prevalencia sobre la utilidad pública del "
            "monte Comuns de la Vila, núm. 31, del Catálogo de Montes de "
            "Utilidad Pública de Tarragona, y sobre la utilidad pública del "
            "monte Maleses i Garrigues, núm. 56, del Catálogo de montes de "
            "utilidad pública de Tarragona.",
            AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
            AdministrativeDecision.DECLARED,
            "Declarar la utilidad pública del Proyecto del parque eólico "
            "Tivissa III y de sus infraestructuras de evacuación",
        ),
        (
            "BOE-B-2026-27231",
            date(2026, 8, 17),
            "Acuerdo GOV/201/2026 del Gobierno de la Generalitat de Catalunya, "
            "de 28 de julio, por el que se declara la utilidad pública del "
            "Proyecto del parque eólico Tivissa IV y de sus infraestructuras "
            "de evacuación, y su prevalencia sobre la utilidad pública del "
            "monte Comuns de la Vila, núm. 31, del Catálogo de Montes de "
            "Utilidad Pública de Tarragona.",
            AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
            AdministrativeDecision.DECLARED,
            "Declarar la utilidad pública del Proyecto del parque eólico "
            "Tivissa IV y de sus infraestructuras de evacuación",
        ),
        (
            "BOE-B-2026-27384",
            date(2026, 8, 19),
            "Resolución de 3 de agosto de 2026 de la Dirección General de "
            "Industria, Energía y Minas, de la Consejería de Industria, "
            "Energía, Ciencia y Territorio, por la que se declara, en "
            "concreto, de utilidad pública, la instalación fotovoltaica \"CSF "
            "Arco I\", ubicada en el término municipal de Malpartida de "
            "Cáceres (Cáceres), e infraestructura de evacuación de energía "
            "eléctrica asociada, expediente GE-M/03/22.",
            AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
            AdministrativeDecision.DECLARED,
            "Resolución [...] por la que se declara, en concreto, de utilidad "
            "pública, la instalación fotovoltaica \"CSF Arco I\" [...] e "
            "infraestructura de evacuación de energía eléctrica asociada",
        ),
    ]
    result = []
    for boe_id, publication_date, title, action_type, decision, evidence in controls:
        extraction = _extraction(
            boe_id,
            publication_date,
            [_event([_action(action_type, decision, evidence)], "Proyecto")],
        )
        row = _document_row(
            boe_id,
            publication_date,
            title,
            (
                f"Antecedentes de hecho. Referencias del expediente. "
                f"Fundamentos de Derecho. El Gobierno resuelve: {evidence}."
            ),
        )
        result.append((row, extraction))
    return result


def _attempts_and_sources(
    examples: list[tuple[pd.Series, BOEProjectExtraction]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_records = []
    attempt_records = []
    for position, (row, extraction) in enumerate(examples, start=1):
        document = build_source_document(row)
        source_record = row.to_dict()
        source_record["source_document_sha256"] = (
            document.source_document_sha256
        )
        source_records.append(source_record)
        attempt_records.append({
            "attempt_id": f"attempt-{position}",
            "identificador_boe": extraction.boe_id,
            "fecha_publicacion": pd.Timestamp(extraction.publication_date),
            "titulo": document.title,
            "source_document_sha256": document.source_document_sha256,
            "extraction_config_id": EXTRACTION_CONFIG_ID,
            "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
            "instructions_sha256": INSTRUCTIONS_SHA256,
            "model_provider": MODEL_PROVIDER,
            "model_name": AI_MODEL_NAME,
            "document_validation_version": DOCUMENT_VALIDATION_VERSION,
            "classification_status": "classified",
            "classification_reason": extraction.classification_reason,
            "extraction_json": extraction.model_dump_json(),
            "extracted_at": pd.Timestamp(
                "2026-08-27T12:00:00Z"
            ),
            "extraction_status": "ok",
            "processing_stage": "completed",
            "document_validation_status": "passed",
        })
    return (
        normalise_ai_extraction_attempts_log(pd.DataFrame(attempt_records)),
        pd.DataFrame(source_records),
    )


def _write_current_reviews(tmp_path: Path, findings):
    records = [{
        "review_version": 1,
        "status": "approved",
        "outcome": "current",
        "boe_id": finding.boe_id,
        "administrative_action_id": finding.administrative_action_id,
        "source_document_sha256": finding.source_document_sha256,
        "expected_action_type": finding.action_type,
        "expected_decision": finding.decision,
        "expected_evidence_sha256": finding.evidence_sha256,
        "reason_code": finding.reason_code,
        "detector_policy_version": finding.detector_policy_version,
        "review_reason": "La acción es vigente y el warning es falso positivo.",
        "decision_source": "human_review:p0-current-regression",
        "reviewed_on": "2026-08-27",
        "reviewer": "human_tfm_review",
    } for finding in findings]
    path = tmp_path / "historical_antecedent_reviews.csv"
    pd.DataFrame(
        records,
        columns=HISTORICAL_ANTECEDENT_REVIEW_COLUMNS,
    ).to_csv(path, index=False)
    return load_historical_antecedent_reviews(path)


def test_known_temporal_audit_replay_detects_11_of_11_and_zero_of_five():
    positives = []
    for row, extraction in _replay_documents():
        positives.extend(detect_possible_historical_antecedents(
            document=build_source_document(row),
            extraction=extraction,
        ))
    negative_findings = []
    for row, extraction in _negative_controls():
        negative_findings.extend(detect_possible_historical_antecedents(
            document=build_source_document(row),
            extraction=extraction,
        ))

    expected_positive_ids = {
        "BOE-A-2023-17979_event_1_action_2",
        *{
            f"BOE-A-2026-17939_event_1_action_{index}"
            for index in range(1, 5)
        },
        *{
            f"BOE-B-2025-30392_event_{index}_action_3"
            for index in range(1, 5)
        },
        "BOE-B-2026-26938_event_1_action_4",
        "BOE-B-2026-26938_event_1_action_5",
    }
    assert {item.administrative_action_id for item in positives} == (
        expected_positive_ids
    )
    assert len(positives) == 11
    assert negative_findings == []


def test_replay_fingerprints_match_11_approved_versioned_corrections():
    findings = tuple(
        finding
        for row, extraction in _replay_documents()
        for finding in detect_possible_historical_antecedents(
            document=build_source_document(row),
            extraction=extraction,
        )
    )
    corrections = load_administrative_action_corrections(CORRECTIONS_PATH)
    reconciled = reconcile_historical_antecedent_findings(
        findings,
        corrections,
    )

    assert len(reconciled.resolved) == 11
    assert reconciled.pending == ()
    assert all(
        item.correction_id.startswith("historical-action-exclusion-v1-")
        for item in reconciled.resolved
    )


def test_detector_is_pure_deterministic_and_preserves_action_evidence():
    row, extraction = _replay_documents()[1]
    before = deepcopy(extraction.model_dump())
    document = build_source_document(row)

    first = detect_possible_historical_antecedents(
        document=document,
        extraction=extraction,
    )
    second = detect_possible_historical_antecedents(
        document=document,
        extraction=extraction,
    )

    assert first == second
    assert extraction.model_dump() == before
    assert len(extraction.publication_events[0].administrative_actions) == 6
    assert first[0].evidence == _REQUEST_17939


def test_unlocatable_or_unordered_composite_evidence_is_not_flagged():
    evidence = (
        "solicitó el 1 de enero de 2024 [...] fragmento inexistente"
    )
    extraction = _extraction(
        "BOE-A-2026-10001",
        date(2026, 1, 1),
        [_event([_action(
            AdministrativeActionType.APPLICATION_SUBMISSION,
            AdministrativeDecision.REQUESTED,
            evidence,
        )], "Aurora")],
    )
    row = _document_row(
        extraction.boe_id,
        extraction.publication_date,
        "Resolución por la que se autoriza Aurora.",
        (
            "Antecedentes de hecho. solicitó el 1 de enero de 2024. "
            "Esta Dirección General resuelve: Autorizar Aurora."
        ),
    )

    assert detect_possible_historical_antecedents(
        document=build_source_document(row), extraction=extraction
    ) == ()


def test_isolated_old_date_and_fundamentos_alone_are_not_sufficient():
    evidence = "Consta la fecha 1 de enero de 2024 en el expediente"
    extraction = _extraction(
        "BOE-A-2026-10002",
        date(2026, 1, 1),
        [_event([_action(
            AdministrativeActionType.OTHER,
            AdministrativeDecision.FAVORABLE,
            evidence,
        )], "Aurora")],
    )
    row = _document_row(
        extraction.boe_id,
        extraction.publication_date,
        "Resolución sobre Aurora.",
        (
            f"Fundamentos de Derecho. {evidence}. Esta Dirección General "
            "resuelve: Autorizar Aurora."
        ),
    )

    assert detect_possible_historical_antecedents(
        document=build_source_document(row), extraction=extraction
    ) == ()


def test_repeated_historical_and_operative_occurrence_is_conservative():
    evidence = "la petición fue sometida el 1 de enero de 2025"
    extraction = _extraction(
        "BOE-A-2026-10003",
        date(2026, 1, 1),
        [_event([_action(
            AdministrativeActionType.PUBLIC_INFORMATION,
            AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
            evidence,
        )], "Aurora")],
    )
    row = _document_row(
        extraction.boe_id,
        extraction.publication_date,
        "Resolución sobre Aurora.",
        (
            f"Antecedentes de hecho. {evidence}. Fundamentos de Derecho. "
                f"Esta Dirección General resuelve: "
                f"{evidence.replace('[...]', ' contenido documental ')}."
        ),
    )

    assert detect_possible_historical_antecedents(
        document=build_source_document(row), extraction=extraction
    ) == ()


def test_proposed_antecedent_outcome_is_flagged_but_current_outcome_is_not():
    proposed = (
        "el órgano propuso el 1 de junio de 2025 que no era necesaria la "
        "evaluación ambiental ordinaria"
    )
    current = (
        "resuelve la formulación de informe de determinación de afección "
        "ambiental en el sentido de que el proyecto se someta a evaluación "
        "ambiental ordinaria"
    )
    extraction = _extraction(
        "BOE-A-2025-17072",
        date(2025, 8, 13),
        [_event([
            _action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
                AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
                proposed,
            ),
            _action(
                AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
                AdministrativeDecision.ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
                current,
            ),
        ], "PFVH Mirabel")],
    )
    row = _document_row(
        extraction.boe_id,
        extraction.publication_date,
        "Resolución por la que se formula informe de determinación de "
        "afección ambiental de PFVH Mirabel.",
        (
            f"Antecedentes de hecho. {proposed}. Fundamentos de Derecho. "
            f"Esta Dirección General {current}."
        ),
    )

    findings = detect_possible_historical_antecedents(
        document=build_source_document(row), extraction=extraction
    )
    assert [item.administrative_action_id for item in findings] == [
        "BOE-A-2025-17072_event_1_action_1"
    ]


def test_review_queue_aggregates_action_findings_without_changing_json():
    examples = [_replay_documents()[1]]
    attempts, sources = _attempts_and_sources(examples)
    extraction_json = attempts.iloc[0]["extraction_json"]

    queue = build_review_queue(
        attempts=attempts,
        source_df=sources,
        enable_historical_antecedent_safeguard=True,
    )

    assert len(queue) == 1
    row = queue.iloc[0]
    diagnostics = json.loads(row["validation_issues_json"])
    assert row["reason_code"] == POSSIBLE_HISTORICAL_ANTECEDENT_REASON_CODE
    assert row["reason_severity"] == "blocking"
    assert row["queue_status"] == "pending"
    assert row["proposed_extraction_json"] == extraction_json
    assert len(diagnostics) == 4
    assert all(item["temporal_signals"] for item in diagnostics)
    assert all(item["contextual_signals"] for item in diagnostics)

    metric = build_quality_metric(
        attempts=attempts,
        source_df=sources,
        manual_reviews=None,
        run_scope="regression",
        enable_historical_antecedent_safeguard=True,
    ).iloc[0]
    assert metric["n_review_required"] == 1
    assert metric["quality_status"] == "degraded"


def test_current_review_resolves_only_exact_finding_without_mutating_extraction(
    tmp_path: Path,
):
    row, extraction = _replay_documents()[1]
    original_json = extraction.model_dump_json()
    findings = detect_possible_historical_antecedents(
        document=build_source_document(row),
        extraction=extraction,
    )
    current_reviews = _write_current_reviews(tmp_path, findings[:1])

    reconciliation = reconcile_historical_antecedent_findings(
        findings,
        corrections=None,
        current_reviews=current_reviews,
    )

    assert len(reconciliation.resolved) == 1
    assert reconciliation.resolved[0].resolution_kind == "current_validation"
    assert reconciliation.resolved[0].correction_id is None
    assert reconciliation.resolved[0].review_decision_id is not None
    assert [item.administrative_action_id for item in reconciliation.pending] == [
        item.administrative_action_id for item in findings[1:]
    ]
    assert extraction.model_dump_json() == original_json

    changed_fingerprint = reconcile_historical_antecedent_findings(
        (replace(findings[0], evidence_sha256="0" * 64),),
        corrections=None,
        current_reviews=current_reviews,
    )
    assert len(changed_fingerprint.pending) == 1
    assert changed_fingerprint.resolved == ()


def test_current_review_registry_identity_is_row_order_independent(
    tmp_path: Path,
):
    row, extraction = _replay_documents()[1]
    findings = detect_possible_historical_antecedents(
        document=build_source_document(row),
        extraction=extraction,
    )
    first = _write_current_reviews(tmp_path, findings[:2])
    reversed_path = tmp_path / "historical_antecedent_reviews_reversed.csv"
    first.reviews.iloc[::-1].to_csv(reversed_path, index=False)
    second = load_historical_antecedent_reviews(reversed_path)

    assert first.semantic_identity == second.semantic_identity
    assert first.file_sha256 != second.file_sha256


def test_boe_queue_keeps_unresolved_action_when_sibling_is_current(
    tmp_path: Path,
):
    request_evidence = (
        "el promotor solicitó el 1 de enero de 2025 autorización previa"
    )
    public_information_evidence = (
        "la petición fue sometida el 2 de febrero de 2025 a información pública"
    )
    extraction = _extraction(
        "BOE-A-2026-10007",
        date(2026, 1, 1),
        [_event([
            _action(
                AdministrativeActionType.APPLICATION_SUBMISSION,
                AdministrativeDecision.REQUESTED,
                request_evidence,
            ),
            _action(
                AdministrativeActionType.PUBLIC_INFORMATION,
                AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                public_information_evidence,
            ),
        ], "Aurora")],
    )
    row = _document_row(
        extraction.boe_id,
        extraction.publication_date,
        "Resolución por la que se otorga autorización previa a la planta "
        "solar fotovoltaica Aurora.",
        (
            f"Antecedentes de hecho. {request_evidence}. "
            f"{public_information_evidence}. Fundamentos de Derecho. "
            "Esta Dirección General resuelve: Otorgar autorización previa a "
            "la planta solar fotovoltaica Aurora."
        ),
    )
    example = (row, extraction)
    attempts, sources = _attempts_and_sources([example])
    findings = detect_possible_historical_antecedents(
        document=build_source_document(example[0]),
        extraction=example[1],
    )
    current_reviews = _write_current_reviews(tmp_path, findings[:1])

    queue = build_review_queue(
        attempts=attempts,
        source_df=sources,
        enable_historical_antecedent_safeguard=True,
        historical_antecedent_reviews=current_reviews,
    )

    assert len(queue) == 1
    diagnostics = json.loads(queue.iloc[0]["validation_issues_json"])
    assert [item["administrative_action_id"] for item in diagnostics] == [
        item.administrative_action_id for item in findings[1:]
    ]
    assert len(diagnostics) == 1
    manual_reviews = pd.DataFrame([{
        "manual_review_id": pd.NA,
        "identificador_boe": example[1].boe_id,
        "source_document_sha256": attempts.iloc[0][
            "source_document_sha256"
        ],
        "source_attempt_id": attempts.iloc[0]["attempt_id"],
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "review_status": "manually_validated",
        "corrected_extraction_json": example[1].model_dump_json(),
        "reviewer": "human_tfm_review",
        "review_notes": "Validación genérica sin decisión histórica.",
        "reviewed_at_utc": pd.Timestamp("2026-08-27T13:00:00Z"),
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }])
    queue_after_generic_review = build_review_queue(
        attempts=attempts,
        source_df=sources,
        manual_reviews=manual_reviews,
        enable_historical_antecedent_safeguard=True,
        historical_antecedent_reviews=current_reviews,
    )
    assert len(queue_after_generic_review) == 1
    assert queue_after_generic_review.iloc[0]["source_attempt_id"] != (
        attempts.iloc[0]["attempt_id"]
    )
    assert [
        item["administrative_action_id"]
        for item in json.loads(
            queue_after_generic_review.iloc[0]["validation_issues_json"]
        )
    ] == [item.administrative_action_id for item in findings[1:]]

    metric = build_quality_metric(
        attempts=attempts,
        source_df=sources,
        manual_reviews=manual_reviews,
        run_scope="regression",
        enable_historical_antecedent_safeguard=True,
        historical_antecedent_reviews=current_reviews,
    ).iloc[0]
    assert metric["n_review_required"] == 1
    assert metric["quality_status"] == "degraded"


def test_approved_corrections_do_not_reopen_pending_review():
    examples = _replay_documents()
    attempts, sources = _attempts_and_sources(examples)
    corrections = load_administrative_action_corrections(CORRECTIONS_PATH)

    queue = build_review_queue(
        attempts=attempts,
        source_df=sources,
        enable_historical_antecedent_safeguard=True,
        historical_antecedent_corrections=corrections,
    )

    assert queue.empty


def test_existing_review_queue_behavior_is_unchanged_when_safeguard_disabled():
    source = pd.DataFrame([{
        "identificador": "BOE-A-2026-10004",
        "source_document_sha256": sha256(b"source").hexdigest(),
    }])
    attempts = normalise_ai_extraction_attempts_log(pd.DataFrame([{
        "attempt_id": "failed-attempt",
        "identificador_boe": "BOE-A-2026-10004",
        "source_document_sha256": source.iloc[0]["source_document_sha256"],
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "extraction_status": "error",
        "document_validation_status": pd.NA,
        "classification_status": pd.NA,
        "extracted_at": pd.Timestamp("2026-08-27T12:00:00Z"),
    }]))

    queue = build_review_queue(attempts=attempts, source_df=source)

    assert queue["reason_code"].tolist() == ["extraction_error"]
    assert queue["reason_severity"].tolist() == ["blocking"]


def test_extraction_snapshot_persists_safeguard_and_keeps_flagged_action(
    tmp_path: Path,
):
    evidence = (
        "el promotor solicitó el 1 de enero de 2025 autorización "
        "administrativa previa"
    )
    extraction = _extraction(
        "BOE-A-2026-10005",
        date(2026, 1, 1),
        [_event([_action(
            AdministrativeActionType.APPLICATION_SUBMISSION,
            AdministrativeDecision.REQUESTED,
            evidence,
        )], "Aurora")],
    )
    example = (
        _document_row(
            extraction.boe_id,
            extraction.publication_date,
            "Resolución por la que se otorga autorización a Aurora.",
            (
                f"Antecedentes de hecho. {evidence}. Fundamentos de Derecho. "
                "Esta Dirección General resuelve: Otorgar autorización a "
                "Aurora."
            ),
        ),
        extraction,
    )
    attempts, sources = _attempts_and_sources([example])
    documents_path = tmp_path / "documents.parquet"
    attempts_path = tmp_path / "attempts.parquet"
    output_dir = tmp_path / "extraction"
    sources.to_parquet(documents_path, index=False)
    attempts.to_parquet(attempts_path, index=False)

    result = run_extraction_stage(
        documents=documents_path,
        attempts=attempts_path,
        output_dir=output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert isinstance(result, ExtractionStageResult)
    assert result.blocking_review_count == 1
    persisted_current = pd.read_parquet(result.current_extractions_path)
    persisted_queue = pd.read_parquet(result.review_queue_path)
    assert persisted_current.iloc[0]["extraction_json"] == (
        extraction.model_dump_json()
    )
    assert json.loads(persisted_current.iloc[0]["extraction_json"])[
        "publication_events"
    ][0]["administrative_actions"][0]["evidence"] == evidence
    assert persisted_queue["reason_code"].tolist() == [
        POSSIBLE_HISTORICAL_ANTECEDENT_REASON_CODE
    ]
    assert (output_dir / "historical_antecedent_corrections.csv").is_file()
    assert (output_dir / "historical_antecedent_reviews.csv").is_file()

    loaded = load_extraction_snapshot(
        output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    assert len(loaded.current_extractions) == 1
    assert loaded.review_queue["reason_code"].tolist() == [
        POSSIBLE_HISTORICAL_ANTECEDENT_REASON_CODE
    ]


def test_current_review_survives_snapshot_reload_and_recanonicalization(
    tmp_path: Path,
):
    evidence = (
        "el promotor solicitó el 1 de enero de 2025 autorización "
        "administrativa previa"
    )
    extraction = _extraction(
        "BOE-A-2026-10006",
        date(2026, 1, 1),
        [_event([_action(
            AdministrativeActionType.APPLICATION_SUBMISSION,
            AdministrativeDecision.REQUESTED,
            evidence,
        )], "Aurora")],
    )
    row = _document_row(
        extraction.boe_id,
        extraction.publication_date,
        "Resolución por la que se otorga autorización a Aurora.",
        (
            f"Antecedentes de hecho. {evidence}. Fundamentos de Derecho. "
            "Esta Dirección General resuelve: Otorgar autorización a Aurora."
        ),
    )
    attempts, sources = _attempts_and_sources([(row, extraction)])
    finding = detect_possible_historical_antecedents(
        document=build_source_document(row),
        extraction=extraction,
    )[0]
    current_reviews = _write_current_reviews(tmp_path, (finding,))
    documents_path = tmp_path / "documents.parquet"
    attempts_path = tmp_path / "attempts.parquet"
    source_snapshot = tmp_path / "source-extraction"
    target_snapshot = tmp_path / "recanonicalized-extraction"
    sources.to_parquet(documents_path, index=False)
    attempts.to_parquet(attempts_path, index=False)

    result = run_extraction_stage(
        documents=documents_path,
        attempts=attempts_path,
        output_dir=source_snapshot,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        historical_antecedent_reviews=current_reviews.source_path,
    )
    assert result.blocking_review_count == 0
    assert pd.read_parquet(result.review_queue_path).empty
    persisted_json = pd.read_parquet(
        result.current_extractions_path
    ).iloc[0]["extraction_json"]
    assert persisted_json == extraction.model_dump_json()
    silver = run_silver_stage(
        extraction_snapshot=source_snapshot,
        output_dir=tmp_path / "silver",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    assert silver.output_dir.is_dir()

    with pytest.raises(PipelineError, match="CURRENT reviews drop or rewrite"):
        recanonicalize_extraction_snapshot(
            source_snapshot=source_snapshot,
            documents=documents_path,
            output_dir=tmp_path / "lost-current-provenance",
            source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            created_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        )

    recanonicalize_extraction_snapshot(
        source_snapshot=source_snapshot,
        documents=documents_path,
        output_dir=target_snapshot,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        historical_antecedent_reviews=current_reviews.source_path,
    )
    loaded = load_extraction_snapshot(
        target_snapshot,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    assert loaded.review_queue.empty
    assert BOEProjectExtraction.model_validate_json(
        str(loaded.current_extractions.iloc[0]["extraction_json"])
    ).model_dump() == extraction.model_dump()
