-- Fire episodes with their before / during / after windows.
-- A recent fire has not had `window_months` of "after" yet: the after window stops yesterday.
with windows as (
    select
        e.episode_id,
        e.region_id,
        r.region_name,
        r.country_code,
        e.fire_name,
        r.min_lon, r.min_lat, r.max_lon, r.max_lat,
        e.before_months,
        add_months(e.fire_start, -e.before_months)                   as before_start,
        date_sub(e.fire_start, 1)                                    as before_end,
        e.fire_start,
        e.fire_end,
        date_add(e.fire_end, 1)                                      as after_start,
        least(add_months(e.fire_end, {{ var('window_months') }}),
              date_sub(current_date(), 1))                         as after_end
    from {{ ref('fire_episodes') }} as e
    inner join {{ ref('stg_regions') }} as r
        on e.region_id = r.region_id
)

select
    *,
    -- when "after" is shorter than a year, compare it with the same season in the "before" years
    months_between(after_end, fire_end) < 12                                        as is_season_matched,
    -- 1 = most recent fire of the region: drives the red ramp of the map
    row_number() over (partition by region_id order by fire_start desc)            as recency_rank
from windows
