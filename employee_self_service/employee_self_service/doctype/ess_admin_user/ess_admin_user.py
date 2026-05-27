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
