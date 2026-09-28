-- In every zone x period box, taxon group shares must add up to 100%.
select episode_id, zone, period, sum(share) as total_share
from {{ ref('fct_taxon_group_mix') }}
group by episode_id, zone, period
having abs(sum(share) - 1) > 0.01
