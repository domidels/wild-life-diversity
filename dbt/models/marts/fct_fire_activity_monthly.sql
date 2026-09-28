-- Monthly fire detections per region (nominal + high confidence), over the window covering all its episodes.
with region_windows as (
    select region_id, min(before_start) as window_start, max(after_end) as window_end
    from {{ ref('stg_episodes') }}
    group by region_id
)

select
    d.region_id,
    trunc(d.acq_date, 'MM')   as month,
    count(*)                  as n_detections,
    round(sum(d.frp_mw))      as total_frp_mw
from {{ ref('stg_firms__detections') }} as d
inner join region_windows as w
    on d.region_id = w.region_id
where d.confidence_level in ('nominal', 'high')
  and d.acq_date between w.window_start and w.window_end
group by d.region_id, trunc(d.acq_date, 'MM')
