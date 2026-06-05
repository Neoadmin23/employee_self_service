import frappe
from frappe import _


@frappe.whitelist()
def get_ess_admin_details():
    """
    Returns whether the current logged-in user is an ESS Admin.
    Used by the mobile app to decide whether to show Admin Panel.
    """
    user = frappe.session.user

    admin_record = frappe.db.get_value(
        "ESS Admin User",
        {"user": user, "is_active": 1},
        ["name", "role", "email", "full_name"],
        as_dict=True
    )

    if not admin_record:
        return {"is_admin": False}

    return {
        "is_admin": True,
        "admin_id": admin_record.name,
        "role": admin_record.role,
        "email": admin_record.email,
        "full_name": admin_record.full_name
    }


@frappe.whitelist()
def get_company_print_setting(company: str) -> dict:
    """
    Get company print setting for salary slip.
    
    Args:
        company: Company name
    
    Returns:
        dict: Print setting with company and salary_slip_print_format, or None if not found
    """
    try:
        setting = frappe.db.get_value(
            "ESS Company Print Settings",
            {"company": company},
            ["company", "salary_slip_print_format"],
            as_dict=True
        )
        
        if setting:
            return {
                "company": setting.company,
                "salary_slip_print_format": setting.salary_slip_print_format
            }
        return None
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def save_company_print_setting(company: str, salary_slip_print_format: str) -> dict:
    """
    Save company print setting for salary slip.
    
    Args:
        company: Company name
        salary_slip_print_format: Print format name
    
    Returns:
        dict: Success response
    """
    try:
        # Check whether record exists
        existing = frappe.db.exists(
            "ESS Company Print Settings",
            {"company": company}
        )
        
        if existing:
            # Update existing record
            doc = frappe.get_doc("ESS Company Print Settings", company)
            doc.salary_slip_print_format = salary_slip_print_format
            doc.is_active = 1
            doc.save(ignore_permissions=True)
        else:
            # Create new document
            frappe.get_doc(
                {
                    "doctype": "ESS Company Print Settings",
                    "company": company,
                    "salary_slip_print_format": salary_slip_print_format,
                    "is_active": 1
                }
            ).insert(ignore_permissions=True)
        
        frappe.db.commit()
        return {
            "success": True,
            "message": "Saved successfully"
        }
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_salary_slip_print_format(salary_slip: str, language: str = "en") -> dict:
    """
    Get the print format for a Salary Slip based on company settings.
    
    Args:
        salary_slip: Salary Slip document name
        language: Language code (default: "en")
    
    Returns:
        dict: Print format and language
    """
    try:
        frappe.logger().info(f"Received salary slip: {salary_slip}")
        
        # Fetch Salary Slip document
        if not frappe.db.exists("Salary Slip", salary_slip):
            frappe.throw("Salary Slip not found")
        
        salary_slip_doc = frappe.get_doc("Salary Slip", salary_slip)
        company = salary_slip_doc.company
        
        frappe.logger().info(f"Detected company: {company}")
        
        # Look in ESS Company Print Settings
        if not company:
            return {
                "print_format": None,
                "language": language
            }
        
        setting = frappe.db.get_value(
            "ESS Company Print Settings",
            {"company": company},
            "salary_slip_print_format",
            as_dict=True
        )
        
        if setting and setting.salary_slip_print_format:
            frappe.logger().info(f"Selected print format: {setting.salary_slip_print_format}")
            return {
                "print_format": setting.salary_slip_print_format,
                "language": language
            }
        
        return {
            "print_format": None,
            "language": language
        }
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_admin_dashboard_stats():
    try:
        total_employees = frappe.db.count("Employee")
        total_companies = frappe.db.count("Company")
        total_admin_users = frappe.db.count("ESS Admin User", {"is_active": 1})

        pending_leaves = frappe.db.count("Leave Application", {"status": "Open"})
        pending_attendance = frappe.db.count(
            "Employee Checkin", {"attendance": ["is", "not set"]}
        )
        pending_travel = frappe.db.count("Travel Request", {"status": "Open"})
        pending_tasks = frappe.db.count("Task", {"status": ["!=", "Completed"]})

        return {
            "total_employees": total_employees,
            "total_companies": total_companies,
            "total_admin_users": total_admin_users,
            "pending_leaves": pending_leaves,
            "pending_attendance": pending_attendance,
            "pending_travel": pending_travel,
            "pending_tasks": pending_tasks,
        }
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_pending_leave_approvals():
    try:
        leaves = frappe.get_all(
            "Leave Application",
            filters={"status": "Open"},
            fields=[
                "name",
                "employee",
                "employee_name",
                "leave_type",
                "DATE_FORMAT(from_date, '%d-%m-%Y') as from_date",
                "DATE_FORMAT(to_date, '%d-%m-%Y') as to_date",
                "total_leave_days",
                "status",
            ],
        )
        return leaves
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_pending_travel_approvals():
    try:
        travels = frappe.get_all(
            "Travel Request",
            filters={"status": "Open"},
            fields=[
                "name",
                "employee",
                "purpose_of_travel",
                "DATE_FORMAT(from_date, '%d-%m-%Y') as from_date",
                "DATE_FORMAT(to_date, '%d-%m-%Y') as to_date",
                "status",
            ],
        )
        return travels
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_pending_task_monitoring():
    try:
        tasks = frappe.get_all(
            "Task",
            filters={"status": ["!=", "Completed"]},
            fields=[
                "name",
                "subject",
                "priority",
                "status",
                "exp_end_date",
            ],
        )
        for task in tasks:
            if task.get("exp_end_date"):
                task["exp_end_date"] = task["exp_end_date"].strftime("%d-%m-%Y")
        return tasks
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


