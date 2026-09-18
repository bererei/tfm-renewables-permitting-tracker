# Final Streamlit Product Alignment

## 1. Purpose

This document records the final alignment of the public, read-only Streamlit
product with the validated W14 Gold corpus. The application answers bounded
questions about projects, BOE publications, administrative associations,
published situations and documentary evidence. It does not execute or modify
the analytical pipeline.

> **Operational update (2026-08-27):** the active application default is the
> corrected Gold v2 at
> `data/gold/final-w14-corpus-20220101-20260820-v2-316008e9bfce550c651d4f6377090243a180c6b5192666327fc1ba2ff8eeef86`, with downstream
> ID `316008e9bfce550c651d4f6377090243a180c6b5192666327fc1ba2ff8eeef86`.
> This five-file immutable package is versioned so a clean checkout can run the
> app without `runs/` or evaluation artifacts. Streamlit Community Cloud is the
> intended target; public deployment and its URL remain pending.
> The v1 path and identity below are preserved as the input audited during the
> original product-alignment review.

## 2. Final Gold input

The default input at the time of this alignment audit was:

```text
runs/final-w14-corpus-20220101-20260820-v1/downstream/gold
```

Its expected downstream ID is:

```text
e3664ebb4efa0876262aed522d8c68e670c13c9ddee5f1fc0c8b76b74481b6e3
```

The existing contractual loader verifies the manifest, four exact tables,
physical and semantic hashes, schemas, dtypes, PK/FK relations and recomputed
downstream identity before returning any data. The validated row counts are:

| Table | Rows |
| --- | ---: |
| `projects` | 86 |
| `project_events` | 251 |
| `project_locations` | 453 |
| `project_location_sources` | 839 |

Operators may replace the default only by configuring a matching
`RENEWABLES_GOLD_DIR` and `RENEWABLES_EXPECTED_DOWNSTREAM_ID`.

## 3. Product scope

The public product contains a filtered summary, project catalogue, project
detail and methodology. The existing technical Gold explorer remains local,
read-only, disabled by default and separate from the public navigation.

The application never reads Silver, invokes extraction, downloads BOE,
contacts a model, edits reviews or writes Gold. Authentication, a persistent
reporting backend and an administrative correction interface remain POST-TFM.

## 4. KPI definitions

The summary contains exactly two primary KPIs, both recomputed from the active
filter selection:

- **Proyectos:** distinct `project_id` in the selected catalogue;
- **Publicaciones BOE relevantes:** distinct `boe_id` among the
  selected supporting event rows, never the number of `project_events` rows.

Without filters they return 86 and 80. The 104 analyzed documents and the
80/24 relevant/non-relevant split are methodological context, not a third
product KPI.

## 5. Filters

The shared sidebar exposes project text, technology, autonomous community,
province, municipality, publication year, inclusive publication dates,
administrative action, published situation, temporal interpretation and
any/all action matching. Values within a category use OR; active categories
compose with AND. Administrative predicates retain the existing same-row
semantics. Empty selections show a clear zero-result state.

Both annual charts, the administrative chart and the summary map are filter
inputs. A year applies its exact calendar interval; an administrative bar
applies its action and decision; and a polygon applies the equivalent
administrative hierarchy. Technology, autonomous-community, province and
municipality cells in the catalogue apply their structured values to the same
filter state. These native selections compose with the sidebar through one
AND-filtered selection consumed by every output. Their state is visible in the
sidebar. The primary **Limpiar filtros** action resets widgets and every chart,
map and table cross-filter.

## 6. Administrative map

The Summary choropleth uses one native segmented control with exactly
**Comunidades y ciudades autónomas**, **Provincias** and **Municipios**. The map
left-joins filtered distinct-`project_id` counts to the applicable official
administrative reference by code, never by name. Therefore all 19 communities
or autonomous cities, all 52 provinces and the 95 final-corpus municipalities
remain visible within their respective level when their count is zero. A
project may contribute to several polygons, so polygon counts are not summed as
the total number of projects.

