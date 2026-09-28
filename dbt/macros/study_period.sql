{#- Label a date relative to a region's fire (needs the columns of stg_regions in scope). -#}
{% macro study_period(date_column) -%}
    case
        when {{ date_column }} between before_start and before_end then 'before'
        when {{ date_column }} between fire_start and fire_end then 'during'
        when {{ date_column }} between after_start and after_end then 'after'
    end
{%- endmacro %}
