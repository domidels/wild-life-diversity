-- One row per fire episode, with its region and the headline numbers of the dashboard.
with cells as (
    select episode_id, count_if(zone = 'burned') as n_burned_cells
    from {{ ref('int_cell_zones') }}
    group by episode_id
),

fire as (
    select episode_id, sum(n_detections_studied_fire) as n_fire_detections
    from {{ ref('int_cell_fire_history') }}
    group by episode_id
),

obs as (
    select
        episode_id,
        count(*)                    as n_observations,
        count(distinct species_key) as n_species,
        count(distinct dataset_key) as n_datasets
    from {{ ref('int_occurrences_labeled') }}
    group by episode_id
)

select
    e.*,
    coalesce(cells.n_burned_cells, 0)                                        as n_burned_cells,
    round(coalesce(cells.n_burned_cells, 0) * {{ var('h3_cell_area_km2') }}) as burned_area_km2,
    coalesce(fire.n_fire_detections, 0)                                      as n_fire_detections,
    coalesce(obs.n_observations, 0)                                          as n_observations,
    coalesce(obs.n_species, 0)                                               as n_species,
    coalesce(obs.n_datasets, 0)                                              as n_datasets
from {{ ref('stg_episodes') }} as e
left join cells using (episode_id)
left join fire using (episode_id)
left join obs using (episode_id)