The Vega/Altair map renderer is retired. Three human browser reviews found the
map invisible even after correcting its nested FeatureCollection payload and
then precomputing the projection and color domain. Those diagnoses remain
useful evidence, but passing Vega tests or producing paths outside the real app
did not satisfy the visual acceptance criterion.

The application uses separate Folium/Leaflet builders for the analytical map
and project detail. Both consume integrity-checked local vector assets: Natural
Earth countries for geographic orientation and IGN GeoJSON for Spanish
administrative boundaries. There is no tile layer, provider API key, watermark
or runtime map-data request. The analytical builder styles filtered
distinct-project counts, uses a neutral fill for zero, adds a territory/count
tooltip and keeps a stable viewport covering mainland Spain, Balearic and
Canary Islands, Ceuta and Melilla, Portugal, southern France and northern
Africa.

The general selector supports communities/autonomous cities, provinces and
municipalities. The first two levels retain the complete 19/52 reference. The
municipality level retains all 95 municipality codes represented by final Gold,
not all 8,132 Spanish municipalities; filtered counts are left-joined so a
corpus municipality remains visible with zero under unrelated filters.

Summary maps mount through `streamlit-folium` `st_folium()` and request only
`last_active_drawing`. A clicked GeoJSON feature returns its `level`, stable
administrative `code`, `name` and count. Python validates all four values
against the complete previous-map code set before synchronizing the
CCAA/province/municipality hierarchy. A known zero-count territory is safe to select; it may
produce a valid empty dashboard. Repeated or invalid events are ignored;
the shared chart epoch remounts a clean component after a valid selection or
**Limpiar filtros**. The detail map requests no returned objects and cannot
change global filters. At municipality precision it loads only the project's
municipal polygons, adds discrete parent province/community boundaries and
fits to the selected project territory rather than loading all municipalities.

The map means **projects associated with administrative territories according
to BOE publications**. It is not project density, installed capacity, precise
plant coordinates or facility footprints. The 83 projects with a resolved
territory are map-eligible; the other three remain in KPIs, catalogue,
chronology and administrative charts.

## 7. Temporal charts

The summary contains two separate annual charts:

- **Evolución de proyectos:** distinct projects with at least one observed
  publication in each year. It does not mean projects built or necessarily
  first observed in that year;
- **Evolución de publicaciones BOE:** distinct relevant `boe_id` by publication
  year. A BOE linked to several projects or actions is counted once.

The observed BOE counts are 5 in 2022, 14 in 2023, 10 in 2024, 17 in 2025 and
34 in 2026. Both are cohort-based corpus measures, not exhaustive annual BOE
statistics for Spain, and both expose the same year-selection interaction.

## 8. Administrative situations

The administrative chart derives the latest observed row for every
`project_id × action_type`, then counts distinct projects by action and
published decision. It does not count event-join multiplicity or claim a
legally definitive current status. All action and decision codes observed in
the final Gold have explicit Spanish labels. Selecting a bar applies both its
canonical action and decision to the global filters.

## 9. Project catalog

The complete catalogue is integrated in **Resumen**; there is no duplicated
public Explore page. It keeps one row per project and shows display name, primary
technology, autonomous community, province, municipalities, first/last
observed publication and BOE count by default. A compact selector controls
optional visible columns while **Proyecto** remains mandatory. Multiple
territories are summarized deterministically in the same project row; no join
expands the catalogue grain. The default order is latest observed publication
descending. Internal project identifiers remain navigation keys and are not
prominent display fields.

Native dataframe selection has two distinct meanings: selecting a row or its
**Proyecto** cell opens that project's detail, while selecting a cell in
**Tecnología**, **Comunidad autónoma**, **Provincia** or **Municipio(s)**
applies the corresponding global filter. A filterable cell takes precedence
over a simultaneous row event. Territorial interaction uses the structured
Gold values associated with `project_id`, not the abbreviated display string;
multiple values use OR within the category, and province/municipality choices
synchronize their parents. Every cell filter updates KPIs, both temporal
charts, the map, the administrative chart and the catalogue itself. First/last
publication cells remain display-only because a click would not distinguish
unambiguously between filtering the observed boundary and filtering all BOE
activity in its calendar year.

