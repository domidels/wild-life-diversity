-- Composition of observations by taxonomic group, per zone and period.
with counts as (
    select episode_id, zone, period, taxon_group, count(*) as n_observations
    from {{ ref('int_occurrences_labeled') }}
    where zone in ('burned', 'control')
      and period in ('before', 'after')
      and in_comparison
    group by episode_id, zone, period, taxon_group
)

select
    *,
    round(n_observations / sum(n_observations) over (partition by episode_id, zone, period), 4) as share
from counts
