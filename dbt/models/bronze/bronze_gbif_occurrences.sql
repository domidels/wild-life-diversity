-- Raw GBIF CSVs from the landing volume, loaded as-is (all columns as strings).
select *
from read_files(
    '{{ var("landing_path") }}/gbif/',
    format => 'csv',
    header => true,
    inferColumnTypes => false
)