Project names use a deterministic display-only formatter. It normalizes
whitespace and all-uppercase presentation conservatively while preserving
known acronyms, units, numbers and Roman numerals. Gold names and literal BOE
evidence remain unchanged. The methodology glossary defines **HSF = Huerta
Solar Fotovoltaica.** without expanding HSF inside an official name.

## 10. Project detail

Each detail view uses the complete Gold dataset, independently of the filters
used to find the project. It starts with a deterministic Gold-only description
and bordered summary metrics ordered as BOE publications, published actions,
first observed publication and last observed publication. It then shows a map restricted to the project's
most precise resolved territories, a compact distinct-publication summary and
the full chronology. A project without resolved territory receives an explicit
message instead of an empty map. The previous top-level latest-situations block
is no longer shown ahead of the chronology.

## 11. Evidence and BOE links

Chronology rows are deterministically ordered from oldest to newest by
publication date and Gold indices. Display groups them as one block per
publication date and BOE, followed by all actions in that publication. The BOE
header is not repeated for each action. Every action retains its decision,
modification flag and literal evidence in an expander. Raw extraction JSON is
not exposed.

The shared action in `BOE-B-2023-27607` has three project-centric Gold rows,
one for each linked project, but one `administrative_action_id`. Each affected
project detail therefore displays it once; no join multiplies it within a
project.

## 12. Reporting

The sole **Reportar posible error** control appears immediately below
**Metodología** in the left navigation on every public view; it is neither in
the Methodology body nor in project detail. A valid
`RENEWABLES_REPORT_EMAIL` takes precedence over the Streamlit secret
`report_email`. The control opens a preformatted local `mailto:` with bounded
view and active-filter context. Project detail additionally includes the
display name, stable administrative `project_id`, observed date range, latest
BOE and its canonical public URL. It includes no local paths, hashes, secrets
or raw JSON. Without a valid destination, the UI renders a discrete
configuration fallback instead of a broken link.

The template asks the user to classify the possible problem and explains that
the application does not send, persist, approve or apply the report. Human
triage can route an extraction/content defect to a versioned `manual_review`,
or the one currently supported historical-action exclusion to the narrow
`administrative_action_corrections_v1` registry. A downstream
location-resolution or grouping defect without an existing correction
contract requires a tested deterministic rule and regeneration. Every accepted
path continues through recanonicalization/materialization, Silver, downstream
and a new validated Gold publication. Streamlit never mutates Gold; a
persistent administrative backend remains POST-TFM.

## 13. Geometry provenance

The local administrative reference asset is:

```text
app_assets/geometry/ign_bdlje_2026-07-28/
├── autonomous_communities.geojson
├── provinces.geojson
├── project_municipalities.geojson
└── manifest.json
```

Its source is IGN/CNIG, product **Límites y Unidades Administrativas Actuales**
from the series **Límites municipales, provinciales y autonómicos (LILIM)**,
file `LINEAS_LIMITE.ZIP`, updated 2026-07-28. The source SHA-256 is:

```text
d752b1b943e6c60f46a23119d6c3d4ad0b198461c502f0a5433197d7a5e34c83
```

The deterministic standard-library build script combines the official ETRS89
peninsula/Balearic/Ceuta/Melilla layers with the WGS84 Canary layers. It keeps
the complete valid CCAA/city and province references, excludes only the
official pseudo-territories not associated with an autonomy/province, and
retains the 95 municipality codes represented by final Gold for the analytical
municipality level and project detail.
It rounds to six decimals and applies conservative RDP tolerances of
0.005°/0.0025°/0.001°. The manifest SHA-256 configured by the application is:

```text
0b93ffb56c9553d7532c891094f4b77e06d6f70423eaf8c85df677ef231f722e
```

Artifact hashes are
`54fd723d1d687c11b7ed17b256ffc53fed88cee787674f129880733f3b66ba0f`
for 19 communities/autonomous cities,
`8861b8ed21e4d46210f59ca02e759d24832280e2a693ee40c285f558b6f781ee`
for 52 provinces and
`0ef0f331c2be0641a80e65416cfcfe60f57abc4b9af2657f74adb6941187100b`
for 95 project municipalities.
All Gold codes match; unmatched counts are zero at every level. Ceuta and
Melilla remain at their official North-African coordinates, and Canarias is not
translated into an inset. Source and processing identities, tolerances, code
fields and counts are recorded in the manifest. Visible IGN attribution is:
**Obra derivada de BDLJE CC-BY 4.0 ign.es**.

