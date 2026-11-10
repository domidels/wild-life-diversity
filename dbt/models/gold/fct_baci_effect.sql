-- The BACI effect per episode and metric:
--     effect = (burned_after / burned_before) / (control_after / control_before)
-- 1.0 means the burned area changed exactly like the control; 0.7 means it did 30% worse.
-- Dividing by the control cancels what changed everywhere (e.g. the growth of iNaturalist).
-- is_reliable is false when one of the four boxes has fewer than `min_box_observations`
-- observations: the dashboard then says "not enough data" instead of showing a number.
{% set metrics = ['n_observations', 'n_species', 'rarefied_richness'] %}

with boxes as (
    select * from {{ ref('fct_baci_summary') }}
),

box_sizes as (
    -- a missing box counts as 0 observations
    select episode_id, if(count(*) < 4, 0, min(n_observations)) as smallest_box_observations
    from boxes
    group by episode_id
),

{% for metric in metrics %}
{{ metric }}_pivot as (
    select
        episode_id,
        '{{ metric }}' as metric,
        max(case when zone = 'burned'  and period = 'before' then {{ metric }} end) as burned_before,
        max(case when zone = 'burned'  and period = 'after'  then {{ metric }} end) as burned_after,
        max(case when zone = 'control' and period = 'before' then {{ metric }} end) as control_before,
        max(case when zone = 'control' and period = 'after'  then {{ metric }} end) as control_after
    from boxes
    group by episode_id
){{ "," if not loop.last }}
{% endfor %}

, pivoted as (
    {% for metric in metrics %}
    select * from {{ metric }}_pivot
    {{ "union all" if not loop.last }}
    {% endfor %}
)

select
    p.*,
    b.smallest_box_observations,
    b.smallest_box_observations >= {{ var('min_box_observations') }}          as is_reliable,
    -- try_divide returns null instead of failing when a box is empty (ANSI mode)
    round(try_divide(burned_after, burned_before), 3)                       as burned_ratio,
    round(try_divide(control_after, control_before), 3)                     as control_ratio,
    round(try_divide(try_divide(burned_after, burned_before),
                     try_divide(control_after, control_before)), 3)         as baci_ratio,
    round((try_divide(try_divide(burned_after, burned_before),
                      try_divide(control_after, control_before)) - 1) * 100, 1) as baci_effect_pct
from pivoted as p
inner join box_sizes as b using (episode_id)
