-- Raw GBIF CSVs from the landing volume, loaded as-is (all columns as strings).
select *
from read_files(
    '{{ var("landing_path") }}/gbif/',
    format => 'csv',
    header => true,
    inferColumnTypes => false,
    -- observer_id was added later: the hint keeps the column even if older files lack it
    schemaHints => 'observer_id string'
)
