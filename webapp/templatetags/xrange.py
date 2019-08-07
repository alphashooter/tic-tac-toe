from django import template

register = template.Library()


@register.filter('xrange')
def xrange(value):
    return range(value)
