-- Did the observed range of a species move? Mean latitude of its observations, before vs after.
-- 1 degree of latitude ~ 111.2 km. `is_notable` when the shift exceeds ~2 standard errors.
-- Inside a small region this mostly reveals where people looked — read with care.
with obs as (
    select * from {{ ref('int_occurrences_labeled') }}
    where period in ('before', 'after')
      and in_comparison
),

by_period as (
    select
        episode_id,
        species_key,
        any_value(species_name)                         as species_name,
        any_value(taxon_group)                          as taxon_group,
        count_if(period = 'before')                     as n_before,
        count_if(period = 'after')                      as n_after,
        avg(case when period = 'before' then latitude end)     as mean_lat_before,
        avg(case when period = 'after'  then latitude end)     as mean_lat_after,
        stddev(case when period = 'before' then latitude end)  as sd_lat_before,
        stddev(case when period = 'after'  then latitude end)  as sd_lat_after
    from obs
    group by episode_id, species_key
)

select
    episode_id,
    species_key,
    species_name,
    taxon_group,
    n_before,
    n_after,
    round(mean_lat_before, 4)                                          as mean_lat_before,
    round(mean_lat_after, 4)                                           as mean_lat_after,
    round((mean_lat_after - mean_lat_before) * 111.2, 1)               as shift_km,
    round(sqrt(power(sd_lat_before, 2) / n_before
               + power(sd_lat_after, 2) / n_after) * 111.2, 1)         as shift_se_km,
    abs(mean_lat_after - mean_lat_before)
        > 2 * sqrt(power(sd_lat_before, 2) / n_before + power(sd_lat_after, 2) / n_after)
                                                                       as is_notable
from by_period
where n_before >= {{ var('min_obs_latitude_shift') }}
  and n_after  >= {{ var('min_obs_latitude_shift') }}
