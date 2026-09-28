-- One row per usable GBIF occurrence: typed, filtered, deduplicated, indexed on the H3 grid.
with typed as (
    select
        cast(gbif_id as bigint)                     as gbif_id,
        region_id,
        cast(species_key as bigint)                 as species_key,
        species                                     as species_name,
        kingdom,
        class_name,
        family,
        cast(decimal_latitude as double)            as latitude,
        cast(decimal_longitude as double)           as longitude,
        try_cast(coordinate_uncertainty_m as double) as coordinate_uncertainty_m,
        -- eventDate can be a timestamp or an interval ("2021-05-01/2021-05-03"): keep the start day
        try_cast(left(event_date, 10) as date)      as event_date,
        basis_of_record,
        dataset_key,
        country_code
    from {{ ref('bronze_gbif_occurrences') }}
)

select
    *,
    {{ taxon_group('kingdom', 'class_name') }}                               as taxon_group,
    h3_longlatash3(longitude, latitude, {{ var('h3_resolution') }})       as h3_cell
from typed
where species_key is not null
  and latitude is not null
  and longitude is not null
  and event_date is not null
  and basis_of_record in ('{{ var("kept_basis_of_record") | join("', '") }}')
  and (coordinate_uncertainty_m is null
       or coordinate_uncertainty_m <= {{ var('max_coord_uncertainty_m') }})
qualify row_number() over (partition by gbif_id order by event_date) = 1