The separate geographic context asset is:

```text
app_assets/geometry/natural_earth/
├── countries_context.geojson
└── manifest.json
```

It was derived without a download from the locally available GeoPandas
`naturalearth_lowres` dataset copied by Pyogrio. It is Natural Earth admin-0
country context at 1:110m in EPSG:4326, public domain. The local fixture does
not declare a more specific dataset version or publication date, and the
manifest records that limitation rather than inventing one. All 177 source
countries are retained, Polygon records are promoted to MultiPolygon, and
coordinates are neither clipped nor moved. Source-bundle SHA-256 is
`ddfa7af6ff87ac6bfe7b216913462069244aa140fe2a30de61576cfde58a8c53`;
artifact SHA-256 is
`8d22eb9c64c8136d4b3d30b3cf75cb5cf6196e567529e7fbd9041b5b7d1323f0`;
manifest SHA-256 is
`59b20957215f0ced4971f101b628f5dc5f6f6ce8a3211c9c5ba2290947e279d5`.
It includes Spain, Portugal, France, Morocco and Algeria. The 1:110m source
generalises very small states and does not contain Andorra. Visible attribution
is **Contexto geográfico: Natural Earth**.

Runtime separates map data from frontend resources: both GeoJSON sources are
local versioned assets, while Folium and `streamlit-folium` are reproducibly
locked Python packages. The component still loads Leaflet plus supporting
JavaScript/CSS from the upstream CDN URLs declared by Folium. This frontend
dependency must be allowed or vendorized for a fully offline deployment, but
no country, administrative geometry or basemap tile is fetched at runtime.

## 14. Methodology language

The UI defines the corpus as:

> Proyectos de generación con actividad publicada en el BOE durante la ventana
> ancla del 7 al 20 de agosto de 2026, con reconstrucción retrospectiva
> conservadora de publicaciones relacionadas observadas desde 2022.

It states that this is not an exhaustive national census, historical retrieval
uses Tier 1 plus Tier 2 strict while Tier 3 is excluded, project grouping is a
deterministic reconstruction because BOE supplies no stable project ID, dates
are observations within the analyzed corpus, territories are administrative
associations rather than exact locations, and latest publications are not a
legal guarantee of current status.

## 15. Tests

The automated coverage includes Gold fail-closed loading, query purity,
distinct project/BOE grains, both annual series, chart-year parsing and filter
composition, administrative latest/historical semantics, territorial columns
without row expansion, display-name and acronym rules, grouped chronology, the
shared 27607 action, both manifest identities and artifact hashes, complete
19/52 references, the 95-municipality corpus universe, Ceuta/Melilla bounds,
zero-count retention, absence of remote tiles, the exact three Summary levels,
Natural Earth country coverage, feature identities, tooltips and bounds,
temporal, administrative, map and structured table cross-filters, equal 50/50
KPI and temporal-chart columns, clear-all behavior, project-only municipality
subsets and no-territory states, safe contextual sidebar mailto construction
and navigation placement, detail, evidence, BOE links and the opt-in audit
explorer.

Validation commands and final results are recorded in the task handoff rather
than copied here as mutable status.

## 16. Final product questions

| Question | Status | UI section | Query |
| --- | --- | --- | --- |
| How many projects are observed? | PASS | Summary KPI | `build_dashboard_selection` + `summarize_dashboard_selection` |
| How many relevant BOE publications are represented? | PASS | Summary KPI | distinct `boe_id` in supporting events |
| Where are projects associated administratively? | PASS | Administrative map | `build_territory_project_counts` |
| How many projects had an observed publication each year? | PASS | Project temporal chart | `build_yearly_project_counts` |
| How did observed BOE activity evolve? | PASS | BOE temporal chart | `build_publication_counts` |
| What is the latest published situation per action type? | PASS | Administrative chart | `build_latest_project_actions` + distinct-project aggregation |
| What is a project's chronology? | PASS | Project detail | `get_project_timeline` |
| What evidence supports an action? | PASS | Chronology expander | Gold `evidence` |
| What are first/last observed publication dates? | PASS | Catalogue/detail | Gold `projects` dates |

