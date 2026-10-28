# IRIS Task 053 — Hesse Compensation Register (HLNUG)

A reproducible Python and PostGIS ingestion pipeline for the Hesse compensation register. The pipeline processes geospatial source data, validates and repairs geometries, and loads records exclusively into the isolated `iris_staging.compensation_sites` table.

## 1. Project Scope

The project aims to:

- Retrieve and process compensation-site data from the Hesse environmental data source.
- Preserve original source attributes without fabricating missing values.
- Validate coordinate reference systems, repair invalid geometries, and transform spatial data to `EPSG:25832`.
- Generate stable staging identifiers from available source attributes.
- Load records using repeatable, idempotent staging upserts.
- Report ingestion counts and geometry-quality results.
- Keep all writes isolated from production schemas.

## 2. Data Source and Fallback

### Configured WFS source

- **Endpoint:** https://gds.hessen.de/wfs/hlnug/kompensation
- **Configured feature type:** `he_kompensationskataster`

During development, the WFS GetCapabilities request returned HTTP 404 with a JPEG response. Successful live WFS harvesting and pagination have therefore **not been established**.

### Tested official ZIP source

The tested ingestion workflow uses the official Hesse compensation-data ZIP:

https://umweltdaten.hessen.de/resources/recherche/Geodaten/Komp_Hessen_utm.zip

The archive contains the `Komp_Hessen_UTM.shp` shapefile in `EPSG:25832`.

The ZIP import is a documented fallback, not a successful live WFS harvest. The WFS endpoint remains configured for future verification.

## 3. Technology Stack

| Component | Technology |
|---|---|
| Language | Python |
| Geospatial processing | GeoPandas, Shapely |
| Database access | SQLAlchemy, psycopg |
| Spatial database | PostgreSQL with PostGIS |
| Containerization | Docker, Docker Compose |
| Automated testing | pytest |

## 4. Architecture and Processing Pipeline

The ingestion workflow follows these stages:

1. **Read source data:** Load the source dataset while retaining its original attributes.
2. **Validate and normalize:** Check the source CRS and normalize available fields without inventing unavailable attributes.
3. **Repair geometries:** Repair invalid geometries and handle missing or unusable geometries according to the pipeline's validation rules.
4. **Transform CRS:** Convert geometries to the target CRS, `EPSG:25832`.
5. **Generate staging identifiers:** Build a staging key from available source identifiers.
6. **Upsert records:** Insert or update records in `iris_staging.compensation_sites`.
7. **Validate results:** Check record counts, key uniqueness, geometry validity, and SRID.

### Staging key

For the tested official ZIP snapshot, the staging identifier is formed from `FO_KOMP_ID` and `MASS_ID`.

These identifiers were observed to form a unique composite key in the tested snapshot. They are not assumed to be globally permanent identifiers across all possible source versions.

The staging table uses a unique `(site_id, state_code)` constraint to support repeatable imports. Original source attributes are retained in a JSONB column for traceability.

## 5. Configuration

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Review the database connection settings before running any ingestion command. Keep `.env` and real credentials out of version control.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection URL |
| `WFS_BASE_URL` | Configured WFS endpoint |
| `WFS_LAYER` | Configured WFS feature type |
| `WFS_TIMEOUT_SECONDS` | HTTP request timeout |
| `WFS_PAGE_SIZE` | Requested WFS page size |
| `TARGET_CRS` | Target coordinate reference system; `EPSG:25832` |

The actual ingestion path verified in this assessment is the official ZIP workflow. Configuring a WFS endpoint does not establish that live WFS access is working.

## 6. Run with Docker

Run these commands from the project root.

### Start the database

```powershell
docker compose up -d db
```

### Check service status

```powershell
docker compose ps
```

Confirm that the database service is healthy before running database-dependent commands.

### Import the official ZIP dataset

Place the downloaded archive at `data/Komp_Hessen_utm.zip`, then run:

```powershell
docker compose run --rm harvester python scripts/load_official_zip.py
```

