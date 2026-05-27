import frappe
from frappe.custom.doctype.custom_field.custom_field import (
    create_custom_fields as _create_custom_fields,
)

from employee_self_service.constants.custom_fields import CUSTOM_FIELDS


def after_install():
    create_custom_fields()
    add_default_language_in_ess_settings()
    create_ess_admin_manager_role()


def create_custom_fields():
    # Removed print statement: Creating custom fields
    _create_custom_fields(get_all_custom_fields(), ignore_validate=True)
    # Removed print statement: Custom fields added


def get_all_custom_fields():
    result = {}

    # for custom_fields in CUSTOM_FIELDS:
    for doctypes, fields in CUSTOM_FIELDS.items():
        if isinstance(fields, dict):
            fields = [fields]

        result.setdefault(doctypes, []).extend(fields)
    return result


def add_default_language_in_ess_settings():
    if frappe.db.exists("DocType", "Employee Self Service Settings"):
        ess_settings = frappe.get_doc(
            "Employee Self Service Settings", "Employee Self Service Settings"
        )
        if not len(ess_settings.get("ess_language")) >= 1:
            ess_settings.append(
                "ess_language", dict(language="en", language_name="English")
            )
            ess_settings.save(ignore_permissions=True)


def create_ess_admin_manager_role():
    """Create ESS Admin Manager role if it doesn't exist."""
    if not frappe.db.exists("Role", "ESS Admin Manager"):
        frappe.get_doc(
            doctype="Role",
            role_name="ESS Admin Manager"
        ).insert(ignore_permissions=True)
