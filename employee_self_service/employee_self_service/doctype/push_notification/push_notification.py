import json

import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password
import firebase_admin
from firebase_admin import credentials, messaging

_firebase_app = None


def get_firebase_app():
    global _firebase_app
    if _firebase_app:
        return _firebase_app
    raw = get_decrypted_password(
        "Employee Self Service Settings",
        "Employee Self Service Settings",
        "firebase_service_account_json",
    )
    if not raw:
        frappe.throw("Firebase Service Account JSON is not configured in Employee Self Service Settings")
    cred = credentials.Certificate(json.loads(raw))
    _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


def _send_to_tokens(tokens, title, body, notification_type=None, reference_doctype=None, reference_name=None):
    get_firebase_app()
    data = {
        "notification_type": notification_type or "",
        "reference_doctype": reference_doctype or "",
        "reference_name": reference_name or "",
    }
    results = []
    for token in tokens:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=data,
                token=token,
            )
            message_id = messaging.send(message)
            results.append({"token": token, "status": "sent", "id": message_id})
        except messaging.UnregisteredError:
            frappe.db.delete("Employee Device Info", {"token": token})
            results.append({"token": token, "status": "invalid_token_removed"})
        except Exception as e:
            frappe.log_error(title="FCM Push Send Error", message=f"Token: {token}\n{frappe.get_traceback()}")
            results.append({"token": token, "status": "failed", "error": str(e)})
    return results


class PushNotification(Document):
    def after_insert(self):
        if self.send_for == "Single User":
            token = frappe.db.get_value("Employee Device Info", filters={"user": self.user}, fieldname="token")
            if token:
                self.response = json.dumps(
                    _send_to_tokens([token], self.title, self.message, self.notification_type)
                )
                self.save()

        elif self.send_for == "Multiple User":
            users = [nu.user for nu in self.users]
            tokens = frappe.get_all(
                "Employee Device Info",
                filters=[["user", "in", users], ["token", "is", "set"]],
                pluck="token",
            )
            if tokens:
                self.response = json.dumps(
                    _send_to_tokens(tokens, self.title, self.message, self.notification_type)
                )
                self.save()

        elif self.send_for == "All User":
            tokens = frappe.get_all("Employee Device Info", filters={"token": ["is", "set"]}, pluck="token")
            if tokens:
                self.response = json.dumps(
                    _send_to_tokens(tokens, self.title, self.message, self.notification_type)
                )
                self.save()


@frappe.whitelist()
def send_single_notification(registration_id, title=None, message=None, user=None, notification_type=None):
    return _send_to_tokens([registration_id], title, message, notification_type)


@frappe.whitelist()
def send_multiple_notification(registration_ids, users=None, title=None, message=None, notification_type=None):
    return _send_to_tokens(registration_ids, title, message, notification_type)


def create_push_notification(title, message, send_for, notification_type, user=None):
    push_notification_doc = frappe.new_doc("Push Notification")
    push_notification_doc.title = title
    push_notification_doc.message = message
    push_notification_doc.send_for = send_for
    push_notification_doc.user = user
    push_notification_doc.notification_type = notification_type
    push_notification_doc.save(ignore_permissions=True)
