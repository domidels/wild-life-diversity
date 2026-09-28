-- Fire history of each H3 cell, per episode, over that episode's study window:
-- detections during the studied fire vs. at any other time (other fires, agricultural burning...).
with detections as (
    select
        e.episode_id,
        e.region_id,
        d.h3_cell,
        d.acq_date,
        d.frp_mw,
        d.acq_date between e.fire_start and e.fire_end as is_studied_fire
    from {{ ref('stg_firms__detections') }} as d
    inner join {{ ref('stg_episodes') }} as e
        on d.region_id = e.region_id
    where d.confidence_level in ('nominal', 'high')
      and d.acq_date between e.before_start and e.after_end
)

select
    episode_id,
    region_id,
    h3_cell,
    count_if(is_studied_fire)                          as n_detections_studied_fire,
    count_if(not is_studied_fire)                      as n_detections_other,
    sum(case when is_studied_fire then frp_mw end)     as total_frp_studied_fire_mw,
    min(case when is_studied_fire then acq_date end)   as first_detection_date
from detections
group by episode_id, region_id, h3_cell
