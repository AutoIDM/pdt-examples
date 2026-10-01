{#
  One row per item from every source, in one shape. A row with `notify`
  set goes into autoidm_state.send_once_notifications once per hash, so
  the same item is mailed again only when its hash changes (for example
  an Adobe incident that moves from Opened to Closed).
#}
{{ config(
    materialized='table',
    post_hook="insert into autoidm_state.send_once_notifications (hash, source, title, body, updated_at)
               select hash, source, title, body, updated_at from {{ this }} where notify
               on conflict do nothing"
) }}

{% set lookback_days = env_var('NOTIFY_LOOKBACK_DAYS', '2') | int %}
{% set adobe_products = env_var('ADOBE_PRODUCTS', '') | replace("'", "''") %}
{% set ms_issues = adapter.get_relation(database=target.database, schema='tap_ms365_service_health', identifier='issues') %}
{% set ms_messages = adapter.get_relation(database=target.database, schema='tap_ms365_service_health', identifier='messages') %}

with adobe as (

    select
        'Adobe' as source,
        event_id || '/' || product_id as item_id,
        status,
        product_name || ': ' || title || ' (' || status || ')' as title,
        concat_ws(chr(10),
            message,
            'Kind: ' || kind || coalesce(', severity: ' || severity, ''),
            'Services: ' || nullif(array_to_string(from_json(services, '["VARCHAR"]'), ', '), ''),
            'Started: ' || strftime(started_at, '%Y-%m-%d %H:%M UTC'),
            'Ended: ' || strftime(ended_at, '%Y-%m-%d %H:%M UTC'),
            url
        ) as body,
        updated_at,
        '{{ adobe_products }}' = ''
            or list_contains(string_split('{{ adobe_products }}', '|'), product_name)
            or list_has_any(string_split('{{ adobe_products }}', '|'), string_split(cloud_name, ', ')) as wanted
    from {{ source('tap_adobe_status', 'events') }}

), cisa_advisories as (

    select
        'CISA advisories' as source,
        link as item_id,
        null as status,
        title,
        concat_ws(chr(10), left(summary, 600), link) as body,
        published_at as updated_at,
        -- ICS advisories cover industrial control systems. The KEV alerts
        -- repeat what the known_exploited_vulnerabilities rows below say.
        advisory_type <> 'ics-advisories' and title not ilike 'CISA Adds % Known Exploited Vulnerabilit%' as wanted
    from {{ source('tap_cisa', 'advisories') }}

), cisa_kev as (

    select
        'CISA known exploited vulnerabilities' as source,
        cve_id as item_id,
        null as status,
        cve_id || ': ' || vulnerability_name as title,
        concat_ws(chr(10),
            short_description,
            'Required action: ' || required_action,
            'Due: ' || due_date,
            'Known ransomware use: ' || known_ransomware_campaign_use,
            url
        ) as body,
        date_added::timestamp as updated_at,
        true as wanted
    from {{ source('tap_cisa', 'known_exploited_vulnerabilities') }}

{% if ms_issues is not none %}
), ms_issues as (

    select
        'Microsoft 365' as source,
        id as item_id,
        status,
        service || ': ' || title || ' (' || id || ', ' || status || ')' as title,
        concat_ws(chr(10),
            impact_description,
            'Latest update: ' || nullif(trim(regexp_replace(latest_post, '<[^>]+>', ' ', 'g')), ''),
            'Classification: ' || classification,
            'Feature: ' || feature,
            'Started: ' || strftime(start_at, '%Y-%m-%d %H:%M UTC'),
            'Ended: ' || strftime(end_at, '%Y-%m-%d %H:%M UTC'),
            url
        ) as body,
        updated_at,
        true as wanted
    from {{ ms_issues }}
{% endif %}

{% if ms_messages is not none %}
), ms_messages as (

    select
        'Microsoft 365 Message center' as source,
        id as item_id,
        null as status,
        title || ' (' || id || ')' as title,
        concat_ws(chr(10),
            'Services: ' || nullif(array_to_string(from_json(services, '["VARCHAR"]'), ', '), ''),
            'Category: ' || category || coalesce(', severity: ' || severity, ''),
            'Act by: ' || strftime(action_required_by, '%Y-%m-%d'),
            url
        ) as body,
        updated_at,
        true as wanted
    from {{ ms_messages }}
{% endif %}

), unioned as (

    select * from adobe
    union all select * from cisa_advisories
    union all select * from cisa_kev
    {% if ms_issues is not none %}union all select * from ms_issues{% endif %}
    {% if ms_messages is not none %}union all select * from ms_messages{% endif %}

)

select
    *,
    sha256(concat_ws('|', source, item_id, coalesce(status, ''))) as hash,
    wanted and updated_at >= now()::timestamp - interval {{ lookback_days }} day as notify
from unioned
