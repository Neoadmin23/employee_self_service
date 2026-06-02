# Copyright (c) 2024, Nesscale Solutions Private Limited and contributors
# For license information, please see license.txt

import frappe
from employee_self_service.notifications.manager import create_notification


def after_expense_insert(doc, method):
    """
    Create notification when Expense Claim is submitted.
    """
    # Get employee user_id and name
    employee_user_id = frappe.db.get_value("Employee", doc.employee, "user_id")
    employee_name = frappe.db.get_value("Employee", doc.employee, "employee_name")
    if not employee_user_id:
        return

    # Notify Employee
    create_notification(
        recipient=employee_user_id,
        subject="Expense Claim Submitted",
        message="Your expense claim has been submitted successfully.",
        reference_doctype=doc.doctype,
        reference_name=doc.name
    )

    # Notify Expense Approver
    if doc.expense_approver:
        approver_user_id = frappe.db.get_value("Employee", doc.expense_approver, "user_id")
        if approver_user_id:
            create_notification(
                recipient=approver_user_id,
                subject="New Expense Claim Request",
                message=f"{employee_name} submitted an expense claim.",
                reference_doctype=doc.doctype,
                reference_name=doc.name
            )

    # Notify HR Managers
    hr_managers = frappe.get_all("Has Role", filters={"role": "HR Manager"}, fields=["parent"])
    for hr in hr_managers:
        hr_user_id = hr.parent
        # Optionally, check if the user is enabled
        if frappe.db.get_value("User", hr_user_id, "enabled"):
            create_notification(
                recipient=hr_user_id,
                subject="New Expense Claim Request",
                message=f"{employee_name} submitted an expense claim.",
                reference_doctype=doc.doctype,
                reference_name=doc.name
            )


def after_expense_update(doc, method):
    """
    Create notification when Expense Claim status changes.
    """
    # Get employee user_id
    employee_user_id = frappe.db.get_value("Employee", doc.employee, "user_id")
    if not employee_user_id:
        return

    # Check if status changed
    if doc.get_doc_before_save():
        old_status = doc.get_doc_before_save().status
        new_status = doc.status
        if old_status != new_status:
            # Map status to subject
            subject_map = {
                "Approved": "Expense Claim Approved",
                "Rejected": "Expense Claim Rejected"
            }
            subject = subject_map.get(new_status)
            if subject:
                message = f"Your expense claim has been {new_status.lower()}."
                create_notification(
                    recipient=employee_user_id,
                    subject=subject,
                    message=message,
                    reference_doctype=doc.doctype,
                    reference_name=doc.name
                )