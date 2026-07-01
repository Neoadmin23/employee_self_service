# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ESSAdminUser(Document):
    def validate(self):
        if self.email and not self.full_name:
            # Auto-fill full name from User if possible
            user_full_name = frappe.db.get_value("User", self.user, "full_name")
            if user_full_name:
                self.full_name = user_full_name


@frappe.whitelist(allow_guest=True)
def get_admin_user(user):
    try:
        admin_user = frappe.get_all(
            "ESS Admin User",
            filters={"user": user, "is_active": 1},
            fields=["user", "full_name", "email", "role", "is_active"],
        )

        if not admin_user:
            return {
                "success": False,
                "message": "User is not admin. Please register it as Company admin.",
                "data": None,
            }

        admin_user = admin_user[0]
        admin_user["allowed_companies"] = frappe.get_all(
            "ESS Admin User Company",
            filters={"parent": admin_user["user"]},
            fields=["company"],
        )

        return {
            "success": True,
            "message": "Admin User Get Successfully",
            "data": admin_user,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Admin User Error")
        return {
            "success": False,
            "message": str(e),
            "data": None,
        }
