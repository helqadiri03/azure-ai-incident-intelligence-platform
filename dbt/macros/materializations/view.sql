{% materialization view, adapter='synapse' %}
    {%- set identifier = model['alias'] -%}
    {%- set target_relation = api.Relation.create(identifier=identifier, schema=schema, database=database, type='view') -%}

    {{ run_hooks(pre_hooks) }}

    -- Drop the existing relation if it exists, since Synapse Serverless does not support RENAME OBJECT
    {{ adapter.drop_relation(target_relation) }}

    -- Build the model directly to the target relation (no __dbt_tmp)
    {% call statement('main') -%}
        {{ get_create_view_as_sql(target_relation, sql) }}
    {%- endcall %}

    {{ run_hooks(post_hooks) }}

    {{ return({'relations': [target_relation]}) }}
{% endmaterialization %}
