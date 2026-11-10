-- One row per satellite fire detection, with a confidence level comparable across instruments.
with typed as (
    select
        region_id,
        source,
        cast(latitude as double)             as latitude,
        cast(longitude as double)            as longitude,
        cast(acq_date as date)               as acq_date,
        lpad(acq_time, 4, '0')               as acq_time,
        satellite,
        instrument,
        confidence                           as confidence_raw,
        try_cast(frp as double)              as frp_mw,
        daynight
    from {{ ref('bronze_firms_detections') }}
)

select
    *,
    case
        -- MODIS reports 0-100, VIIRS reports l / n / h
        when instrument = 'MODIS' then
            case
                when try_cast(confidence_raw as int) >= 80 then 'high'
                when try_cast(confidence_raw as int) >= 30 then 'nominal'
                else 'low'
            end
        when lower(confidence_raw) in ('h', 'high') then 'high'
        when lower(confidence_raw) in ('n', 'nominal') then 'nominal'
        else 'low'
    end                                                               as confidence_level,
    h3_longlatash3(longitude, latitude, {{ var('h3_resolution') }}) as h3_cell
from typed
where latitude is not null and acq_date is not null
qualify row_number() over (
    partition by region_id, latitude, longitude, acq_date, acq_time, satellite
    order by source
) = 1
