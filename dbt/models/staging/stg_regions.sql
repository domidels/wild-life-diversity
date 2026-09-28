-- Study regions: the bounding box inside which everything is downloaded.
select
    region_id,
    region_name,
    country_code,
    min_lon, min_lat, max_lon, max_lat
from {{ ref('regions') }}
