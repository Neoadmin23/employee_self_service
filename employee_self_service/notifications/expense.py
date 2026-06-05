# Copyright (c) 2024, Nesscale Solutions Private Limited and contributors
# For license information, please see license.txt

import frappe
from employee_self_service.notifications.manager import create_notification


def after_expense_insert(doc, method):
    """
    Create notification when Expense Claim is created.
    Notifies the employee that their expense claim has been submitted.
    """
    # Get employee user_id and name
    employee_user_id = frappe.db.get_value("Employee", doc.employee, "user_id")
    if not employee_user_id:
        frappe.logger().warning(
            f"[EXPENSE NOTIFICATION] No user_id found for employee {doc.employee}"
        )
        return

    # Notify Employee only (approver notification is handled on_submit)
    try:
        create_notification(
            recipient=employee_user_id,
            subject="Expense Claim Submitted",
            message="Your expense claim has been submitted successfully.",
            reference_doctype=doc.doctype,
            reference_name=doc.name
        )
        frappe.logger().info(
            f"[EXPENSE NOTIFICATION] Employee notification created for {employee_user_id}"
        )
    except Exception as e:
        frappe.log_error(
            title=_("Failed to create expense claim employee notification"),
            message=frappe.get_traceback()
        )


def after_expense_submit(doc, method):
    """
    Create notification when Expense Claim is submitted.
    Notifies the expense approver and HR Managers about the new request.
    """
    # Get employee details
    employee_user_id = frappe.db.get_value("Employee", doc.employee, "user_id")
    employee_name = frappe.db.get_value("Employee", doc.employee, "employee_name")

    if not employee_user_id:
        frappe.logger().warning(
            f"[EXPENSE NOTIFICATION] No user_id found for employee {doc.employee}"
        )
        return

    # Notify Expense Approver
    if doc.expense_approver:
        try:
            approver_user_id = frappe.db.get_value("Employee", doc.expense_approver, "user_id")
            if approver_user_id:
                create_notification(
                    recipient=approver_user_id,
                    subject="New Expense Claim Request",
                    message=f"{employee_name} submitted an expense claim.",
                    reference_doctype=doc.doctype,
                    reference_name=doc.name
                )
                frappe.logger().info(
                    f"[EXPENSE NOTIFICATION] Approver notification created for {approver_user_id}"
                )
        except Exception as e:
            frappe.log_error(
                title=_("Failed to create expense claim approver notification"),
                message=frappe.get_traceback()
            )

    # Notify HR Managers
    try:
        hr_managers = frappe.get_all("Has Role", filters={"role": "HR Manager"}, fields=["parent"])
        for hr in hr_managers:
            hr_user_id = hr.parent
            if frappe.db.get_value("User", hr_user_id, "enabled"):
                create_notification(
                    recipient=hr_user_id,
                    subject="New Expense Claim Request",
                    message=f"{employee_name} submitted an expense claim.",
                    reference_doctype=doc.doctype,
                    reference_name=doc.name
                )
                frappe.logger().info(
                    f"[EXPENSE NOTIFICATION] HR Manager notification created for {hr_user_id}"
                )
    except Exception as e:
        frappe.log_error(
            title=_("Failed to create expense claim HR manager notification"),
            message=frappe.get_traceback()
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