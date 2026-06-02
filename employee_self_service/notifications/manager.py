# Copyright (c) 2024, Nesscale Solutions Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date

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
        # Check for duplicate notification in the last 5 minutes
        five_minutes_ago = add_to_date(now_datetime(), minutes=-5)
        duplicate_exists = frappe.db.exists(
            "ESS Notification Log",
            {
                "recipient": recipient,
                "subject": subject,
                "reference_name": reference_name,
                "creation": [">=", five_minutes_ago],
            }
        )
        if duplicate_exists:
            frappe.logger().info(f"Duplicate ESS Notification Log skipped for recipient: {recipient}, subject: {subject}, reference_name: {reference_name}")
            return None

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