field_map_1 = {
    "title": "[name='title']",
    "purpose_id": "[name='purpose_id']",
    "value_premise_id": "[name='value_premise_id']",
    "value_base": "[name='value_base_id']",
    "report_type": "[name='report_type']",
    "client_name": "[name='client[0][name]']",
    "telephone": "[name='client[0][telephone]']",
    "email": "[name='client[0][email]']",
    "valued_at": "[name='valued_at']",
    "submitted_at": "[name='submitted_at']",
    "assumptions": "[name='assumptions']",
    "special_assumptions": "[name='special_assumptions']",
    "value": "[name='value']",
    "valuation_currency": "[name='currency_id']",
    "report_asset_file": "[name='report_file']",
    "has_other_users": "[name='has_user']",
}

field_types_1 = {
    "title": "text",
    "purpose_id": "select",
    "value_premise_id": "select",
    "value_base": "select",
    "report_type": "radio",
    "valued_at": "text",
    "submitted_at": "text",
    "client_name": "text",
    "telephone": "text",
    "email": "text",
    "assumptions": "text",
    "special_assumptions": "text",
    "final_value": "text",
    "valuation_currency": "select",
    "report_asset_file": "file",
    "has_other_users": "checkbox",
}

field_map_2 = {
    "number_of_macros": "[id='macros']"
}

field_types_2 = {
    "number_of_macros": "text"
}

field_map_3 = {
    "asset_type": "[name='asset_type']",
    "asset_name": "[name='asset_name']",
    "asset_usage_id": "[name='asset_usage_id']",
    "value_base": "[id='value_base_id']",
    "inspection_date": "[name='inspected_at']",
    "final_value": "[name='value']",
    "production_capacity": "[name='production_capacity']",
    "production_capacity_measuring_unit": "[name='production_capacity_measuring_unit']",
    "owner_name": "[name='owner_name']",
    "product_type": "[name='product_type']",

    "market_approach": "[id='approach1']",
    "market_approach_value": "[name='approach[1][value]']",
    "cost_approach": "[id='approach3']",
    "cost_approach_value": "[name='approach[3][value]']",

    "country": "[id='select2-country_id-container']",
    "region": "[id='select2-region-container']",
    "city": "[id='select2-city-container']",
}

field_types_3 = {
    "asset_type": "text",
    "asset_name": "text",
    "asset_usage_id": "select",
    "value_base": "select",
    "final_value": "text",
    "production_capacity": "text",
    "production_capacity_measuring_unit": "text",
    "owner_name": "text",
    "product_type": "text",

    "market_approach": "select",
    "market_approach_value": "text",
    "cost_approach": "select",
    "cost_approach_value": "text",
    
    "country": "location",
    "region": "location",
    "city": "location",

    "inspection_date": "date",
}

form_steps = [
    {"field_map": field_map_1, "field_types": field_types_1},
    {"field_map": field_map_2, "field_types": field_types_2},
]

macro_form_config = {
    "field_map": field_map_3,
    "field_types": field_types_3,
}
