import json

import frappe
from frappe import _
from frappe.utils import pretty_date, today

from employee_self_service.mobile.v1.api_utils import (
    ess_validate,
    exception_handler,
    gen_response,
)

TASK_FIELDS = ["_assign", "owner", "status"]
ERR = {
    "not_assigned": "Task is not assigned to any user",
    "unauthorized": "You are not authorized to update this task",
    "id_required": "Task ID is required",
    "progress_required": "Progress is required",
    "status_required": "New status is required",
    "already_updated": "Status is already up to date",
}


def validate_assign_task(task_data):
    if not task_data.get("_assign"):
        frappe.throw(ERR["not_assigned"])

    try:
        assigned_users = json.loads(task_data["_assign"])
    except Exception:
        assigned_users = []

    if (
        frappe.session.user not in assigned_users
        and frappe.session.user != task_data.get("owner")
    ):
        frappe.throw(ERR["unauthorized"])


@frappe.whitelist()
@ess_validate(methods=["POST"])
def update_task_status(task_id=None, new_status=None):
    try:
        if not task_id:
            return gen_response(500, ERR["id_required"])
        if not new_status:
            return gen_response(500, ERR["status_required"])

        task_data = frappe.db.get_value(
            "Task", {"name": task_id}, TASK_FIELDS, as_dict=True
        )
        if not task_data:
            return gen_response(404, "Task not found")

        validate_assign_task(task_data)

        if task_data.status == new_status:
            return gen_response(500, ERR["already_updated"])

        update_values = {"status": new_status}
        if new_status == "Completed":
            update_values.update(
                {"completed_by": frappe.session.user, "completed_on": today()}
            )

        frappe.db.set_value("Task", task_id, update_values)
        return gen_response(200, "Task status updated successfully")
    except frappe.PermissionError:
        return gen_response(403, ERR["unauthorized"])
    except Exception as e:
        return exception_handler(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def update_task_progress(task_id=None, progress=None):
    try:
        if not task_id:
            return gen_response(500, ERR["id_required"])
        if progress is None:
            return gen_response(500, ERR["progress_required"])

        task_data = frappe.db.get_value(
            "Task", task_id, ["_assign", "owner"], as_dict=True
        )
        if not task_data:
            return gen_response(404, "Task not found")

        validate_assign_task(task_data)
        frappe.db.set_value("Task", task_id, "progress", progress)
        return gen_response(200, "Progress updated successfully")
    except frappe.PermissionError:
        return gen_response(403, ERR["unauthorized"])
    except Exception as e:
        return exception_handler(e)


def update_task_filters(filters, today_task):
    if isinstance(filters, str):
        filters = json.loads(filters)
    if today_task:
        filters.append(["Task", "exp_end_date", "=", today()])
    return filters


def fetch_user_details(emails):
    return (
        frappe.get_all(
            "User",
            filters={"email": ["in", emails]},
            fields=["name", "full_name", "full_name as user", "user_image"],
            order_by="creation asc",
        )
        if emails
        else []
    )


def fetch_project_map(project_ids):
    if not project_ids:
        return {}
    return {
        row.name: row.project_name
        for row in frappe.get_all(
            "Project",
            filters={"name": ["in", project_ids]},
            fields=["name", "project_name"],
        )
    }


def fetch_user(user_id):
    if not user_id:
        return None
    return frappe.db.get_value(
        "User",
        user_id,
        ["name", "full_name", "full_name as user", "user_image"],
        as_dict=True,
    )


def fetch_comments(task_id):
    comments = frappe.get_all(
        "Comment",
        filters={
            "reference_name": task_id,
            "comment_type": "Comment",
        },
        fields=[
            "content as comment",
            "comment_by",
            "reference_name",
            "creation",
            "comment_email",
        ],
    )
    for comment in comments:
        comment["commented"] = pretty_date(comment["creation"])
        comment["creation"] = comment["creation"].strftime("%I:%M %p")
        comment["user_image"] = frappe.db.get_value(
            "User", comment["comment_email"], "user_image", cache=True
        )
    return comments


def send_task_notifications(task_doc, assigned_user, creator_user):
    try:
        if not assigned_user:
            return

        employee_name = frappe.db.get_value(
            "Employee",
            {"user_id": assigned_user},
            "name"
        )

        if not employee_name:
            frappe.log_error(
                f"Employee not found for user: {assigned_user}",
                "Task Notification"
            )
            return

        reports_to_employee = frappe.db.get_value(
            "Employee",
            employee_name,
            "reports_to"
        )

        manager_user = None

        if reports_to_employee:
            manager_user = frappe.db.get_value(
                "Employee",
                reports_to_employee,
                "user_id"
            )

        created_any = False

        # Notification for assigned employee
        frappe.get_doc(
            {
                "doctype": "ESS Notification Log",
                "notification_name": "Task Created",
                "document_type": "Task",
                "subject": f"Task Created: {task_doc.name}",
                "message": (
                    f"Your task '{task_doc.subject}' has been created."
                ),
                "recipient": assigned_user,
                "reference_document": "Task",
                "reference_name": task_doc.name,
                "read": 0,
            }
        ).insert(ignore_permissions=True)
        created_any = True

        # Notification for reporting manager
        if manager_user and manager_user != assigned_user:
            employee_display_name = frappe.db.get_value(
                "Employee",
                {"user_id": assigned_user},
                "employee_name"
            ) or assigned_user

            frappe.get_doc(
                {
                    "doctype": "ESS Notification Log",
                    "notification_name": "Task Created",
                    "document_type": "Task",
                    "subject": f"New Task Created: {task_doc.name}",
                    "message": (
                        f"{employee_display_name} has created a new task: "
                        f"{task_doc.subject}"
                    ),
                    "recipient": manager_user,
                    "read": 0,
                    "reference_document": "Task",
                    "reference_name": task_doc.name,
                }
            ).insert(ignore_permissions=True)

        # Remove old "Task Assigment" notifications caused by the generic
        # ESS Notification rule firing on ToDo.after_insert for this task.
        if created_any:
            frappe.db.delete(
                "ESS Notification Log",
                {
                    "notification_name": "Task Assigment",
                    "reference_document": "Task",
                    "reference_name": task_doc.name,
                },
            )

            # Remove "Mention In Comment" ESS Notification Logs created by
            # the feedback loop: ESS Notification Log -> Frappe Notification Log
            # -> wildcard hook -> ESS Notification Log again.
            frappe.db.delete(
                "ESS Notification Log",
                {
                    "notification_name": "Mention In Comment",
                    "document_type": "Task",
                    "reference_name": task_doc.name,
                },
            )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Task Notification Error"
        )


