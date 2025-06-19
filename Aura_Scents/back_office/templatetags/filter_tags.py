from django import template
from urllib.parse import urlencode

register = template.Library()

@register.filter
def subtract(value, arg):
    return value - arg

@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    try:
        request = context['request']
        query_dict = request.GET.copy()
    except KeyError:
        query_dict = {}  # Fallback to empty dict if request is missing
    query_dict.update(kwargs)
    query_string = urlencode(query_dict)
    return f'?{query_string}' if query_string else ''