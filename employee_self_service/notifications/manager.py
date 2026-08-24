# Copyright (c) 2024, Nesscale Solutions Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, get_url_to_form

def create_notification(recipient, subject, message, reference_doctype=None, reference_name=None):
    """
    Create a new ESS Notification Log record.

    Args:
        recipient (str): The recipient of the notification.
        subject (str): The subject of the notification.
        message (str): The message body of the notification.
        reference_doctype (str, optional): The DocType of the reference document.
        reference_name (str, optional): The name of the reference document.

    Returns:
        str: The name of the created ESS Notification Log document, or None if duplicate.
    """
    try:
        # Create a new ESS Notification Log document
        notification_log = frappe.get_doc({
            "doctype": "ESS Notification Log",
            "recipient": recipient,
            "subject": subject,
            "message": message,
            "document_type": reference_doctype,
            "reference_document": reference_doctype,
            "reference_name": reference_name,
            "read": 0
        })

        # Insert the document ignoring permissions
        notification_log.insert(ignore_permissions=True)

        # Commit the transaction
        frappe.db.commit()

        # Log the creation
        frappe.logger().info(f"ESS Notification Log created: {notification_log.name} for recipient: {recipient}")

        # Return the name of the created notification log
        return notification_log.name
    except Exception as e:
        frappe.log_error(
            title=_("Failed to create ESS Notification Log"),
            message=frappe.get_traceback()
        )
        raise


def sync_to_frappe_notification_log(doc, method):
    """
    Sync ESS Notification Log to Frappe's built-in Notification Log.
    Called automatically when an ESS Notification Log is created.
    Uses enqueue to ensure the sync never fails silently and is retried if needed.
    Passes all data directly to the background job to avoid "document not found" errors.
    """
    try:
        if not doc.recipient:
            frappe.logger().warning(
                f"ESS Notification Log {doc.name} has no recipient, skipping Frappe sync"
            )
            return

        # Enqueue the sync as a background job with all data passed directly
        # This avoids "document not found" errors if the ESS Notification Log
        # is deleted or the background job runs in a different context
        frappe.enqueue(
            "employee_self_service.notifications.manager._sync_single_to_frappe",
            recipient=doc.recipient,
            subject=doc.subject,
            message=doc.message,
            reference_document=doc.reference_document,
            reference_name=doc.reference_name,
            queue="short",
            timeout=300,
            now=frappe.flags.in_test,
        )

    except Exception as e:
        error_msg = f"Failed to enqueue Frappe Notification Log sync for ESS Notification Log {doc.name}: {str(e)}\n{frappe.get_traceback()}"
        frappe.log_error(
            title=_("Failed to enqueue Frappe Notification Log sync"),
            message=error_msg
        )
        # Don't raise - we don't want to break the original ESS notification creation
        # The error is logged and can be investigated


def _sync_single_to_frappe(recipient, subject, message, reference_document, reference_name):
    """
    Background job to sync a single ESS Notification Log to Frappe Notification Log.
    This is called by sync_to_frappe_notification_log via enqueue.
    All data is passed directly as parameters to avoid database fetch issues.
    """
    try:
        if not recipient:
            frappe.logger().warning(
                f"Frappe sync skipped: no recipient provided"
            )
            return

        # Check if Frappe Notification Log already exists for this notification
        existing = frappe.db.exists(
            "Notification Log",
            {
                "for_user": recipient,
                "subject": subject,
                "document_type": reference_document,
                "document_name": reference_name,
            }
        )
        if existing:
            frappe.logger().info(
                f"Frappe Notification Log already exists for recipient: {recipient}, subject: {subject}"
            )
            return

        # Build link to reference document
        link = None
        if reference_document and reference_name:
            try:
                link = get_url_to_form(reference_document, reference_name)
            except Exception as e:
                frappe.logger().warning(
                    f"Could not build link for notification to {recipient}: {str(e)}"
                )
                link = None

        # Create Frappe Notification Log
        frappe.flags.ignore_ess_notification_sync = True
        frappe_notification = frappe.get_doc({
            "doctype": "Notification Log",
            "for_user": recipient,
            "subject": subject,
            "type": "Alert",
            "email_content": message,
            "document_type": reference_document,
            "document_name": reference_name,
            "from_user": frappe.session.user,
            "read": 0,
            "link": link,
        })

        frappe_notification.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.flags.ignore_ess_notification_sync = False

        frappe.logger().info(
            f"Frappe Notification Log synced for recipient: {recipient}, subject: {subject}"
        )

    except Exception as e:
        error_msg = f"Failed to sync to Frappe Notification Log for recipient {recipient}: {str(e)}\n{frappe.get_traceback()}"
        frappe.log_error(
            title=_("Failed to sync ESS Notification Log to Frappe Notification Log"),
            message=error_msg
        )
        # Don't raise - background job failures are logged and can be retried
        # Raising would cause the job to be retried unnecessarily


@frappe.whitelist()
def mark_notification_as_read(notification_name):
    """
    Mark an ESS Notification Log as read.

    Args:
        notification_name (str): The name of the ESS Notification Log document.

    Returns:
        dict: Success response with notification details.
    """
    try:
        # Fetch the ESS Notification Log document
        if not frappe.db.exists("ESS Notification Log", notification_name):
            frappe.throw(_("Notification Log not found"))

        notification = frappe.get_doc("ESS Notification Log", notification_name)

        # Validate that the recipient matches the current user
        if notification.recipient != frappe.session.user:
            frappe.throw(_("You are not authorized to mark this notification as read"))

        # Update read status
        notification.read = 1

        # Save with ignore_permissions
        notification.save(ignore_permissions=True)

        # Commit the transaction
        frappe.db.commit()

        return {
            "success": True,
            "notification": notification_name,
            "read": 1
        }
    except Exception as e:
        frappe.log_error(
            title=_("Failed to mark notification as read"),
            message=frappe.get_traceback()
        )
        frappe.throw(str(e))