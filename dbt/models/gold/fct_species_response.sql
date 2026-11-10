-- How each species' share of observations changed after the fire, burned vs control.
--
-- We compare relative frequencies (share of all observations of the zone & period), not raw
-- counts, because observers are not spread evenly in time. log2 changes use +0.5 smoothing so a
-- species absent in one box does not produce an infinite value.
--     baci_log2 = log2 change in burned - log2 change in control
-- +1 => the species became twice as frequent in the burned area relative to the control.
with obs as (
    select * from {{ ref('int_occurrences_labeled') }}
    where period in ('before', 'after')
      and in_comparison
),

box_totals as (
    select
        episode_id,
        count_if(zone = 'burned'  and period = 'before') as tot_burned_before,
        count_if(zone = 'burned'  and period = 'after')  as tot_burned_after,
        count_if(zone = 'control' and period = 'before') as tot_control_before,
        count_if(zone = 'control' and period = 'after')  as tot_control_after
    from obs
    group by episode_id
),

species as (
    select
        episode_id,
        species_key,
        any_value(species_name)                             as species_name,
        any_value(taxon_group)                              as taxon_group,
        count_if(zone = 'burned'  and period = 'before')    as n_burned_before,
        count_if(zone = 'burned'  and period = 'after')     as n_burned_after,
        count_if(zone = 'control' and period = 'before')    as n_control_before,
        count_if(zone = 'control' and period = 'after')     as n_control_after,
        -- whole region, all zones: used to spot species new to the region
        count_if(period = 'before')                         as n_region_before,
        count_if(period = 'after')                          as n_region_after
    from obs
    group by episode_id, species_key
),

scored as (
    select
        s.*,
        log2(try_divide(n_burned_after + 0.5, tot_burned_after)
             / try_divide(n_burned_before + 0.5, tot_burned_before))     as log2_change_burned,
        log2(try_divide(n_control_after + 0.5, tot_control_after)
             / try_divide(n_control_before + 0.5, tot_control_before))   as log2_change_control
    from species as s
    inner join box_totals as t using (episode_id)
)

select
    episode_id,
    species_key,
    species_name,
    taxon_group,
    n_burned_before, n_burned_after, n_control_before, n_control_after,
    n_region_before, n_region_after,
    round(log2_change_burned, 3)                          as log2_change_burned,
    round(log2_change_control, 3)                         as log2_change_control,
    round(log2_change_burned - log2_change_control, 3)    as baci_log2,
    case
        when n_region_before = 0 and n_region_after >= 3 then 'new_in_region'
        when n_region_after = 0 and n_region_before >= 3 then 'not_seen_after'
        when n_burned_before + n_burned_after + n_control_before + n_control_after
             < {{ var('min_species_obs') }} then 'insufficient_data'
        when n_burned_before + n_burned_after < {{ var('min_species_obs_burned') }} then 'insufficient_data'
        when log2_change_burned - log2_change_control >= 1 then 'more_frequent'
        when log2_change_burned - log2_change_control <= -1 then 'less_frequent'
        else 'stable'
    end                                                   as response
from scored
where n_region_before + n_region_after >= 3
