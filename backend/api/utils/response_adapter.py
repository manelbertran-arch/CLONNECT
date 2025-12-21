"""Response adapter for frontend compatibility"""

def to_camel_case(snake_str: str) -> str:
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def add_camel_case_aliases(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    result = {}
    for key, value in data.items():
        result[key] = value
        camel_key = to_camel_case(key)
        if camel_key != key:
            result[camel_key] = value
        if isinstance(value, dict):
            result[key] = add_camel_case_aliases(value)
            if camel_key != key:
                result[camel_key] = add_camel_case_aliases(value)
        elif isinstance(value, list):
            result[key] = [add_camel_case_aliases(item) if isinstance(item, dict) else item for item in value]
            if camel_key != key:
                result[camel_key] = result[key]
    return result

def adapt_dashboard_response(data: dict) -> dict:
    adapted = add_camel_case_aliases(data)
    if 'bot_active' in data:
        adapted['botActive'] = data['bot_active']
        adapted['clone_active'] = data['bot_active']
    if 'creator_name' in data:
        adapted['creatorName'] = data['creator_name']
    return adapted

def adapt_lead_response(lead: dict) -> dict:
    adapted = add_camel_case_aliases(lead)
    if 'id' in lead:
        adapted['follower_id'] = lead['id']
    if 'purchase_intent' in lead:
        adapted['purchaseIntent'] = lead['purchase_intent']
    return adapted

def adapt_leads_response(leads: list) -> list:
    return [adapt_lead_response(lead) for lead in leads]

def adapt_product_response(product: dict) -> dict:
    adapted = add_camel_case_aliases(product)
    if 'is_active' in product:
        adapted['isActive'] = product['is_active']
    return adapted

def adapt_products_response(products: list) -> list:
    return [adapt_product_response(p) for p in products]
