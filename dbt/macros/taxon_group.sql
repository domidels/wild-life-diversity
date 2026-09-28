{#- Coarse, reader-friendly taxonomic groups for charts (max 8 categories). -#}
{% macro taxon_group(kingdom, class_name) -%}
    case
        when {{ class_name }} = 'Aves' then 'Birds'
        when {{ class_name }} = 'Mammalia' then 'Mammals'
        when {{ class_name }} in ('Reptilia', 'Squamata', 'Testudines', 'Crocodylia') then 'Reptiles'
        when {{ class_name }} = 'Amphibia' then 'Amphibians'
        when {{ class_name }} = 'Insecta' then 'Insects'
        when {{ kingdom }} = 'Plantae' then 'Plants'
        when {{ kingdom }} = 'Fungi' then 'Fungi'
        else 'Other'
    end
{%- endmacro %}
