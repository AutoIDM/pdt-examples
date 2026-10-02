{#
  The items for the next email: every unsent notification that changed
  inside the lookback window. render-email turns these into the message.
#}
{{ config(materialized='table') }}

-- vendor_events inserts the rows read here, so it must run first.
-- depends_on: {{ ref('vendor_events') }}

{% set lookback_days = env_var('NOTIFY_LOOKBACK_DAYS', '2') | int %}

select hash, source, item_id, status, title, url, updated_at, data
from {{ source('autoidm_state', 'send_once_notifications') }}
where not sent
  and updated_at >= now()::timestamp - interval {{ lookback_days }} day
