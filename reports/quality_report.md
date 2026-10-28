# IRIS Task 053 — Data Quality Report

## 1. Scope

This report documents validation of the official Hesse compensation-register ZIP snapshot loaded into the local PostGIS staging table `iris_staging.compensation_sites`.

**Important:** This report describes the tested ZIP workflow, not a successful live WFS harvest.

## 2. Source and coordinate reference system

- Configured WFS endpoint: `https://gds.hessen.de/wfs/hlnug/kompensation`
- Configured WFS feature type: `he_kompensationskataster`
- ZIP fallback: `https://umweltdaten.hessen.de/resources/recherche/Geodaten/Komp_Hessen_utm.zip`
- Shapefile: `Komp_Hessen_UTM.shp`
- Source CRS: EPSG:25832
- Target CRS: EPSG:25832

The WFS GetCapabilities request returned HTTP 404 with a JPEG response during development. Live WFS retrieval and pagination remain unverified.

## 3. Import results

| Check | Observed result |
|---|---:|
| Source features | 44,327 |
| Records upserted | 44,327 |
| Records skipped for missing keys | 0 |
| Invalid geometries before repair | 94 |
| Invalid geometries after repair | 0 |
| Staging records after repeat import | 44,327 |
| Distinct site identifiers after repeat import | 44,327 |
| Missing geometries after import | 0 |
| Geometry SRID | 25832 |

These are results from the tested snapshot and local database. Re-run validation after importing a different snapshot.

## 4. Attribute and identifier handling

The source includes attributes such as `OBJECTID`, `FO_KOMP_ID`, `GEMEINDE`, `MASS_ART`, `DAT_BESCH`, `SACHSTAND`, `MASS_ID`, and `FO_ID`.

- Original source properties are retained in JSONB.
- The ZIP importer constructs `site_id` from `FO_KOMP_ID` and `MASS_ID`.
- These two fields were unique as a combined key in the tested snapshot.
- `FO_ID` is missing in some records and is not used as the sole key.
- `OBJECTID` is unique in the snapshot but is treated as a source attribute, not a guaranteed permanent identifier.

## 5. Geometry quality

The source snapshot contained 94 invalid geometries. Geometry repair was applied, and the importer reported zero invalid geometries after repair. The imported geometries use SRID 25832.

## 6. Idempotency

The import was executed twice. The staging table retained 44,327 records with 44,327 distinct site identifiers after the repeated import. This supports idempotent behavior for the tested snapshot and staging configuration.

## 7. Limitations and follow-up

1. Verify the live WFS endpoint, capabilities, layer schema, and paging behavior before claiming live WFS harvesting.
2. Re-run geometry and uniqueness checks when the source snapshot changes.
3. Review any import errors and data-quality counts after each run.
4. Keep all writes restricted to `iris_staging.compensation_sites`; do not write to `iris_core` or production.

## 8. Reproducibility

Run the import and automated tests using the commands documented in the project README. Preserve the console output from the final import and test run as evidence for the submitted implementation.
