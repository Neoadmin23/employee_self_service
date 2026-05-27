import frappe
from frappe import _

@frappe.whitelist()
def get_ess_admin_details():
    """
    Returns whether the current logged-in user is an ESS Admin.
    Used by the mobile app to decide whether to show Admin Panel.
    """
    user = frappe.session.user

    admin_record = frappe.db.get_value(
        "ESS Admin User",
        {"user": user, "is_active": 1},
        ["name", "role", "email", "full_name"],
        as_dict=True
    )

    if not admin_record:
        return {"is_admin": False}

    return {
        "is_admin": True,
        "admin_id": admin_record.name,
        "role": admin_record.role,
        "email": admin_record.email,
        "full_name": admin_record.full_name
    }