The downloaded source archive is local input data and is excluded from version control.

### Run automated tests

```powershell
docker compose run --rm --no-deps harvester python -m pytest -q
```

To run the tests using the local Python environment instead:

```powershell
python -m pytest -q
```

## 7. Verified Import Results

The tested official ZIP snapshot contained 44,327 features.

| Metric | Verified result |
|---|---:|
| Source features | 44,327 |
| Records upserted | 44,327 |
| Records skipped for missing keys | 0 |
| Invalid geometries before repair | 94 |
| Invalid geometries after repair | 0 |

A repeated import was also tested. The staging table remained at 44,327 records.

The subsequent database integrity query returned:

| Integrity check | Result |
|---|---:|
| Total rows | 44,327 |
| Distinct site IDs | 44,327 |
| Missing geometries | 0 |
| Invalid geometries | 0 |
| Geometries with an unexpected SRID | 0 |

These results describe the tested ZIP snapshot and local staging database. They do not establish live WFS availability or guarantee that future source snapshots will have identical record counts.

## 8. Reproducible Spatial Query

The project includes `sql/sample_spatial_query.sql`, a read-only PostGIS query that finds the ten nearest valid compensation-site geometries to a reference point in Frankfurt am Main.

The query transforms the reference point from `EPSG:4326` to `EPSG:25832`, filters records to state code `HE`, and reports distances in metres.

Run the saved query from PowerShell:

```powershell
Get-Content .\sql\sample_spatial_query.sql | docker compose exec -T db psql -U iris_app -d iris
```

The query was tested against the staging database and returned ten records. The nearest returned record was approximately 930.24 metres from the reference point, and the farthest of the ten returned records was approximately 3,226.81 metres away.

Results depend on the source data currently loaded into the staging table.

## 9. Data Quality and Provenance

The tested source contains attributes including:

- `OBJECTID`
- `FO_KOMP_ID`
- `GEMEINDE`
- `MASS_ART`
- `B_BEHOERDE`
- `DAT_BESCH`
- `Z_BEHOERDE`
- `AKZ`
- `SACHSTAND`
- `NR`
- `MASS_ID`
- `InfoGrafik`
- `FO_ID`

Data-quality considerations:

- Some source identifiers repeat individually. The combination of `FO_KOMP_ID` and `MASS_ID` was unique in the tested snapshot.
- `FO_ID` is missing in some records and is not used as the sole staging key.
- Original source properties are retained for traceability.
- Geometry repair is applied before loading.
- The tested dataset does not establish the availability of every possible area or ecological-credit attribute.
- Unavailable source values must not be fabricated.
- Source-service failures and ingestion limitations should be recorded in the quality report.

## 10. Safety and Operational Constraints

- Write only to `iris_staging.compensation_sites`.
- Never write to `iris_core` or production resources.
- Never commit `.env`, passwords, or other secrets.
- Do not fabricate missing source values or attributes.
- Do not represent ZIP ingestion as a successful live WFS harvest.
- Review database connection settings before running ingestion commands.
- Use the isolated local database for assessment testing.

## 11. Repository Structure

```text
.
├── data/
│   └── .gitkeep
├── reports/
│   ├── .gitkeep
│   └── quality_report.md
├── scripts/
│   └── load_official_zip.py
├── sql/
│   └── sample_spatial_query.sql
├── src/
│   └── compensation_harvester/
├── tests/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

The source archive is supplied locally and is excluded from Git. The `src/` directory contains the processing and database logic; `tests/` contains automated checks; and `reports/` contains the data-quality report.

## 12. Known Limitations and Next Steps

The live WFS endpoint returned an unexpected HTTP 404/JPEG response during the initial investigation. Successful capability discovery, feature-type verification, and live WFS pagination have not been established.

Before claiming full live WFS harvesting support, verify the endpoint, service capabilities, feature-type schema, and paging behavior.

The official ZIP workflow is the tested ingestion path. Any unavailable source attributes must remain explicitly unavailable, and all limitations must be documented rather than inferred away.
