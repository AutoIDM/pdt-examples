{#
  Runs after target-apprise sent the digest. A failed send stops the job
  before this, so the same rows go out in the next run.
#}
{% macro mark_sent() %}
    {% do run_query("update autoidm_state.send_once_notifications set sent = true where not sent") %}
{% endmacro %}
