-- Rarefying can only lower the species count: a row returned here is a bug.
select *
from {{ ref('fct_baci_summary') }}
where rarefied_richness > n_species + 0.01