## 17. Residual gaps

- Three projects lack a resolvable published territory and cannot be mapped.
- The map shows administrative associations, not coordinates or physical
  footprints.
- Published situations are observations, not a consolidated legal status.
- Reporting depends on the user's email client and has no persistent backend.
- Local map data and background require no tile server or API key. Folium's
  Leaflet JavaScript/CSS still use declared external frontend resources.
- Public deployment, final holdout/evaluation, screenshots and written TFM
  completion remain separate closeout gates.

## 18. Latest approved map iteration

The final interaction pass consolidates the full catalogue into Summary, uses
equal 50/50 KPI and temporal-chart columns, makes every applicable summary
visual a global filter, generalizes native cell filtering to structured
technology and territorial values, moves glossary and legal interpretation to
Methodology and places reporting directly below that navigation control. After
the third human browser
failure, an approved follow-up retired only the Vega renderer. This later
approved iteration initially added a remote tile basemap and accidentally
removed the general municipality level. The corrective iteration replaces it with versioned
local Natural Earth country context, restores municipalities using the
95-code final-corpus universe, preserves complete IGN CCAA/province references
and keeps every other chart and interaction. It changes
presentation assets, geometry/query presentation code, tests and documentation;
extraction, Silver, downstream, Gold, corpus configuration and the sealed
holdout remain untouched.

Technical validation and reproducible visual-equivalent runtime checks are
recorded in the task handoff. Final subjective review remains explicitly
**HUMAN VISUAL REVIEW REQUIRED** until the human reviewer reopens the resulting
version; screenshots and automated checks do not approve that gate.

## 19. Final human polish pass

The final human-directed polish keeps the approved product and data semantics
unchanged. It orders the administrative sidebar as **Interpretación temporal →
Año de publicación → Fecha publicación → Trámite → Situación publicada**, with
an executable render-order regression. The report link keeps its fixed sidebar
position but uses secondary emphasis so it does not compete with the primary
clear-filter action. No Gold, extraction, map, reporting or cross-filter
contract changes are introduced. The product remains
**TECHNICALLY CLOSED — HUMAN VISUAL REVIEW REQUIRED**.

## 20. Administrative chart and reporting follow-up

The final human follow-up keeps the two approved temporal interpretations and
their query semantics. One native segmented control switches the single
administrative chart area between latest-per-project/action and deduplicated
historical project/action/decision counts; it mirrors the canonical sidebar
state in both directions. Every administrative mark transports canonical
`action_type` plus `decision`, visibly highlights the selection and applies
both predicates to the shared filters.

**Reportar posible error** remains immediately below **Metodología** in every
view. A configured recipient produces the bounded mailto; an installation
without one displays a disabled control and a short configuration caption in
the same position. Methodology contains no reporting workflow and its compact
alphabetical glossary now defines BOE, CNIG, FV, HSF, IGN and INE without
rewriting official project names. The product remains **TECHNICALLY CLOSED —
HUMAN VISUAL REVIEW REQUIRED**.

## 21. Administrative temporal-attribution gate

The final interaction refinement keeps one Streamlit/Vega administrative chart
and adds two explicit selection grains inside it. A small **Todo** marker per
row applies the canonical action type with no decision predicate; each existing
bar segment applies the action type and published decision together. Both
latest and historical modes write to the same sidebar filters and clear/switch
through the existing selection epoch.

Every project chronology now renders newest publication first, with stable
ascending event/action identifiers inside a date. The real W14 Don Rodrigo II
case is covered by presentation regressions.

The accompanying read-only audit found proposed historical-antecedent
exclusions in the current W14 data. No correction registry or generated Gold
was changed. Data correction remains behind an explicit human approval gate,
and the product remains **TECHNICALLY CLOSED — HUMAN VISUAL REVIEW REQUIRED**.