def _apply_approval_action(doctype, docname, action, remarks=None):
    """
    Apply approval action to a document.
    If workflow exists, use workflow action.
    Otherwise, update status field directly.
    """
    doc = frappe.get_doc(doctype, docname)

    # Check for active workflow
    workflow = frappe.get_all(
        "Workflow",
        filters={"document_type": doctype, "is_active": 1},
        fields=["name", "workflow_state_field"],
        limit=1,
    )

    if workflow:
        # Workflow exists - try to use workflow action
        workflow_state_field = workflow[0].workflow_state_field or "workflow_state"

        # Map action to workflow state
        state_map = {
            "approve": "Approved",
            "reject": "Rejected",
        }
        new_state = state_map.get(action.lower(), action)

        # Update workflow state field if it exists
        if hasattr(doc, workflow_state_field):
            setattr(doc, workflow_state_field, new_state)

        # Also update status if it's a different field
        if workflow_state_field != "status" and hasattr(doc, "status"):
            doc.status = new_state

        if remarks and hasattr(doc, "remarks"):
            doc.remarks = remarks

        doc.save(ignore_permissions=True)
    else:
        # No workflow - update status directly
        status_map = {
            "approve": "Approved",
            "reject": "Rejected",
        }
        new_status = status_map.get(action.lower(), action)
        frappe.db.set_value(doctype, docname, "status", new_status)

        if remarks:
            frappe.db.set_value(doctype, docname, "remarks", remarks)


