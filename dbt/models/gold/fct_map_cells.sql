-- One row per (episode, H3 cell with data), for the map. h3_index is the hex string used by h3-js.
-- The map shows every fire of the region at once: `last_burned_episode_id` is the most recent
-- episode that burned the cell (red ramp), `burned_episodes` lists them all.
with cells as (
    select episode_id, region_id, h3_cell from {{ ref('int_occurrences_labeled') }}
    union
    select episode_id, region_id, h3_cell from {{ ref('int_cell_fire_history') }}
),

burn_history as (
    select
        z.region_id,
        z.h3_cell,
        max_by(z.episode_id, e.fire_start)                          as last_burned_episode_id,
        array_join(array_sort(collect_set(year(e.fire_start))), ', ') as burned_episodes
    from {{ ref('int_cell_zones') }} as z
    inner join {{ ref('stg_episodes') }} as e
        on z.episode_id = e.episode_id
    where z.zone = 'burned'
    group by z.region_id, z.h3_cell
),

obs as (
    select
        episode_id,
        h3_cell,
        count_if(period = 'before')                                      as n_obs_before,
        count_if(period = 'after')                                       as n_obs_after,
        count(distinct case when period = 'before' then species_key end) as n_species_before,
        count(distinct case when period = 'after'  then species_key end) as n_species_after
    from {{ ref('int_occurrences_labeled') }}
    where in_comparison
    group by episode_id, h3_cell
)

select
    c.episode_id,
    c.region_id,
    h3_h3tostring(c.h3_cell)                        as h3_index,
    coalesce(z.zone, 'control')                     as zone,
    b.last_burned_episode_id,
    b.burned_episodes,
    coalesce(f.n_detections_studied_fire, 0)        as n_fire_detections,
    coalesce(o.n_obs_before, 0)                     as n_obs_before,
    coalesce(o.n_obs_after, 0)                      as n_obs_after,
    coalesce(o.n_species_before, 0)                 as n_species_before,
    coalesce(o.n_species_after, 0)                  as n_species_after
from cells as c
left join {{ ref('int_cell_zones') }} as z
    on c.episode_id = z.episode_id and c.h3_cell = z.h3_cell
left join burn_history as b
    on c.region_id = b.region_id and c.h3_cell = b.h3_cell
left join {{ ref('int_cell_fire_history') }} as f
    on c.episode_id = f.episode_id and c.h3_cell = f.h3_cell
left join obs as o
    on c.episode_id = o.episode_id and c.h3_cell = o.h3_cell
