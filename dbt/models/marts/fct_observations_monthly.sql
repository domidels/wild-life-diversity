-- Monthly observation effort and species count, burned vs control, per episode.
-- Active datasets only (see int_occurrences_labeled): otherwise late publishers make recent
-- months look empty. All seasons are kept: this is the effort timeline.
select
    episode_id,
    trunc(event_date, 'MM')      as month,
    zone,
    count(*)                     as n_observations,
    count(distinct species_key)  as n_species
from {{ ref('int_occurrences_labeled') }}
where zone in ('burned', 'control')
  and is_active_dataset
group by episode_id, trunc(event_date, 'MM'), zone
