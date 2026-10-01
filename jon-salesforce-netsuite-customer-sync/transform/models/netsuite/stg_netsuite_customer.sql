with source as (

    select * from {{ source('tap_netsuite', 'customer')}}

), stage as (

SELECT
source.id,
source.externalid,
source.companyname,
source.phone,
source.fax,
source.url,
source.comments,
source.subsidiary
FROM source


), final as (

    select * from stage

)

select * from final
