-- English common names looked up by ingestion/gbif_names.py, loaded as-is (all columns as strings).
select *
from read_files(
    '{{ var("landing_path") }}/gbif_names/',
    format => 'csv',
    header => true,
    inferColumnTypes => false
)
