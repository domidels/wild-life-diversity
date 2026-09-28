-- Per episode, the cells that are NOT plain controls. Every other cell of the region is a control.
--   burned    : the studied fire went through it
--   buffer    : within `buffer_rings` of a burned cell (edge effects, fleeing fauna) — excluded
--   disturbed : burned by another fire during the study window — excluded, it would pollute the control
with history as (
    select * from {{ ref('int_cell_fire_history') }}
),

burned as (
    select episode_id, region_id, h3_cell
    from history
    where n_detections_studied_fire >= {{ var('min_detections_burned') }}
),

buffer as (
    select distinct
        episode_id,
        region_id,
        explode(h3_kring(h3_cell, {{ var('buffer_rings') }})) as h3_cell
    from burned
),

candidates as (
    select episode_id, region_id, h3_cell, 'burned' as zone, 1 as priority from burned
    union all
    select episode_id, region_id, h3_cell, 'buffer' as zone, 2 as priority from buffer
    union all
    select episode_id, region_id, h3_cell, 'disturbed' as zone, 3 as priority
    from history
    where n_detections_other >= {{ var('min_detections_burned') }}
)

select episode_id, region_id, h3_cell, zone
from candidates
qualify row_number() over (partition by episode_id, h3_cell order by priority) = 1
