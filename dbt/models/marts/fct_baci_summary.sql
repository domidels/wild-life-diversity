-- The four boxes of the BACI design (Before-After x Control-Impact) per episode.
--
-- Raw species counts grow with observation effort, so richness is also rarefied:
-- the expected number of species in a random sample of `n_rarefaction` observations,
-- the same n for the four boxes of an episode (Hurlbert 1971, with-replacement approximation):
--     E[S_n] = sum_i ( 1 - (1 - n_i / N)^n )
with obs as (
    select *
    from {{ ref('int_occurrences_labeled') }}
    where zone in ('burned', 'control')
      and period in ('before', 'after')
      and in_comparison
),

totals as (
    select
        episode_id, zone, period,
        count(*)                    as n_observations,
        count(distinct species_key) as n_species,
        count(distinct dataset_key) as n_datasets,
        count(distinct h3_cell)     as n_cells_observed
    from obs
    group by episode_id, zone, period
),

rarefaction_n as (
    select episode_id, least(min(n_observations), {{ var('rarefaction_cap') }}) as n_rarefaction
    from totals
    group by episode_id
),

species_counts as (
    select episode_id, zone, period, species_key, count(*) as n_i
    from obs
    group by episode_id, zone, period, species_key
),

rarefied as (
    select
        s.episode_id, s.zone, s.period,
        sum(1 - power(1 - s.n_i / t.n_observations, rn.n_rarefaction)) as rarefied_richness
    from species_counts as s
    inner join totals as t using (episode_id, zone, period)
    inner join rarefaction_n as rn using (episode_id)
    group by s.episode_id, s.zone, s.period
)

select
    t.episode_id,
    t.zone,
    t.period,
    t.n_observations,
    t.n_species,
    t.n_datasets,
    t.n_cells_observed,
    rn.n_rarefaction,
    round(r.rarefied_richness, 1) as rarefied_richness
from totals as t
inner join rarefaction_n as rn using (episode_id)
inner join rarefied as r using (episode_id, zone, period)
