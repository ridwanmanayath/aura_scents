from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})

@register.filter
def status_color(status):
    mapping = {
        "Processing": "text-blue-600",
        "Delivered": "text-green-700",
        "Cancelled": "text-red-600",
        "Returned": "text-yellow-600",
    }
    return mapping.get(status, "text-gray-700")