@frappe.whitelist()
def get_leave_approval_details(name):
    try:
        if not frappe.db.exists("Leave Application", name):
            frappe.throw("Leave Application not found")

        leave = frappe.get_doc(
            "Leave Application",
            name,
            [
                "name",
                "employee",
                "employee_name",
                "leave_type",
                "from_date",
                "to_date",
                "total_leave_days",
                "description",
                "status",
            ],
        )

        result = {
            "name": leave.name,
            "employee": leave.employee,
            "employee_name": leave.employee_name,
            "leave_type": leave.leave_type,
            "from_date": leave.from_date.strftime("%d-%m-%Y") if leave.from_date else None,
            "to_date": leave.to_date.strftime("%d-%m-%Y") if leave.to_date else None,
            "total_leave_days": leave.total_leave_days,
            "description": leave.description,
            "status": leave.status,
        }
        return result
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def approve_leave_request(name, remarks=None):
    try:
        if not frappe.db.exists("Leave Application", name):
            frappe.throw("Leave Application not found")

        _apply_approval_action("Leave Application", name, "approve", remarks)
        return {"success": True, "message": "Leave request approved successfully"}
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def reject_leave_request(name, remarks=None):
    try:
        if not frappe.db.exists("Leave Application", name):
            frappe.throw("Leave Application not found")

        _apply_approval_action("Leave Application", name, "reject", remarks)
        return {"success": True, "message": "Leave request rejected successfully"}
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_travel_approval_details(name):
    try:
        if not frappe.db.exists("Travel Request", name):
            frappe.throw("Travel Request not found")

        travel = frappe.get_doc(
            "Travel Request",
            name,
            [
                "employee",
                "purpose_of_travel",
                "from_date",
                "to_date",
                "description",
                "status",
            ],
        )

        result = {
            "name": travel.name,
            "employee": travel.employee,
            "purpose_of_travel": travel.purpose_of_travel,
            "from_date": travel.from_date.strftime("%d-%m-%Y") if travel.from_date else None,
            "to_date": travel.to_date.strftime("%d-%m-%Y") if travel.to_date else None,
            "description": travel.description,
            "status": travel.status,
        }
        return result
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def approve_travel_request(name, remarks=None):
    try:
        if not frappe.db.exists("Travel Request", name):
            frappe.throw("Travel Request not found")

        _apply_approval_action("Travel Request", name, "approve", remarks)
        return {"success": True, "message": "Travel request approved successfully"}
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def reject_travel_request(name, remarks=None):
    try:
        if not frappe.db.exists("Travel Request", name):
            frappe.throw("Travel Request not found")

        _apply_approval_action("Travel Request", name, "reject", remarks)
        return {"success": True, "message": "Travel request rejected successfully"}
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


def _apply_attendance_approval_action(docname, action, remarks=None):
    doc = frappe.get_doc("Attendance Request", docname)

    workflow = frappe.get_all(
        "Workflow",
        filters={"document_type": "Attendance Request", "is_active": 1},
        fields=["name", "workflow_state_field"],
        limit=1,
    )

    if workflow:
        workflow_state_field = workflow[0].workflow_state_field or "workflow_state"
        state_map = {"approve": "Approved", "reject": "Rejected"}
        new_state = state_map.get(action.lower(), action)

        if hasattr(doc, workflow_state_field):
            setattr(doc, workflow_state_field, new_state)

        if remarks and hasattr(doc, "remarks"):
            doc.remarks = remarks

        doc.save(ignore_permissions=True)
    else:
        if remarks and hasattr(doc, "remarks"):
            doc.remarks = remarks

        if action.lower() == "approve":
            doc.submit()
        elif action.lower() == "reject":
            doc.cancel()


