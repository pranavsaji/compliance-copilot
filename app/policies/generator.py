from jinja2 import Template

OPA_TEMPLATE = Template("""
package compliance.{{ package }}

default allow = false

allow {
  input.{{ resource }}.{{ field }} == {{ expected | tojson }}
}
""")

def generate_opa_policy(package: str, resource: str, field: str, expected):
    return OPA_TEMPLATE.render(package=package, resource=resource, field=field, expected=expected)
