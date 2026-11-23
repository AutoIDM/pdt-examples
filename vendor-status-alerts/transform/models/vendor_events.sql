{#
  One row per item from every source, in one shape. `data` holds the
  item's own fields for the email template. A row with `notify` set goes
  into autoidm_state.send_once_notifications once per hash, so the same
  item is mailed again only when its hash changes (for example an Adobe
  incident that moves from Opened to Closed).
#}
{{ config(
    materialized='table',
    post_hook="insert into autoidm_state.send_once_notifications (hash, source, item_id, status, title, url, updated_at, data)
               select hash, source, item_id, status, title, url, updated_at, data from {{ this }} where notify
               on conflict do nothing"
) }}

{% set lookback_days = env_var('NOTIFY_LOOKBACK_DAYS', '2') | int %}
{% set adobe_products = env_var('ADOBE_PRODUCTS', '') | replace("'", "''") %}
{% set ms_issues = adapter.get_relation(database=target.database, schema='tap_ms365_service_health', identifier='issues') %}
{% set ms_messages = adapter.get_relation(database=target.database, schema='tap_ms365_service_health', identifier='messages') %}

with adobe as (

    select
        'adobe' as source,
        event_id || '/' || product_id as item_id,
        status,
        product_name || ': ' || title as title,
        url,
        updated_at,
        to_json(e) as data,
        '{{ adobe_products }}' = ''
            or list_contains(string_split('{{ adobe_products }}', '|'), product_name)
            or list_has_any(string_split('{{ adobe_products }}', '|'), string_split(cloud_name, ', ')) as wanted
    from {{ source('tap_adobe_status', 'events') }} as e

), cisa_advisories as (

    select
        'cisa_advisories' as source,
        link as item_id,
        null as status,
        title,
        link as url,
        published_at as updated_at,
        to_json(a) as data,
        -- ICS advisories cover industrial control systems. The KEV alerts
        -- repeat what the known_exploited_vulnerabilities rows below say.
        advisory_type <> 'ics-advisories' and title not ilike 'CISA Adds % Known Exploited Vulnerabilit%' as wanted
    from {{ source('tap_cisa', 'advisories') }} as a

), cisa_kev as (

    select
        'cisa_kev' as source,
        cve_id as item_id,
        null as status,
        cve_id || ': ' || vulnerability_name as title,
        url,
        date_added::timestamp as updated_at,
        to_json(k) as data,
        true as wanted
    from {{ source('tap_cisa', 'known_exploited_vulnerabilities') }} as k

{% if ms_issues is not none %}
), ms365_issues as (

    select
        'ms365_issues' as source,
        id as item_id,
        status,
        service || ': ' || title as title,
        url,
        updated_at,
        to_json(i) as data,
        true as wanted
    from {{ ms_issues }} as i
{% endif %}

{% if ms_messages is not none %}
), ms365_messages as (

    select
        'ms365_messages' as source,
        id as item_id,
        null as status,
        title,
        url,
        updated_at,
        to_json(m) as data,
        true as wanted
    from {{ ms_messages }} as m
{% endif %}

), unioned as (

    select * from adobe
    union all select * from cisa_advisories
    union all select * from cisa_kev
    {% if ms_issues is not none %}union all select * from ms365_issues{% endif %}
    {% if ms_messages is not none %}union all select * from ms365_messages{% endif %}

)

select
    *,
    sha256(concat_ws('|', source, item_id, coalesce(status, ''))) as hash,
    wanted and updated_at >= now()::timestamp - interval {{ lookback_days }} day as notify
from unioned