@frappe.whitelist()
def get_pending_attendance_approvals():
    try:
        attendance_requests = frappe.get_all(
            "Attendance Request",
            filters={"docstatus": ["!=", 2]},
            fields=[
                "name",
                "employee",
                "employee_name",
                "department",
                "company",
                "DATE_FORMAT(from_date, '%d-%m-%Y') as from_date",
                "DATE_FORMAT(to_date, '%d-%m-%Y') as to_date",
                "reason",
                "explanation",
                "docstatus",
            ],
        )
        return attendance_requests
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_attendance_approval_details(name):
    try:
        if not frappe.db.exists("Attendance Request", name):
            frappe.throw("Attendance Request not found")

        request = frappe.get_doc(
            "Attendance Request",
            name,
            [
                "name",
                "employee",
                "employee_name",
                "department",
                "company",
                "from_date",
                "to_date",
                "half_day",
                "half_day_date",
                "reason",
                "explanation",
                "shift",
                "include_holidays",
                "docstatus",
            ],
        )

        result = {
            "name": request.name,
            "employee": request.employee,
            "employee_name": request.employee_name,
            "department": request.department,
            "company": request.company,
            "from_date": request.from_date.strftime("%d-%m-%Y") if request.from_date else None,
            "to_date": request.to_date.strftime("%d-%m-%Y") if request.to_date else None,
            "half_day": request.half_day,
            "half_day_date": request.half_day_date.strftime("%d-%m-%Y") if request.half_day_date else None,
            "reason": request.reason,
            "explanation": request.explanation,
            "shift": request.shift,
            "include_holidays": request.include_holidays,
            "docstatus": request.docstatus,
        }
        return result
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def approve_attendance_request(name):
    try:
        if not frappe.db.exists("Attendance Request", name):
            frappe.throw("Attendance Request not found")

        _apply_attendance_approval_action(name, "approve")
        return {"success": True, "message": "Attendance request approved successfully"}
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def reject_attendance_request(name, remarks=None):
    try:
        if not frappe.db.exists("Attendance Request", name):
            frappe.throw("Attendance Request not found")

        _apply_attendance_approval_action(name, "reject", remarks)
        return {"success": True, "message": "Attendance request rejected successfully"}
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_employee_list(search_text=None):
    try:
        filters = []
        if search_text:
            filters = [
                ["Employee", "employee_name", "like", f"%{search_text}%"],
                ["Employee", "name", "like", f"%{search_text}%"],
                ["Employee", "department", "like", f"%{search_text}%"],
            ]

        employees = frappe.get_all(
            "Employee",
            filters=filters,
            fields=[
                "name",
                "employee_name",
                "designation",
                "department",
                "company",
                "status",
                "user_id",
                "image",
            ],
        )
        return employees
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_employee_details(employee):
    try:
        if not frappe.db.exists("Employee", employee):
            frappe.throw("Employee not found")

        emp = frappe.get_doc(
            "Employee",
            employee,
            [
                "name",
                "employee_name",
                "designation",
                "department",
                "company",
                "date_of_joining",
                "status",
                "user_id",
                "personal_email",
                "company_email",
                "mobile_no",
                "image",
            ],
        )

        result = {
            "employee": emp.name,
            "employee_name": emp.employee_name,
            "designation": emp.designation,
            "department": emp.department,
            "company": emp.company,
            "date_of_joining": emp.date_of_joining.strftime("%d-%m-%Y") if emp.date_of_joining else None,
            "status": emp.status,
            "user_id": emp.user_id,
            "personal_email": emp.personal_email,
            "company_email": emp.company_email,
            "mobile_no": emp.mobile_no,
            "image": emp.image,
        }
        return result
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_employee_leave_history(employee):
    try:
        if not frappe.db.exists("Employee", employee):
            frappe.throw("Employee not found")

        leaves = frappe.get_all(
            "Leave Application",
            filters={"employee": employee},
            fields=[
                "name",
                "leave_type",
                "DATE_FORMAT(from_date, '%d-%m-%Y') as from_date",
                "DATE_FORMAT(to_date, '%d-%m-%Y') as to_date",
                "total_leave_days",
                "status",
            ],
            order_by="creation desc",
        )
        return leaves
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_employee_attendance_history(employee):
    try:
        if not frappe.db.exists("Employee", employee):
            frappe.throw("Employee not found")

        attendance = frappe.get_all(
            "Attendance",
            filters={"employee": employee},
            fields=[
                "DATE_FORMAT(attendance_date, '%d-%m-%Y') as attendance_date",
                "status",
                "in_time",
                "out_time",
                "working_hours",
            ],
            order_by="attendance_date desc",
            limit=30,
        )
        return attendance
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
def get_employee_task_history(employee):
    try:
        if not frappe.db.exists("Employee", employee):
            frappe.throw("Employee not found")

        tasks = frappe.get_all(
            "Task",
            filters={"_assign": ["like", f"%{employee}%"]},
            fields=[
                "name",
                "subject",
                "priority",
                "status",
                "exp_end_date",
            ],
        )
        for task in tasks:
            if task.get("exp_end_date"):
                task["exp_end_date"] = task["exp_end_date"].strftime("%d-%m-%Y")
        return tasks
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))