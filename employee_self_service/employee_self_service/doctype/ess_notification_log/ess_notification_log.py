import frappe
from frappe.model.document import Document
from employee_self_service.employee_self_service.doctype.push_notification.push_notification import _send_to_tokens


class ESSNotificationLog(Document):
    def after_insert(self):
        if not self.recipient:
            return

        tokens = frappe.get_all(
            "Employee Device Info",
            filters={"user": self.recipient, "token": ["is", "set"]},
            pluck="token",
        )
        if not tokens:
            return

        frappe.enqueue(
            "employee_self_service.employee_self_service.doctype.ess_notification_log.ess_notification_log.send_push_for_log",
            queue="short",
            tokens=tokens,
            title=self.subject,
            body=self.message,
            reference_doctype=self.reference_document,
            reference_name=self.reference_name,
        )


def send_push_for_log(tokens, title, body, reference_doctype=None, reference_name=None):
    _send_to_tokens(tokens, title, body, reference_doctype=reference_doctype, reference_name=reference_name)