@frappe.whitelist()
@ess_validate(methods=["POST"])
def add_task_comment(task_id=None, comment=None):
    try:
        if not task_id:
            return gen_response(500, "Task ID is required")

        if not comment or not comment.strip():
            return gen_response(500, "Comment is required")

        task_data = frappe.db.get_value(
            "Task",
            task_id,
            ["name", "_assign", "owner"],
            as_dict=True,
        )

        if not task_data:
            return gen_response(404, "Task not found")

        # Check whether logged-in employee is assigned to this task
        validate_assign_task(task_data)

        comment_doc = frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Comment",
                "reference_doctype": "Task",
                "reference_name": task_id,
                "content": comment.strip(),
            }
        )

        comment_doc.insert()

        return gen_response(
            200,
            "Comment added successfully",
            {
                "name": comment_doc.name,
            },
        )

    except frappe.PermissionError:
        return gen_response(403, "Not permitted to add comment")

    except Exception as e:
        return exception_handler(e)

@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_task_list(start=0, page_length=10, filters=None, today_task=False):
    try:
        if not frappe.has_permission("Task", "read"):
            frappe.throw(_("Not permitted to read Task"), frappe.PermissionError)

        filters = update_task_filters(filters, today_task)
        filters.append(["Task", "_assign", "like", f"%{frappe.session.user}%"])
        tasks = frappe.get_list(
            "Task",
            fields=[
                "name",
                "subject",
                "project",
                "priority",
                "status",
                "description",
                "exp_end_date",
                "_assign as assigned_to",
                "owner as assigned_by",
                "progress",
                "issue",
            ],
            filters=filters,
            start=start,
            page_length=page_length,
            order_by="modified desc",
        )

        project_map = fetch_project_map(
            {t["project"] for t in tasks if t.get("project")}
        )

        for task in tasks:
            if task.get("exp_end_date"):
                task["exp_end_date"] = task["exp_end_date"].strftime("%d %b %Y")
            task["project_name"] = project_map.get(task.get("project"))
            task["assigned_by"] = fetch_user(task.get("assigned_by"))
            task["comments"] = fetch_comments(task["name"])
            task["num_comments"] = len(task["comments"])

            try:
                emails = json.loads(task.get("assigned_to") or "[]")
            except Exception:
                emails = []

            task["assigned_to"] = fetch_user_details(emails)

        return gen_response(200, "Task list fetched successfully", tasks)

    except frappe.PermissionError:
        return gen_response(403, "Not permitted to read Task")
    except Exception as e:
        return exception_handler(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_task_list_dashboard():
    try:
        filters = [
            ["_assign", "like", f"%{frappe.session.user}%"],
            ["status", "!=", "Completed"],
        ]
        tasks = frappe.get_all(
            "Task",
            fields=[
                "name",
                "subject",
                "project",
                "priority",
                "status",
                "description",
                "exp_end_date",
                "_assign as assigned_to",
                "owner as assigned_by",
                "progress",
            ],
            filters=filters,
            limit=4,
        )

        project_map = fetch_project_map(
            {t["project"] for t in tasks if t.get("project")}
        )

        for task in tasks:
            if task["exp_end_date"]:
                task["exp_end_date"] = task["exp_end_date"].strftime("%d %b %Y")

            task["project_name"] = project_map.get(task.get("project"))
            task["assigned_by"] = fetch_user(task.get("assigned_by"))
            task["comments"] = fetch_comments(task["name"])
            task["num_comments"] = len(task["comments"])

            try:
                emails = json.loads(task.get("assigned_to") or "[]")
            except Exception:
                emails = []

            task["assigned_to"] = fetch_user_details(emails)

        return gen_response(200, "Task list fetched successfully", tasks)

    except Exception as e:
        return exception_handler(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_task_by_id(task_id=None):
    try:
        if not task_id:
            return gen_response(500, "task_id is required", [])

        task = frappe.db.get_value(
            "Task",
            {"name": task_id},
            [
                "name",
                "subject",
                "project",
                "priority",
                "status",
                "description",
                "exp_end_date",
                "expected_time",
                "actual_time",
                "_assign as assigned_to",
                "owner as assigned_by",
                "completed_by",
                "completed_on",
                "progress",
                "issue",
            ],
            as_dict=True,
        )
        if not task:
            return gen_response(404, "No task found", [])

        assigned_to = task.get("assigned_to") or "[]"
        try:
            assigned_users = json.loads(assigned_to)
        except Exception:
            assigned_users = []
        if frappe.session.user not in assigned_users:
            return gen_response(403, "Not authorized to view this task", [])

        task["assigned_by"] = fetch_user(task.get("assigned_by"))
        task["completed_by"] = fetch_user(task.get("completed_by"))
        task["project_name"] = frappe.db.get_value(
            "Project", task.get("project"), "project_name"
        )

        try:
            emails = json.loads(task.get("assigned_to") or "[]")
        except Exception:
            emails = []

        task["assigned_to"] = (
            frappe.get_all(
                "User",
                filters={"email": ["in", emails]},
                fields=["name", "full_name as user", "full_name", "user_image"],
                order_by="creation asc",
            )
            if emails
            else []
        )

        task["comments"] = fetch_comments(task["name"])
        task["num_comments"] = len(task["comments"])

        return gen_response(200, "Task", task)

    except frappe.PermissionError:
        return gen_response(403, "Not permitted to read task")
    except Exception as e:
        return exception_handler(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def create_task(**kwargs):
    try:
        from frappe.desk.form import assign_to

        data = kwargs

        restricted_fields = {"owner", "_assign", "assigned_to", "assign_to"}
        provided_restricted = set(data.keys()) & restricted_fields
        if provided_restricted:
            return gen_response(
                500,
                "These fields are not allowed: {0}".format(
                    ", ".join(sorted(provided_restricted))
                ),
            )

        allowed_fields = {
            "subject",
            "project",
            "type",
            "priority",
            "description",
            "exp_start_date",
            "exp_end_date",
            "expected_time",
            "department",
            "company",
            "color",
            "is_milestone",
        }
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

        filtered_data["owner"] = frappe.session.user

        task_doc = frappe.get_doc(doctype="Task")
        task_doc.update(filtered_data)

        frappe.flags.skip_ess_task_notifications = True
        try:
            task_doc.insert()

            assign_to.add(
                {
                    "assign_to": [frappe.session.user],
                    "doctype": task_doc.doctype,
                    "name": task_doc.name,
                }
            )
        finally:
            frappe.flags.skip_ess_task_notifications = False

        send_task_notifications(
            task_doc=task_doc,
            assigned_user=frappe.session.user,
            creator_user=frappe.session.user,
        )

        return gen_response(
            200, "Task has been created successfully", {"name": task_doc.name}
        )
    except frappe.PermissionError:
        return gen_response(500, "Not permitted for create task")
    except Exception as e:
        return exception_handler(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def update_task(**kwargs):
    try:
        data = kwargs

        task_name = data.get("name")
        if not task_name:
            return gen_response(500, "Task name is required")

        task_doc = frappe.get_doc("Task", task_name)

        # Check whether logged-in employee is assigned to this task
        assigned_to = task_doc.get("_assign") or "[]"

        try:
            assigned_users = json.loads(assigned_to)
        except (TypeError, json.JSONDecodeError):
            return gen_response(500, "Unable to verify task assignment")

        if frappe.session.user not in assigned_users:
            return gen_response(
                403,
                "Not authorized to update this task"
            )

        restricted_fields = {
            "owner",
            "_assign",
            "assigned_to",
            "assign_to",
            "company",
            "department",
            "project",
            "docstatus",
            "status",
            "completed_by",
            "completed_on",
            "actual_time",
            "total_costing_amount",
            "total_expense_claim",
            "total_billing_amount",
            "lft",
            "rgt",
            "creation",
            "modified",
            "modified_by",
        }

        provided_restricted = set(data.keys()) & restricted_fields

        if provided_restricted:
            return gen_response(
                500,
                "These fields are not allowed: {0}".format(
                    ", ".join(sorted(provided_restricted))
                ),
            )

        allowed_fields = {
            "subject",
            "type",
            "priority",
            "description",
            "exp_start_date",
            "exp_end_date",
            "expected_time",
            "color",
            "is_milestone",
        }

        filtered_data = {
            k: v
            for k, v in data.items()
            if k in allowed_fields
        }

        task_doc.update(filtered_data)
        task_doc.save()

        return gen_response(
            200,
            "Task has been updated successfully",
            {"name": task_doc.name}
        )

    except frappe.PermissionError:
        return gen_response(
            500,
            "Not permitted for update task"
        )

    except Exception as e:
        return exception_handler(e)    

@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_task_status_list():
    try:
        task_status = frappe.get_meta("Task").get_field("status").options or ""
        if task_status:
            task_status = task_status.split("\n")
        return gen_response(200, "Status get successfully", task_status)
    except Exception as e:
        return exception_handler(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_project_list():
    try:
        project_list = frappe.get_list("Project", ["name", "project_name"])
        return gen_response(200, "Project List getting Successfully", project_list)
    except frappe.PermissionError:
        return gen_response(500, "Not permitted read project")
    except Exception as e:
        return exception_handler(e)
