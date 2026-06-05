# Copyright (c) 2024, Nesscale Solutions Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_to_date, now_datetime
from employee_self_service.notifications.manager import create_notification


def after_leave_application_insert(doc, method):
    """
    Create notifications when Leave Application is created.
    Notifies both the employee and the leave approver.
    """
    # Get employee user_id and name
    employee_user_id = frappe.db.get_value("Employee", doc.employee, "user_id")
    employee_name = frappe.db.get_value("Employee", doc.employee, "employee_name")

    if not employee_user_id:
        frappe.logger().warning(
            f"[LEAVE NOTIFICATION] No user_id found for employee {doc.employee}"
        )
        return

    # Notify Employee
    try:
        create_notification(
            recipient=employee_user_id,
            subject="Leave Application Submitted",
            message="Your leave application has been submitted successfully.",
            reference_doctype=doc.doctype,
            reference_name=doc.name
        )
        frappe.logger().info(
            f"[LEAVE NOTIFICATION] Employee notification created for {employee_user_id}"
        )
    except Exception as e:
        frappe.log_error(
            title=_("Failed to create leave application employee notification"),
            message=frappe.get_traceback()
        )

    # Notify Leave Approver (even if same as employee - both notifications are created)
    if doc.leave_approver:
        try:
            create_notification(
                recipient=doc.leave_approver,
                subject="New Leave Application Request",
                message=f"{employee_name} submitted a leave application.",
                reference_doctype=doc.doctype,
                reference_name=doc.name
            )
            frappe.logger().info(
                f"[LEAVE NOTIFICATION] Approver notification created for {doc.leave_approver}"
            )
        except Exception as e:
            frappe.log_error(
                title=_("Failed to create leave application approver notification"),
                message=frappe.get_traceback()
            )


def after_leave_application_submit(doc, method):
    """
    Create notification when Leave Application is submitted.
    This is a backup notification for the approver in case on_submit fires
    after the initial insert notifications.
    """
    # Get employee details
    employee_user_id = frappe.db.get_value("Employee", doc.employee, "user_id")
    employee_name = frappe.db.get_value("Employee", doc.employee, "employee_name")

    if not employee_user_id:
        frappe.logger().warning(
            f"[LEAVE NOTIFICATION] No user_id found for employee {doc.employee}"
        )
        return

    # Notify Leave Approver (backup - only if not already notified)
    if doc.leave_approver:
        try:
            # Check if approver was already notified during after_insert
            existing = frappe.db.exists(
                "ESS Notification Log",
                {
                    "recipient": doc.leave_approver,
                    "subject": "New Leave Application Request",
                    "reference_name": doc.name,
                    "creation": [">=", add_to_date(now_datetime(), minutes=-10)],
                }
            )
            if existing:
                frappe.logger().info(
                    f"[LEAVE NOTIFICATION] Approver already notified for {doc.name}, skipping on_submit notification"
                )
                return

            create_notification(
                recipient=doc.leave_approver,
                subject="New Leave Application Request",
                message=f"{employee_name} submitted a leave application.",
                reference_doctype=doc.doctype,
                reference_name=doc.name
            )
            frappe.logger().info(
                f"[LEAVE NOTIFICATION] Approver notification created on_submit for {doc.leave_approver}"
            )
        except Exception as e:
            frappe.log_error(
                title=_("Failed to create leave application approver notification on_submit"),
                message=frappe.get_traceback()
            )


def after_leave_application_update(doc, method):
    """
    Create notification when Leave Application status changes.
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
                "Approved": "Leave Application Approved",
                "Rejected": "Leave Application Rejected",
                "Cancelled": "Leave Application Cancelled"
            }
            subject = subject_map.get(new_status)
            if subject:
                message = f"Your leave application has been {new_status.lower()}."
                try:
                    create_notification(
                        recipient=employee_user_id,
                        subject=subject,
                        message=message,
                        reference_doctype=doc.doctype,
                        reference_name=doc.name
                    )
                except Exception as e:
                    frappe.log_error(
                        title=_("Failed to create leave application status notification"),
                        message=frappe.get_traceback()
                    )