
-- IRIS Task 053: reproducible spatial query
-- Find the 10 nearest compensation sites to Frankfurt city centre.
-- The reference point is transformed from WGS84 to EPSG:25832.
-- Distance is reported in metres.

WITH reference_point AS (
    SELECT ST_Transform(
        ST_SetSRID(
            ST_MakePoint(8.6821, 50.1109),
            4326
        ),
        25832
    ) AS geom
)
SELECT
    sites.site_id,
    sites.state_code,
    sites.source_crs,
    sites.target_crs,
    ROUND(
        ST_Distance(sites.geom, reference_point.geom)::numeric,
        2
    ) AS distance_metres,
    sites.source_properties
FROM iris_staging.compensation_sites AS sites
CROSS JOIN reference_point
WHERE sites.geom IS NOT NULL
  AND ST_IsValid(sites.geom)
  AND sites.state_code = 'HE'
ORDER BY sites.geom <-> reference_point.geom
LIMIT 10;
