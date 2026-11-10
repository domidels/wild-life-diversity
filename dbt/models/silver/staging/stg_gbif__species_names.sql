-- English common name of each species, null when GBIF has none (the scientific name is shown instead).
select
    cast(species_key as bigint)   as species_key,
    scientific_name,
    nullif(common_name, '')       as common_name
from {{ ref('bronze_gbif_species_names') }}
qualify row_number() over (partition by species_key order by checked_on desc) = 1
