{#
  One digest of every unsent notification, as the title and body that
  target-apprise sends. No row when nothing is unsent.
#}
{{ config(materialized='table') }}

-- vendor_events inserts the rows read here, so it must run first.
-- depends_on: {{ ref('vendor_events') }}

{% set lookback_days = env_var('NOTIFY_LOOKBACK_DAYS', '2') | int %}

with unsent as (

    select * from {{ source('autoidm_state', 'send_once_notifications') }}
    where not sent
      and updated_at >= now()::timestamp - interval {{ lookback_days }} day

), per_source as (

    select
        source,
        count(*) as updates,
        string_agg(title || chr(10) || body, chr(10) || chr(10) order by updated_at desc) as items
    from unsent
    group by source

)

select
    'Vendor status: ' || sum(updates) || ' new update' || case when sum(updates) = 1 then '' else 's' end as title,
    string_agg(
        '=== ' || source || ' (' || updates || ') ===' || chr(10) || chr(10) || items,
        chr(10) || chr(10) || chr(10) order by source
    ) as body
from per_source
having count(*) > 0
