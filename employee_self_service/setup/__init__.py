import frappe
from frappe.custom.doctype.custom_field.custom_field import (
    create_custom_fields as _create_custom_fields,
)

from employee_self_service.constants.custom_fields import CUSTOM_FIELDS


def after_install():
    create_custom_fields()
    add_default_language_in_ess_settings()
    create_ess_admin_manager_role()
    update_attendance_request_reason_options()


def update_attendance_request_reason_options():
    property_setter_name = "attendance_request-reason-options"
    new_options = "Work From Home\nOn Duty\nLocation Exception"
    if not frappe.db.exists("Property Setter", property_setter_name):
        frappe.get_doc({
            "doctype": "Property Setter",
            "name": property_setter_name,
            "doctype_or_field": "DocField",
            "doc_type": "Attendance Request",
            "field_name": "reason",
            "property": "options",
            "value": new_options,
        }).insert(ignore_permissions=True)


def after_migrate():
    after_install()
    create_default_document_masters()


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


def create_default_document_masters():
    categories = [
        "Identity",
        "Employment",
        "Education",
        "Banking",
        "Medical",
        "Immigration",
        "Other",
    ]

    document_types = [
        {"name": "Passport", "category": "Identity"},
        {"name": "Aadhaar", "category": "Identity"},
        {"name": "PAN Card", "category": "Identity"},
        {"name": "Emirates ID", "category": "Identity"},
        {"name": "Driving License", "category": "Identity"},
        {"name": "Visa", "category": "Identity"},
        {"name": "Resume", "category": "Employment"},
        {"name": "Offer Letter", "category": "Employment"},
        {"name": "Employment Contract", "category": "Employment"},
        {"name": "Experience Letter", "category": "Employment"},
        {"name": "Degree Certificate", "category": "Education"},
        {"name": "Diploma Certificate", "category": "Education"},
        {"name": "Training Certificate", "category": "Education"},
        {"name": "Cancelled Cheque", "category": "Banking"},
        {"name": "Bank Passbook", "category": "Banking"},
        {"name": "IBAN Letter", "category": "Banking"},
        {"name": "Medical Certificate", "category": "Medical"},
        {"name": "Insurance Card", "category": "Medical"},
        {"name": "Work Permit", "category": "Immigration"},
        {"name": "Residence Permit", "category": "Immigration"},
        {"name": "Other", "category": "Other"},
    ]

    for category in categories:
        if not frappe.db.exists("Document Category", {"category_name": category}):
            frappe.get_doc({
                "doctype": "Document Category",
                "category_name": category,
            }).insert(ignore_permissions=True)

    for doc_type in document_types:
        if not frappe.db.exists("Document Type", {"document_type_name": doc_type["name"]}):
            frappe.get_doc({
                "doctype": "Document Type",
                "document_type_name": doc_type["name"],
                "document_category": doc_type["category"],
            }).insert(ignore_permissions=True)

    frappe.db.commit()
