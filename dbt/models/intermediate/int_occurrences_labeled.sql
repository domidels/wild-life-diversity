-- Each occurrence tagged, for every fire episode of its region, with its period
-- (before / during / after the fire) and its zone (burned / buffer / disturbed / control).
-- One row per (episode, occurrence).
--
-- Season matching: when the after window is shorter than a year (a recent fire),
-- comparisons (in_comparison = true) only keep "before" observations whose calendar day
-- falls inside the after window's span of the year — e.g. August-September 2024 and 2025
-- against August-September 2026. Otherwise a summer "after" would be compared with a
-- whole-year "before" (migrants, flowering...).
--
-- Active datasets: GBIF publishers upload with very different delays (iNaturalist weekly,
-- eBird yearly, some national programmes years later). A dataset with no record in the
-- "after" window of an episode is left out of comparisons, so before and after draw on the
-- same sources (is_active_dataset).
with located as (
    select
        e.episode_id,
        o.*,
        {{ study_period('o.event_date') }} as period,
        e.is_season_matched,
        month(o.event_date) * 100 + day(o.event_date)       as event_md,
        month(e.after_start) * 100 + day(e.after_start)     as after_start_md,
        month(e.after_end) * 100 + day(e.after_end)         as after_end_md
    from {{ ref('stg_gbif__occurrences') }} as o
    inner join {{ ref('stg_episodes') }} as e
        on o.region_id = e.region_id
       and o.latitude between e.min_lat and e.max_lat
       and o.longitude between e.min_lon and e.max_lon
),

active_datasets as (
    select distinct episode_id, dataset_key
    from located
    where period = 'after'
)

select
    located.* except (is_season_matched, event_md, after_start_md, after_end_md),
    coalesce(z.zone, 'control') as zone,
    a.dataset_key is not null   as is_active_dataset,
    -- false for inactive datasets and for "before" observations outside the matched season:
    -- kept for the effort timeline, left out of every before/after comparison
    a.dataset_key is not null
    and (
        not located.is_season_matched
        or located.period <> 'before'
        or case
               when after_start_md <= after_end_md then event_md between after_start_md and after_end_md
               else event_md >= after_start_md or event_md <= after_end_md  -- span crosses 1 January
           end
    ) as in_comparison
from located
left join {{ ref('int_cell_zones') }} as z
    on located.episode_id = z.episode_id
   and located.h3_cell = z.h3_cell
left join active_datasets as a
    on located.episode_id = a.episode_id
   and located.dataset_key = a.dataset_key
where located.period is not null
