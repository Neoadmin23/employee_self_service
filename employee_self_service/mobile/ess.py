import calendar
import json
import os

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.auth import LoginManager
from frappe.utils import (
    cint,
    cstr,
    date_diff,
    flt,
    fmt_money,
    get_date_str,
    get_first_day,
    get_last_day,
    getdate,
    now_datetime,
    nowdate,
    pretty_date,
    today,
)

from employee_self_service.employee_self_service.doctype.push_notification.push_notification import (
    create_push_notification,
)
from employee_self_service.mobile.api_utils import (
    ess_validate,
    exception_handel,
    gen_response,
    generate_key,
    get_employee_by_user,
    get_ess_settings,
    get_global_defaults,
    validate_employee_data,
)
from employee_self_service.utils import get_employees_having_an_event_today


@frappe.whitelist(allow_guest=True)
def login(usr, pwd):
    try:
        login_manager = LoginManager()
        login_manager.authenticate(usr, pwd)

        user = login_manager.user

        # Check if user has ESS Admin Manager role
        is_admin = frappe.db.exists(
            "Has Role",
            {
                "parent": user,
                "role": "ESS Admin Manager"
            }
        )

        # Existing employee validation
        # Skip only for admin users
        if not is_admin:
            validate_employee(user)

        login_manager.post_login()

        if frappe.response["message"] == "Logged In":
            # Existing functionality (unchanged)
            frappe.response["user"] = user
            frappe.response["key_details"] = generate_key(user)

            # Existing employee functionality
            if not is_admin:
                emp_data = get_employee_by_user(user)
                frappe.response["employee_id"] = emp_data.get("name")

            # Additional admin info only
            frappe.response["user_type"] = (
                "admin" if is_admin else "employee"
            )

        gen_response(200, frappe.response["message"])

    except frappe.AuthenticationError:
        gen_response(500, frappe.response["message"])

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def forgot_password(email=None):
    try:
        if not email:
            return gen_response(500, "Email is required")

        user = frappe.db.get_value(
            "User",
            {"email": email},
            ["name", "enabled"],
            as_dict=True,
        )

        if not user:
            return gen_response(500, "User not found with this email")

        if not user.enabled:
            return gen_response(500, "User is disabled")

        from frappe.core.doctype.user.user import reset_password

        reset_password(user.name)

        return gen_response(200, "Password reset link sent successfully")
    except Exception as e:
        return exception_handel(e)


def validate_employee(user):
    if not frappe.db.exists("Employee", dict(user_id=user)):
        frappe.response["message"] = "Please link Employee with this user"
        raise frappe.AuthenticationError(
            frappe.response["message"]
        )

@frappe.whitelist()
@ess_validate(methods=["POST"])
def make_leave_application(*args, **kwargs):
    try:
        from hrms.hr.doctype.leave_application.leave_application import (
            get_leave_approver,
        )

        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)
        leave_application_doc = frappe.get_doc(
            doctype="Leave Application",
            employee=emp_data.get("name"),
            company=emp_data.company,
            leave_approver=get_leave_approver(emp_data.name),
        )
        leave_application_doc.update(kwargs)
        leave_application_doc.insert()
        leave_application_doc.submit()

        messages = _get_server_messages()

        gen_response(
            200,
            "Leave Application Successfully Added",
            leave_application_doc
        )

        if messages:
            frappe.local.response["messages"] = messages

    except Exception as e:
        return exception_handel(e)


def _get_server_messages():
    raw_messages = frappe.local.message_log or []
    result = []
    for msg in raw_messages:
        if not isinstance(msg, dict):
            continue
        indicator = msg.get("indicator") or "blue"
        result.append({
            "type": _map_indicator_to_type(indicator),
            "message": msg.get("message", ""),
            "title": msg.get("title"),
        })
    frappe.clear_messages()
    return result


def _map_indicator_to_type(indicator):
    mapping = {
        "orange": "warning",
        "red": "error",
        "green": "success",
        "blue": "info",
        "yellow": "warning",
    }
    return mapping.get(indicator, "info")


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_leave_type(from_date=None, to_date=None):
    try:
        from hrms.hr.doctype.leave_application.leave_application import (
            get_leave_balance_on,
        )

        emp_data = get_employee_by_user(frappe.session.user)
        leave_types = frappe.get_all(
            "Leave Type", filters={}, fields=["name", "'0' as balance"]
        )
        for leave_type in leave_types:
            leave_type["balance"] = get_leave_balance_on(
                emp_data.get("name"),
                leave_type.get("name"),
                from_date,
                consider_all_leaves_in_the_allocation_period=True,
            )
        return gen_response(200, "Leave Type Get Successfully", leave_types)
    except Exception as e:
        return exception_handel(e)


"""Get Leave Application which is already applied. Get Leave Balance Report"""


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_leave_application_list():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        validate_employee_data(emp_data)
        leave_application_fields = [
            "name",
            "leave_type",
            "DATE_FORMAT(from_date, '%d-%m-%Y') as from_date",
            "DATE_FORMAT(to_date, '%d-%m-%Y') as to_date",
            "total_leave_days",
            "description",
            "status",
            "DATE_FORMAT(posting_date, '%d-%m-%Y') as posting_date",
        ]
        upcoming_leaves = frappe.get_all(
            "Leave Application",
            filters={"from_date": [">", today()], "employee": emp_data.get("name")},
            fields=leave_application_fields,
        )

        taken_leaves = frappe.get_all(
            "Leave Application",
            fields=leave_application_fields,
            filters={"from_date": ["<=", today()], "employee": emp_data.get("name")},
        )
        fiscal_year = get_fiscal_year(nowdate())[0]
        if not fiscal_year:
            return gen_response(500, "Fiscal year not set")
        res = get_leave_balance_report(
            emp_data.get("name"), emp_data.get("company"), fiscal_year
        )
        leave_applications = {
            "upcoming": upcoming_leaves,
            "taken": taken_leaves,
            "balance": res["result"],
        }
        return gen_response(200, "leave data getting successfully", leave_applications)
    except Exception as e:
        return exception_handel(e)


def get_leave_balance_report(employee, company, fiscal_year):
    fiscal_year = get_fiscal_year(fiscal_year=fiscal_year, as_dict=True)
    year_start_date = get_date_str(fiscal_year.get("year_start_date"))
    get_date_str(fiscal_year.get("year_end_date"))
    filters_leave_balance = {
        "from_date": year_start_date,
        "to_date": today(),
        "company": company,
        "employee": employee,
    }
    from frappe.desk.query_report import run

    return run("Employee Leave Balance", filters=filters_leave_balance)


@frappe.whitelist()
def get_expense_type():
    try:
        expense_types = frappe.get_all(
            "Expense Claim Type", filters={}, fields=["name"]
        )
        return gen_response(200, "Expense Type Get Successfully", expense_types)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def book_expense(*args, **kwargs):
    try:
        emp_data = get_employee_by_user(
            frappe.session.user, fields=["name", "company", "expense_approver"]
        )
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)
        data = kwargs
        payable_account = get_payable_account(emp_data.get("company"))
        expense_doc = frappe.get_doc(
            doctype="Expense Claim",
            employee=emp_data.name,
            expense_approver=emp_data.expense_approver,
            expenses=[
                {
                    "expense_date": data.get("expense_date"),
                    "expense_type": data.get("expense_type"),
                    "description": data.get("description"),
                    "amount": data.get("amount"),
                }
            ],
            posting_date=today(),
            company=emp_data.get("company"),
            payable_account=payable_account,
        ).insert()
        # expense_doc.submit()
        if data.get("attachments") is not None:
            for file in data.get("attachments"):
                frappe.db.set_value(
                    "File", file.get("name"), "attached_to_name", expense_doc.name
                )
        return gen_response(200, "Expense applied Successfully", expense_doc)
    except Exception as e:
        return exception_handel(e)


def get_payable_account(company):
    ess_settings = get_ess_settings()
    default_payable_account = ess_settings.get("default_payable_account")
    if not default_payable_account:
        default_payable_account = frappe.db.get_value(
            "Company", company, "default_payable_account"
        )
        if not default_payable_account:
            return gen_response(
                500,
                "Set Default Payable Account Either In ESS Settings or Company Settings",
            )
        else:
            return default_payable_account
    return default_payable_account


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_expense_list():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)
        expense_list = frappe.get_all(
            "Expense Claim",
            filters={"employee": emp_data.get("name")},
            fields=["*"],
        )
        expense_data = {}
        for expense in expense_list:
            (
                expense["expense_type"],
                expense["expense_description"],
                expense["expense_date"],
            ) = frappe.get_value(
                "Expense Claim Detail",
                {"parent": expense.name},
                ["expense_type", "description", "expense_date"],
            )
            expense["expense_date"] = expense["expense_date"].strftime("%d-%m-%Y")
            expense["posting_date"] = expense["posting_date"].strftime("%d-%m-%Y")
            expense["attachments"] = frappe.get_all(
                "File",
                filters={
                    "attached_to_doctype": "Expense Claim",
                    "attached_to_name": expense.name,
                    "is_folder": 0,
                },
                fields=["file_url"],
            )

            month_year = get_month_year_details(expense)
            if month_year not in list(expense_data.keys())[::-1]:
                expense_data[month_year] = [expense]
            else:
                expense_data[month_year].append(expense)
        return gen_response(200, "Expense Date Get Successfully", expense_data)
    except Exception as e:
        return exception_handel(e)


def get_month_year_details(expense):
    date = getdate(expense.get("posting_date"))
    month = date.strftime("%B")
    year = date.year
    return f"{month} {year}"


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_salary_sllip():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)
        salary_slip_list = frappe.get_all(
            "Salary Slip",
            filters={"employee": emp_data.get("name")},
            fields=["posting_date", "name"],
        )
        ss_data = []
        for ss in salary_slip_list:
            ss_details = {}
            month_year = get_month_year_details(ss)
            ss_details["month_year"] = month_year
            ss_details["salary_slip_id"] = ss.name
            ss_details["details"] = get_salary_slip_details(ss.name)
            ss_data.append(ss_details)
        return gen_response(200, "Salary Slip Details Get Successfully", ss_data)
    except Exception as e:
        return exception_handel(e)


def get_salary_slip_details(ss_id):
    return frappe.get_doc("Salary Slip", ss_id)


@frappe.whitelist()
@ess_validate(methods=["GET", "POST"])
def download_salary_slip(ss_id):
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        res = frappe.get_doc("Salary Slip", ss_id)
        if not emp_data.get("name") == res.get("employee"):
            return gen_response(
                500, "Does not have persmission to read this salary slip"
            )
        default_print_format = frappe.db.get_single_value(
            "Employee Self Service Settings",
            "default_print_format",
        )
        if not default_print_format:
            default_print_format = (
                frappe.db.get_value(
                    "Property Setter",
                    dict(property="default_print_format", doc_type=res.doctype),
                    "value",
                )
                or "Standard"
            )
        language = frappe.get_system_settings("language")
        # return  frappe.utils.get_url()
        f"{frappe.utils.get_url()}/{res.doctype}/{res.name}?format={default_print_format or 'Standard'}&_lang={language}&key={res.get_signature()}"
        # return url
        download_pdf(res.doctype, res.name, default_print_format, res)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
def download_pdf(doctype, name, format=None, doc=None, no_letterhead=0):
    from frappe.utils.pdf import get_pdf

    html = frappe.get_print(doctype, name, format, doc=doc, no_letterhead=no_letterhead)
    frappe.local.response.filename = "{name}.pdf".format(
        name=name.replace(" ", "-").replace("/", "-")
    )
    frappe.local.response.filecontent = get_pdf(html)
    frappe.local.response.type = "download"


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_dashboard():
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["name", "company"])
        notice_board = get_notice_board(emp_data.get("name"))
        # attendance_details = get_attendance_details(emp_data)
        log_details = get_last_log_details(emp_data.get("name"))
        settings = get_ess_settings()
        dashboard_data = {
            "notice_board": notice_board,
            "leave_balance": [],
            "latest_leave": {},
            "latest_expense": {},
            "latest_salary_slip": {},
            "stop_location_validate": settings.get("location_validate"),
            "last_log_type": log_details.get("log_type"),
            "version": settings.get("version") or "1.0",
            "update_version_forcefully": settings.get("update_version_forcefully") or 1,
            "company": emp_data.get("company") or "Employee Dashboard",
            "last_log_time": log_details.get("time").strftime("%I:%M%p")
            if log_details.get("time")
            else "",
        }
        dashboard_data["employee_image"] = frappe.get_cached_value(
            "Employee", emp_data.get("name"), "image"
        )
        get_latest_expense(dashboard_data, emp_data.get("name"))
        get_latest_ss(dashboard_data, emp_data.get("name"))
        get_last_log_type(dashboard_data, emp_data.get("name"))
        return gen_response(200, "Dashboard data get successfully", dashboard_data)

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
def get_leave_balance_dashboard():
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["name", "company"])
        fiscal_year = get_fiscal_year(nowdate())[0]
        dashboard_data = {"leave_balance": []}
        if fiscal_year:
            res = get_leave_balance_report(
                emp_data.get("name"), emp_data.get("company"), fiscal_year
            )
            dashboard_data["leave_balance"] = res["result"]
        return gen_response(200, "Leave Balance data get successfully", dashboard_data)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
def get_attendance_details_dashboard():
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["name", "company"])
        attendance_details = get_attendance_details(emp_data)
        return gen_response(
            200, "Leave Balance data get successfully", attendance_details
        )
    except Exception as e:
        return exception_handel(e)


def get_last_log_details(employee):
    log_details = frappe.db.sql(
        """select log_type,time from `tabEmployee Checkin` where employee=%s and DATE(time)=%s order by time desc""",
        (employee, today()),
        as_dict=1,
    )

    if log_details:
        return log_details[0]
    else:
        return {"log_type": "OUT", "time": None}


def get_notice_board(employee=None):
    filters = [
        ["Notice Board Employee", "employee", "=", employee],
        ["Notice Board", "apply_for", "=", "Specific Employees"],
        ["Notice Board", "from_date", "<=", today()],
        ["Notice Board", "to_date", ">=", today()],
    ]
    notice_board_employee = frappe.get_all(
        "Notice Board",
        filters=filters,
        fields=["notice_title as title", "message"],
    )
    common_filters = [
        ["Notice Board", "apply_for", "=", "All Employee"],
        ["Notice Board", "from_date", "<=", today()],
        ["Notice Board", "to_date", ">=", today()],
    ]
    notice_board_common = frappe.get_all(
        "Notice Board",
        filters=common_filters,
        fields=["notice_title as title", "message"],
    )
    notice_board_employee.extend(notice_board_common)
    return notice_board_employee


def get_attendance_details(emp_data):
    last_date = get_last_day(today())
    first_date = get_first_day(today())
    total_days = date_diff(last_date, first_date)
    till_date_days = date_diff(today(), first_date)
    days_off = 0
    absent = 0
    total_present = 0
    attendance_report = run_attendance_report(
        emp_data.get("name"), emp_data.get("company")
    )
    if attendance_report:
        days_off = flt(attendance_report.get("total_leaves")) + flt(
            attendance_report.get("total_holidays")
        )
        absent = till_date_days - (
            flt(days_off) + flt(attendance_report.get("total_present"))
        )
        total_present = attendance_report.get("total_present")
    attendance_details = {
        "month_title": f"{frappe.utils.getdate().strftime('%B')} Details",
        "data": [
            {
                "type": "Total Days",
                "data": [
                    till_date_days,
                    total_days,
                ],
            },
            {
                "type": "Presents",
                "data": [
                    total_present,
                    till_date_days,
                ],
            },
            {
                "type": "Absents",
                "data": [
                    absent,
                    till_date_days,
                ],
            },
            {
                "type": "Days off",
                "data": [
                    days_off,
                    till_date_days,
                ],
            },
        ],
    }
    return attendance_details


@frappe.whitelist()
def run_attendance_report(employee, company):
    filters = {
        "month": cstr(frappe.utils.getdate().month),
        "year": cstr(frappe.utils.getdate().year),
        "company": company,
        "employee": employee,
        "summarized_view": 1,
    }
    from frappe.desk.query_report import run

    attendance_report = run("Monthly Attendance Sheet", filters=filters)
    if attendance_report.get("result"):
        return attendance_report.get("result")[0]


def get_latest_leave(dashboard_data, employee):
    leave_applications = frappe.get_all(
        "Leave Application",
        filters={"employee": employee},
        fields=[
            "status",
            "DATE_FORMAT(from_date, '%d-%m-%Y') AS from_date",
            "DATE_FORMAT(to_date, '%d-%m-%Y') AS to_date",
            "name",
            "leave_type",
            "description",
        ],
        order_by="modified desc",
    )
    if len(leave_applications) >= 1:
        dashboard_data["latest_leave"] = leave_applications[0]


def get_latest_expense(dashboard_data, employee):
    expense_list = frappe.get_all(
        "Expense Claim",
        filters={"employee": employee},
        fields=["name"],
        order_by="modified desc",
    )
    if len(expense_list) >= 1:
        expense_doc = frappe.get_doc("Expense Claim", expense_list[0].name)
        dashboard_data["latest_expense"] = dict(
            status=expense_doc.approval_status,
            date=expense_doc.expenses[0].expense_date.strftime("%d-%m-%Y"),
            expense_type=expense_doc.expenses[0].expense_type,
            amount=expense_doc.expenses[0].amount,
            name=expense_doc.name,
        )


def get_latest_ss(dashboard_data, employee):
    salary_slips = frappe.get_all(
        "Salary Slip",
        filters={"employee": employee},
        fields=["*"],
        order_by="modified desc",
    )
    if len(salary_slips) >= 1:
        month_year = get_month_year_details(salary_slips[0])
        dashboard_data["latest_salary_slip"] = dict(
            name=salary_slips[0].name,
            month_year=month_year,
            posting_date=salary_slips[0].posting_date.strftime("%d-%m-%Y"),
            amount=salary_slips[0].gross_pay,
            total_working_days=salary_slips[0].total_working_days,
        )


def get_distance_between_coordinates(lat1, long1, lat2, long2):
	"""Calculate distance between two coordinates using Haversine formula (returns meters)."""
	from math import asin, cos, pi, sqrt

	r = 6371  # Earth radius in km
	p = pi / 180

	a = 0.5 - cos((lat2 - lat1) * p) / 2 + cos(lat1 * p) * cos(lat2 * p) * (1 - cos((long2 - long1) * p)) / 2
	return 2 * r * asin(sqrt(a)) * 1000


def get_active_shift_assignment(employee, checkin_date):
	"""Get active shift assignment for the given employee and date."""
	shift_assignments = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee,
			"status": "Active",
			"docstatus": 1,
			"start_date": ["<=", checkin_date],
		},
		or_filters=[
			["end_date", ">=", checkin_date],
			["end_date", "is", "not set"],
		],
		fields=["name", "shift_type", "shift_location", "start_date", "end_date"],
	)

	# Filter to find the one that actually covers today (end_date check)
	for sa in shift_assignments:
		if not sa.end_date or sa.end_date >= checkin_date:
			return sa

	return None


@frappe.whitelist()
@ess_validate(methods=["POST"])
def create_employee_log(log_type, latitude=None, longitude=None, biometric_verified=0):
	try:
		# Step 1: Get Employee record from current logged-in user
		emp_data = get_employee_by_user(
			frappe.session.user, fields=["name", "employee_name"]
		)

		if not emp_data:
			return gen_response(500, "Your employee profile could not be found. Please contact HR or system administrator.")

		# Step 1a: Check if employee is on approved leave
		leave_today = frappe.get_all(
			"Leave Application",
			filters={
				"employee": emp_data.get("name"),
				"status": "Approved",
				"docstatus": 1,
				"from_date": ["<=", today()],
				"to_date": [">=", today()],
			},
			fields=["name"],
		)
		if leave_today:
			return gen_response(500, "You are currently on approved leave and cannot check in today. If this is incorrect, please contact HR.")

		# Step 1b: Biometric validation
		if not cint(biometric_verified):
			return gen_response(500, "Biometric verification is required before check-in. Please complete fingerprint or face verification and try again.")

		# Step 2: Validate active Shift Assignment for today
		checkin_date = getdate(now_datetime())
		shift_assignment = get_active_shift_assignment(emp_data.get("name"), checkin_date)

		if not shift_assignment:
			return gen_response(500, "No shift has been assigned to you for today. Please contact HR.")

		# Step 3: Get Shift Location from Shift Assignment
		shift_type = shift_assignment.shift_type
		shift_location = shift_assignment.shift_location

		# Step 4: Fetch Shift Location document
		if not shift_location:
			return gen_response(500, "Your assigned shift does not have a work location configured. Please contact HR.")
		
		try:
			shift_location_doc = frappe.get_doc("Shift Location", shift_location)
		except Exception:
			return gen_response(500, "The assigned work location could not be found. Please contact your HR.")

		# Step 5: Read latitude, longitude, checkin_radius
		location_latitude = shift_location_doc.latitude
		location_longitude = shift_location_doc.longitude
		checkin_radius = shift_location_doc.checkin_radius

		# Validate Shift Location has required fields
		if not location_latitude or not location_longitude or not checkin_radius:
			return gen_response(500, "The work location is not configured correctly for attendance tracking. Please contact HR.")

		try:
			location_latitude = float(location_latitude)
			location_longitude = float(location_longitude)
			checkin_radius = float(checkin_radius)
		except (TypeError, ValueError):
			return gen_response(500, "The work location coordinates or radius are not in a valid format. Please contact HR.")

		# Step 6: Calculate distance between employee coordinates and assigned Shift Location
		if latitude and longitude:
			try:
				lat1 = float(latitude)
				lon1 = float(longitude)
				lat2 = float(location_latitude)
				lon2 = float(location_longitude)
			except Exception:
				return gen_response(500, "Invalid GPS coordinates format.")

			distance = get_distance_between_coordinates(lat1, lon1, lat2, lon2)

			frappe.log_error(
				message=f"ESS Checkin - Calculated distance: {distance} meters, allowed radius: {checkin_radius} meters",
				title="ESS Checkin Debug - Distance"
			)

			# Step 7: Validate distance
			distance_km = round(distance / 1000, 1)
			if distance > checkin_radius:
				return gen_response(
					403,
					"Attendance Restricted",
					{
						"code": "LOCATION_RESTRICTED",
						"title": "Attendance Restricted",
						"message": f"You are currently {distance_km} km away from your assigned work location. Attendance can only be marked within the approved check-in area for this shift.",
						"distance_meters": distance,
						"distance_km": distance_km,
						"allow_request": True,
					},
				)
		else:
			return gen_response(500, "Location access is required for attendance. Please enable GPS and try again.")

		# Step 8: Create Employee Checkin with forced values
		employee_checkin = frappe.get_doc(
			doctype="Employee Checkin",
			employee=emp_data.get("name"),
			employee_name=emp_data.get("employee_name"),
			log_type=log_type,
			time=now_datetime(),
			shift=shift_type,
			custom_checkin_location=shift_location,
			latitude=lat1,
			longitude=lon1,
			device_id="mobile",
		)
		employee_checkin.insert(ignore_permissions=True)

		return gen_response(200, "Check-in recorded successfully.", employee_checkin.as_dict())
	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(),
			title="ESS Checkin Debug - Error"
		)
		return gen_response(500, "Unable to process your attendance request at this time. Please try again later or contact support if the issue persists.")


def update_shift_last_sync(emp_data):
    if emp_data.get("default_shift"):
        frappe.db.set_value(
            "Shift Type",
            emp_data.get("default_shift"),
            "last_sync_of_checkin",
            now_datetime(),
        )


def get_last_log_type(dashboard_data, employee):
    logs = frappe.get_all(
        "Employee Checkin",
        filters={"employee": employee},
        fields=["log_type"],
        order_by="time desc",
    )

    if len(logs) >= 1:
        dashboard_data["last_log_type"] = logs[0].log_type


def daily_notice_board_event():
    create_employee_birthday_board("birthday")
    create_employee_birthday_board("work_anniversary")


def create_employee_birthday_board(event_type):
    event_type_map = {"work_anniversary": "Work Anniversary", "birthday": "Birthday"}
    title, message = frappe.db.get_value(
        "Notice Board Template",
        {"notice_board_template_type": event_type_map.get(event_type)},
        ["board_title", "message"],
    )
    if title and message:
        emp_today_birthdays = get_employees_having_an_event_today(event_type)
        for emp in emp_today_birthdays:
            frappe.get_doc(
                doctype="Notice Board",
                notice_title=title,
                message=message,
                from_date=today(),
                to_date=today(),
                apply_for="Specific Employees",
                employees=[dict(employee=emp.get("emp_id"))],
            ).insert(ignore_permissions=True)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_task_list():
    try:
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
            ],
            filters={"_assign": ["like", f"%{frappe.session.user}%"]},
        )
        completed_task = []
        incomplete_task = []

        for task in tasks:
            if task["exp_end_date"]:
                task["exp_end_date"] = task["exp_end_date"].strftime("%d-%m-%Y")
            comments = frappe.get_all(
                "Comment",
                filters={
                    "reference_name": ["like", "%{0}%".format(task.get("name"))],
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
            project_name = frappe.db.get_value(
                "Project", {"name": task.get("project")}, ["project_name"]
            )
            task["project_name"] = project_name

            assigned_by = frappe.db.get_value(
                "User",
                {"name": task.get("assigned_by")},
                ["full_name as user", "user_image"],
                as_dict=1,
            )
            task["assigned_by"] = assigned_by
            assigned_to = frappe.get_all(
                "User",
                filters=[["User", "email", "in", json.loads(task.get("assigned_to"))]],
                fields=["full_name as user", "user_image"],
                order_by="creation asc",
            )

            task["assigned_to"] = assigned_to

            for comment in comments:
                comment["commented"] = pretty_date(comment["creation"])
                comment["creation"] = comment["creation"].strftime("%I:%M %p")
                user_image = frappe.get_value(
                    "User", comment.comment_email, "user_image", cache=True
                )
                comment["user_image"] = user_image

            task["comments"] = comments
            task["num_comments"] = len(comments)

            if task.status == "Completed":
                completed_task.append(task)
            else:
                incomplete_task.append(task)

        response_data = {"tasks": incomplete_task, "completed_tasks": completed_task}

        return gen_response(200, "Task list getting Successfully", response_data)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def update_task_status():
    try:
        if not frappe.request.json.get("task_id") or not frappe.request.json.get(
            "new_status"
        ):
            return gen_response(500, "task id and new status is required")
        assigned_to = frappe.get_value(
            "Task",
            {"name": frappe.request.json.get("task_id")},
            ["_assign", "status"],
            cache=True,
            as_dict=True,
        )

        if assigned_to.get("_assign") is None:
            return gen_response(500, "Task Not assigned for any user")

        elif frappe.session.user not in assigned_to.get("_assign"):
            return gen_response(500, "You are not authorized to update this task")

        elif frappe.request.json.get("new_status") not in frappe.get_meta(
            "Task"
        ).get_field("status").options.split("\n"):
            return gen_response(500, "Task status invalid")

        elif assigned_to.get("status") == frappe.request.json.get("new_status"):
            return gen_response(500, "status already up-to-date")

        frappe.db.set_value(
            "Task",
            frappe.request.json.get("task_id"),
            "status",
            frappe.request.json.get("new_status"),
        )

        return gen_response(200, "Task status updated successfully")

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_holiday_list(year=None):
    try:
        if not year:
            return gen_response(500, "year is required")
        emp_data = get_employee_by_user(frappe.session.user)

        from erpnext.setup.doctype.employee.employee import (
            get_holiday_list_for_employee,
        )

        holiday_list = get_holiday_list_for_employee(
            emp_data.name, raise_exception=False
        )

        if not holiday_list:
            return gen_response(200, "Holiday list get successfully", [])

        holidays = frappe.get_all(
            "Holiday",
            filters={
                "parent": holiday_list,
                "holiday_date": ("between", [f"{year}-01-01", f"{year}-12-31"]),
            },
            fields=["description", "holiday_date"],
        )

        if len(holidays) == 0:
            return gen_response(500, f"no holidays found for year {year}")

        holiday_list = []

        for holiday in holidays:
            holiday_date = frappe.utils.data.getdate(holiday.holiday_date)
            holiday_list.append(
                {
                    "year": holiday_date.strftime("%Y"),
                    "date": holiday_date.strftime("%d %b"),
                    "day": holiday_date.strftime("%A"),
                    "description": holiday.description,
                }
            )
        return gen_response(200, "Holiday List", holiday_list)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_task_list_dashboard():
    try:
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
            ],
            filters={"_assign": ["like", f"%{frappe.session.user}%"]},
            limit=4,
        )
        for task in tasks:
            if task["exp_end_date"]:
                task["exp_end_date"] = task["exp_end_date"].strftime("%d-%m-%Y")
            comments = frappe.get_all(
                "Comment",
                filters={
                    "reference_name": ["like", "%{0}%".format(task.get("name"))],
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

            project_name = frappe.db.get_value(
                "Project", {"name": task.get("project")}, ["project_name"]
            )
            task["project_name"] = project_name

            assigned_by = frappe.db.get_value(
                "User",
                {"name": task.get("assigned_by")},
                ["full_name as user", "user_image"],
                as_dict=1,
            )
            task["assigned_by"] = assigned_by

            for comment in comments:
                comment["commented"] = pretty_date(comment["creation"])
                comment["creation"] = comment["creation"].strftime("%I:%M %p")
                user_image = frappe.get_value(
                    "User", comment.comment_email, "user_image", cache=True
                )
                comment["user_image"] = user_image

            assigned_to = frappe.get_all(
                "User",
                filters=[["User", "email", "in", json.loads(task.get("assigned_to"))]],
                fields=["full_name as user", "user_image"],
                order_by="creation asc",
            )

            task["assigned_to"] = assigned_to

            task["comments"] = comments
            task["num_comments"] = len(comments)

        return gen_response(200, "Task list getting Successfully", tasks)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_attendance_list(year=None, month=None):
    try:
        if not year or not month:
            return gen_response(500, "year and month is required", [])
        emp_data = get_employee_by_user(frappe.session.user)
        present_count = 0
        absent_count = 0
        late_count = 0

        employee_attendance_list = frappe.get_all(
            "Attendance",
            filters={
                "employee": emp_data.get("name"),
                "attendance_date": [
                    "between",
                    [
                        f"{int(year)}-{int(month)}-01",
                        f"{int(year)}-{int(month)}-{calendar.monthrange(int(year), int(month))[1]}",
                    ],
                ],
            },
            fields=[
                "name",
                "DATE_FORMAT(attendance_date, '%d %W') AS attendance_date",
                "status",
                "working_hours",
                "in_time",
                "out_time",
                "late_entry",
            ],
        )

        if not employee_attendance_list:
            return gen_response(500, "no attendance found for this year and month", [])

        for attendance in employee_attendance_list:
            employee_checkin_details = frappe.get_all(
                "Employee Checkin",
                filters={"attendance": attendance.get("name")},
                fields=["log_type", "time_format(time, '%h:%i%p') as time"],
            )

            attendance["employee_checkin_detail"] = employee_checkin_details

            if attendance["status"] == "Present":
                present_count += 1

                if attendance["late_entry"] == 1:
                    late_count += 1

            elif attendance["status"] == "Absent":
                absent_count += 1

            del attendance["name"]
            del attendance["status"]
            del attendance["late_entry"]

        attendance_details = {
            "days_in_month": calendar.monthrange(int(year), int(month))[1],
            "present": present_count,
            "absent": absent_count,
            "late": late_count,
        }
        attendance_data = {
            "attendance_details": attendance_details,
            "attendance_list": employee_attendance_list,
        }
        return gen_response(
            200, "Attendance data getting Successfully", attendance_data
        )

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def add_comment(reference_doctype=None, reference_name=None, content=None):
    try:
        from frappe.desk.form.utils import add_comment

        comment_by = frappe.db.get_value(
            "User", frappe.session.user, "full_name", as_dict=1
        )

        add_comment(
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            content=content,
            comment_email=frappe.session.user,
            comment_by=comment_by.get("full_name"),
        )
        return gen_response(200, "Comment Added Successfully")

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_comments(reference_doctype=None, reference_name=None):
    """
    reference_doctype: doctype
    reference_name: docname
    """
    try:
        filters = [
            ["Comment", "reference_doctype", "=", f"{reference_doctype}"],
            ["Comment", "reference_name", "=", f"{reference_name}"],
            ["Comment", "comment_type", "=", "Comment"],
        ]
        comments = frappe.get_all(
            "Comment",
            filters=filters,
            fields=[
                "content as comment",
                "comment_by",
                "creation",
                "comment_email",
            ],
        )

        for comment in comments:
            user_image = frappe.get_value(
                "User", comment.comment_email, "user_image", cache=True
            )
            comment["user_image"] = user_image
            comment["commented"] = pretty_date(comment["creation"])
            comment["creation"] = comment["creation"].strftime("%I:%M %p")

        return gen_response(200, "Comment Getting Successfully", comments)

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_profile():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        employee_details = frappe.get_cached_value(
            "Employee",
            emp_data.get("name"),
            [
                "employee_name",
                "designation",
                "name",
                "date_of_joining",
                "date_of_birth",
                "gender",
                "company_email",
                "personal_email",
                "cell_number",
                "emergency_phone_number",
            ],
            as_dict=True,
        )
        employee_details["date_of_joining"] = employee_details[
            "date_of_joining"
        ].strftime("%d-%m-%Y")
        employee_details["date_of_birth"] = employee_details["date_of_birth"].strftime(
            "%d-%m-%Y"
        )

        employee_details["employee_image"] = frappe.get_cached_value(
            "Employee", emp_data.get("name"), "image"
        )

        return gen_response(200, "My Profile", employee_details)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def upload_documents():
    try:
        emp_data = get_employee_by_user(frappe.session.user)

        from frappe.handler import upload_file

        file_doc = upload_file()

        ess_document = frappe.get_doc(
            {
                "doctype": "ESS Documents",
                "employee_no": emp_data.get("name"),
                "title": frappe.form_dict.title,
            }
        ).insert()

        file_doc.attached_to_doctype = "ESS Documents"
        file_doc.attached_to_name = str(ess_document.name)
        file_doc.attached_to_field = "attachement"
        file_doc.save()

        ess_document.attachement = file_doc.file_url
        ess_document.save()

        return gen_response(200, "Document Added Successfully")
    except Exception as e:
        return exception_handel(e)


def get_file_size(file_path, unit="auto"):
    file_size = os.path.getsize(file_path)

    units = ["B", "Kb", "Mb", "Gb", "Tb"]
    if unit == "auto":
        unit_index = 0
        while file_size > 1000:
            file_size /= 1000
            unit_index += 1
            if unit_index == len(units) - 1:
                break
        unit = units[unit_index]
    else:
        unit_index = units.index(unit)

    return f"{file_size:.2f}{unit}"


@frappe.whitelist()
@ess_validate(methods=["GET"])
def document_list():
    try:
        from frappe.utils.file_manager import get_file_path

        emp_data = get_employee_by_user(frappe.session.user)
        documents = frappe.get_all(
            "ESS Documents",
            filters={
                "employee_no": emp_data.get("name"),
            },
            fields=["name", "attachement"],
        )

        if documents:
            for doc in documents:
                file = frappe.get_value(
                    "File",
                    {
                        "file_url": doc.get("attachement"),
                        "attached_to_doctype": "ESS Documents",
                        "attached_to_name": doc.get("name"),
                    },
                    ["name", "file_name", "file_size"],
                    as_dict=1,
                )
                if file:
                    doc["file_name"] = file.get("file_name")
                    doc["file_size"] = get_file_size(
                        (get_file_path(file.get("file_name"))), unit="auto"
                    )
                    doc["file_id"] = file.get("name")

            return gen_response(200, "Documents found for employee", documents)
        else:
            return gen_response(500, "No documents found for employee", [])
    except Exception as e:
        return exception_handel(e)


def leave_application_list(date=None):
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        validate_employee_data(emp_data)
        leave_application_fields = [
            "name",
            "leave_type",
            "from_date",
            "to_date",
            "total_leave_days",
            "description",
            "status",
            "posting_date",
        ]

        filters = {"employee": emp_data.get("name")}

        if date:
            date = getdate(date)
            filters["from_date"] = ["<=", date]
            filters["to_date"] = [">=", date]

        upcoming_leaves = frappe.get_all(
            "Leave Application",
            filters=filters,
            fields=leave_application_fields,
        )

        leave_applications = {"upcoming": upcoming_leaves}

        return leave_applications
    except Exception as e:
        return exception_handel(e)


def notice_board_list(employee=None, date=None):
    filters = [
        ["Notice Board Employee", "employee", "=", employee],
        ["Notice Board", "apply_for", "=", "Specific Employees"],
        ["Notice Board", "from_date", "<=", getdate(date)],
        ["Notice Board", "to_date", ">=", getdate(date)],
    ]
    notice_board_employee = frappe.get_all(
        "Notice Board",
        filters=filters,
        fields=["notice_title as title", "message as description"],
    )
    common_filters = [
        ["Notice Board", "apply_for", "=", "All Employee"],
        ["Notice Board", "from_date", "<=", getdate(date)],
        ["Notice Board", "to_date", ">=", getdate(date)],
    ]
    notice_board_common = frappe.get_all(
        "Notice Board",
        filters=common_filters,
        fields=["notice_title as title", "message as description"],
    )
    notice_board_employee.extend(notice_board_common)
    return notice_board_employee


def holiday_list(date=None):
    emp_data = get_employee_by_user(frappe.session.user)
    from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

    holiday_list = get_holiday_list_for_employee(emp_data.name, raise_exception=False)

    filters = [
        ["Holiday", "holiday_date", "=", getdate(date)],
        ["Holiday", "parent", "=", holiday_list],
    ]

    holidays = frappe.get_all(
        "Holiday", filters=filters, fields=["'holiday' as title", "description"]
    )

    return holidays


@frappe.whitelist()
@ess_validate(methods=["GET"])
def upcoming_activity(date=None):
    try:
        if not date:
            return gen_response(500, "date is required", [])

        leaves = leave_application_list(date=date)

        upcoming_data = {date: []}

        for leave in leaves["upcoming"]:
            upcoming_data[date].append(
                {"title": leave.get("name"), "description": leave.get("leave_type")}
            )

        notice_board = notice_board_list(
            get_employee_by_user(frappe.session.user).get("name"), date=date
        )
        if notice_board:
            upcoming_data[date].extend(notice_board)

        birthday = get_employees_having_an_event_today("birthday", date=date)
        for birthdate in birthday:
            upcoming_data[date].append(
                {
                    "title": f"{birthdate.get('name')}'s Birthday",
                    "description": birthdate.get("name"),
                    "image": birthdate.get("image"),
                }
            )

        work_anniversary = get_employees_having_an_event_today(
            "work_anniversary", date=date
        )
        for anniversary in work_anniversary:
            upcoming_data[date].append(
                {
                    "title": f"{anniversary.get('name')}'s work anniversary",
                    "description": anniversary.get("name"),
                    "image": anniversary.get("image"),
                }
            )
        holidays = holiday_list(date=date)
        if holidays:
            upcoming_data[date].extend(holidays)

        return gen_response(200, "Upcoming Activity", upcoming_data)

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def employee_device_info(**kwargs):
    try:
        data = kwargs
        existing_token = frappe.db.get_value(
            "Employee Device Info",
            filters={"user": frappe.session.user},
            fieldname="name",
        )
        if frappe.db.exists("Employee Device Info", existing_token):
            token = frappe.get_doc("Employee Device Info", existing_token)
            token.platform = data.get("platform")
            token.os_version = data.get("os_version")
            token.device_name = data.get("device_name")
            token.app_version = data.get("app_version")
            token.token = data.get("token")
            token.save(ignore_permissions=True)
        else:
            token = frappe.get_doc(
                doctype="Employee Device Info",
                platform=data.get("platform"),
                os_version=data.get("os_version"),
                device_name=data.get("device_name"),
                app_version=data.get("app_version"),
                token=data.get("token"),
                user=frappe.session.user,
            ).insert(ignore_permissions=True)

        return gen_response(200, "Firebase Token Generated successfully")
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def notification_list():
    try:
        notifications = frappe.get_all(
            "ESS Notification Log",
            filters={"recipient": frappe.session.user},
            fields=["name", "subject", "message", "read", "creation", "reference_document", "reference_name"],
            order_by="creation desc"
        )
        
        for notification in notifications:
            notification["creation"] = pretty_date(notification.get("creation"))
            
        return gen_response(200, "ESS Notification Log", notifications)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_workflow_timeline(doctype: str, docname: str):
    """
    Get workflow timeline information for any document (workflow-enabled or not).
    
    Args:
        doctype (str): The DocType of the document (e.g., "Leave Application")
        docname (str): The name of the document (e.g., "HR-LAP-2026-00018")
        
    Returns:
        dict: Workflow timeline information in the specified format
        
    Example Usage:
        curl -X GET "http://your-site.com/api/method/employee_self_service.mobile.ess.get_workflow_timeline?doctype=Leave%20Application&docname=HR-LAP-2026-00018"
        
    Example Response (Workflow-enabled, Approved):
        {
            "success": true,
            "has_workflow": true,
            "workflow_name": "Leave Approval Workflow",
            "current_state": "Approved by Manager",
            "current_status": "Approved",
            "timeline": [
                {
                    "state": "Draft",
                    "status": "completed",
                    "action_by": null,
                    "action_at": null
                },
                {
                    "state": "Pending Manager Review",
                    "status": "completed",
                    "action_by": null,
                    "action_at": null
                },
                {
                    "state": "Approved by Manager",
                    "status": "completed",
                    "action_by": "testhr@gmail.com",
                    "action_at": "2026-05-31 18:19:48"
                }
            ],
            "pending_roles": [],
            "is_final_state": true
        }
        
    Example Response (Workflow-enabled, Pending):
        {
            "success": true,
            "has_workflow": true,
            "workflow_name": "Leave Approval Workflow",
            "current_state": "Pending Manager Review",
            "current_status": "Open",
            "timeline": [
                {
                    "state": "Draft",
                    "status": "completed"
                },
                {
                    "state": "Pending Manager Review",
                    "status": "current"
                },
                {
                    "state": "Approved by Manager",
                    "status": "pending"
                }
            ],
            "pending_roles": [
                "Leave Approver"
            ],
            "is_final_state": false
        }
        
    Example Response (Non-workflow document):
        {
            "success": true,
            "has_workflow": false,
            "workflow_name": null,
            "current_state": null,
            "current_status": "Approved",
            "timeline": [
                {
                    "state": "Created",
                    "status": "completed"
                },
                {
                    "state": "Approved",
                    "status": "completed"
                }
            ],
            "pending_roles": [],
            "is_final_state": true
        }
    """
    try:
        # Validate that the document exists and user has read access
        doc = frappe.get_doc(doctype, docname)
        
        # Initialize response structure
        response = {
            "success": True,
            "has_workflow": False,
            "workflow_name": None,
            "current_state": None,
            "current_status": doc.get("status", "Unknown"),
            "timeline": [],
            "pending_roles": [],
            "is_final_state": True
        }
        
        # Check if there's an active workflow for this doctype
        workflow_list = frappe.get_all(
            "Workflow",
            filters={
                "document_type": doctype,
                "is_active": 1
            },
            fields=["name", "workflow_state_field"],
            limit=1
        )
        
        if workflow_list:
            # Workflow exists - populate workflow-specific fields
            workflow = frappe.get_doc("Workflow", workflow_list[0].name)
            response["has_workflow"] = True
            response["workflow_name"] = workflow.workflow_name
            
            # Get workflow state field from workflow definition
            workflow_state_field = workflow.workflow_state_field or "workflow_state"
            
            # Get current workflow state from document
            current_state = doc.get(workflow_state_field)
            response["current_state"] = current_state
            
            # Get workflow states and transitions from the workflow document
            states = [s.state for s in workflow.states]
            transitions = workflow.transitions
            
            # Build state transition map for efficient lookup
            state_transitions = {}
            for transition in transitions:
                if transition.state not in state_transitions:
                    state_transitions[transition.state] = []
                state_transitions[transition.state].append(transition)
            
            # Identify final states (states with no outgoing transitions)
            final_states = set()
            for state in states:
                if state not in state_transitions or not state_transitions[state]:
                    final_states.add(state)
            
            # Fetch workflow comments
            comments = frappe.get_all(
                "Comment",
                filters={
                    "comment_type": "Workflow",
                    "reference_doctype": doctype,
                    "reference_name": docname
                },
                fields=["content", "owner", "creation"],
                order_by="creation asc"
            )
            
            # Parse comments to extract state transitions
            comment_events = []  # List of (state, action_by, action_at) tuples
            for comment in comments:
                # Try to extract state from comment content
                # Common patterns: "State changed from X to Y", "Approved by user", etc.
                content = comment.content
                owner = comment.owner
                creation = comment.creation.strftime("%Y-%m-%d %H:%M:%S")
                
                # Look for state names in the comment
                matched_state = None
                for state in states:
                    if state in content:
                        matched_state = state
                        break
                
                if matched_state:
                    comment_events.append((matched_state, owner, creation))
            
            # Build timeline based on actual workflow progression
            # We'll determine completed states by analyzing comments and current state
            completed_states = set()
            
            # Add states that have comments indicating they were reached
            for state, _, _ in comment_events:
                completed_states.add(state)
            
            # If we have a current state, add it and potentially previous states
            if current_state and current_state in states:
                completed_states.add(current_state)
                
                # For simplicity, we'll consider all states before current in the workflow definition as completed
                # A more sophisticated approach would analyze comment timestamps
                try:
                    current_index = states.index(current_state)
                    for i in range(current_index):
                        completed_states.add(states[i])
                except ValueError:
                    pass  # current_state not in states list
            
            # Build timeline entries
            for state in states:
                # Determine status - FIXED: Final states should show as completed when they match current state
                if state == current_state:
                    if current_state in final_states:
                        status = "completed"
                    else:
                        status = "current"
                elif state in completed_states:
                    status = "completed"
                else:
                    status = "pending"
                
                # Find comment for this state
                action_by = None
                action_at = None
                for state_comment, owner, creation in comment_events:
                    if state_comment == state:
                        action_by = owner
                        action_at = creation
                        break
                
                response["timeline"].append({
                    "state": state,
                    "status": status,
                    "action_by": action_by,
                    "action_at": action_at
                })
            
            # Determine pending approvers (roles that can act on current state)
            pending_roles = []
            if current_state and current_state in state_transitions:
                # Get outgoing transitions from current state
                for transition in state_transitions[current_state]:
                    # Extract allowed roles from transition
                    allowed_roles = []
                    if hasattr(transition, 'allowed') and transition.allowed:
                        allowed = transition.allowed
                        if isinstance(allowed, str):
                            # Handle comma-separated roles or JSON-like strings
                            if allowed.startswith('[') and allowed.endswith(']'):
                                # Try to parse as JSON list
                                import json
                                try:
                                    allowed_roles = json.loads(allowed)
                                except:
                                    # Fallback to comma-separated
                                    allowed_roles = [r.strip().strip('"\'') for r in allowed[1:-1].split(',') if r.strip()]
                            else:
                                # Comma-separated string
                                allowed_roles = [r.strip() for r in allowed.split(',') if r.strip()]
                        else:
                            allowed_roles = [str(allowed)]
                    elif hasattr(transition, 'role') and transition.role:
                        allowed_roles = [transition.role]
                    
                    pending_roles.extend(allowed_roles)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_pending_roles = []
            for role in pending_roles:
                if role not in seen:
                    seen.add(role)
                    unique_pending_roles.append(role)
            pending_roles = unique_pending_roles
            
            # Determine if current state is final
            is_final_state = current_state in final_states if current_state else True
            
            # Update response with workflow-specific values
            response.update({
                "current_state": current_state,
                "pending_roles": pending_roles,
                "is_final_state": is_final_state
            })
        
        else:
            # No workflow exists - create a simple timeline based on document status
            # This is a fallback for non-workflow doctypes
            status = doc.get("status", "Unknown")
            
            # Create a basic timeline with common states
            timeline_states = ["Created", status]
            # Remove duplicates while preserving order
            seen = set()
            unique_states = []
            for state in timeline_states:
                if state not in seen:
                    seen.add(state)
                    unique_states.append(state)
            
            # Mark all as completed since we don't have workflow tracking
            for state in unique_states:
                response["timeline"].append({
                    "state": state,
                    "status": "completed",
                    "action_by": None,
                    "action_at": None
                })
            
            # For non-workflow docs, we consider them final state
            response["is_final_state"] = True
        
        return response
        
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "message": f"Document {doctype} {docname} does not exist"
        }
    except frappe.PermissionError:
        return {
            "success": False,
            "message": f"Insufficient permissions to access {doctype} {docname}"
        }
    except Exception as e:
        frappe.log_error(f"Error in get_workflow_timeline: {frappe.get_traceback()}")
        return {
            "success": False,
            "message": f"An error occurred while fetching workflow timeline: {str(e)}"
        }


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_branch():
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["branch"])
        branch = frappe.db.get_value(
            "Branch",
            {"branch": emp_data.get("branch")},
            ["branch", "latitude", "longitude", "radius"],
            as_dict=1,
        )

        return gen_response(200, "Branch", branch)
    except Exception as e:
        return exception_handel(e)


def on_leave_application_update(doc, event):
    user = frappe.get_value("Employee", {"name": doc.employee}, "user_id")
    leave_approver = frappe.get_value(
        "Employee", {"prefered_email": doc.leave_approver}, "employee_name"
    )

    if doc.status == "Approved":
        create_push_notification(
            title=f"{doc.name} is Approved",
            message=f"{leave_approver} accept your leave request",
            send_for="Single User",
            user=user,
            notification_type="leave_application",
        )

    elif doc.status == "Rejected":
        create_push_notification(
            title=f"{doc.name} is Rejected",
            message=f"{leave_approver} reject your leave request",
            send_for="Single User",
            user=user,
            notification_type="leave_application",
        )


def on_expense_submit(doc, event):
    user = frappe.get_value("Employee", {"name": doc.employee}, "user_id")
    expense_approver = frappe.get_value(
        "Employee", {"prefered_email": doc.expense_approver}, "employee_name"
    )
    if doc.approval_status == "Approved":
        create_push_notification(
            title=f"{doc.name} is Approved",
            message=f"{expense_approver} accept your expense claim request",
            send_for="Single User",
            user=user,
            notification_type="expense_claim",
        )

    elif doc.approval_status == "Rejected":
        create_push_notification(
            title=f"{doc.name} is Rejected",
            message=f"{expense_approver} reject your expense claim request",
            send_for="Single User",
            user=user,
            notification_type="expense_claim",
        )


@frappe.whitelist()
def change_password(data):
    try:
        from frappe.utils.password import check_password, update_password

        user = frappe.session.user
        current_password = data.get("current_password")
        new_password = data.get("new_password")
        check_password(user, current_password)
        update_password(user, new_password)
        return gen_response(200, "Password updated")
    except frappe.AuthenticationError:
        return gen_response(500, "Incorrect current password")
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_task_by_id(task_id=None):
    try:
        if not task_id:
            return gen_response(500, "task_id is required", [])
        filters = [
            ["Task", "name", "=", task_id],
            ["Task", "_assign", "like", f"%{frappe.session.user}%"],
        ]
        tasks = frappe.db.get_value(
            "Task",
            filters,
            [
                "name",
                "subject",
                "project",
                "priority",
                "status",
                "description",
                "exp_end_date",
                "_assign as assigned_to",
                "owner as assigned_by",
            ],
            as_dict=1,
        )
        if not tasks:
            return gen_response(500, "you have not task with this task id", [])

        assigned_by = frappe.db.get_value(
            "User",
            {"name": tasks.get("assigned_by")},
            ["full_name as user", "user_image"],
            as_dict=1,
        )
        tasks["assigned_by"] = assigned_by

        project_name = frappe.db.get_value(
            "Project", {"name": tasks.get("project")}, ["project_name"]
        )
        tasks["project_name"] = project_name

        assigned_to = frappe.get_all(
            "User",
            filters=[["User", "email", "in", json.loads(tasks.get("assigned_to"))]],
            fields=["full_name as user", "user_image"],
            order_by="creation asc",
        )

        tasks["assigned_to"] = assigned_to

        comments = frappe.get_all(
            "Comment",
            filters={
                "reference_name": ["like", "%{0}%".format(tasks.get("name"))],
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
            user_image = frappe.get_value(
                "User", comment.comment_email, "user_image", cache=True
            )
            comment["user_image"] = user_image

        tasks["comments"] = comments
        tasks["num_comments"] = len(comments)

        return gen_response(200, "Task", tasks)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def apply_expense():
    try:
        emp_data = get_employee_by_user(
            frappe.session.user, fields=["name", "company", "expense_approver"]
        )

        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)

        payable_account = get_payable_account(emp_data.get("company"))
        expense_doc = frappe.get_doc(
            doctype="Expense Claim",
            employee=emp_data.name,
            expense_approver=emp_data.expense_approver,
            expenses=[
                {
                    "expense_date": frappe.form_dict.expense_date,
                    "expense_type": frappe.form_dict.expense_type,
                    "description": frappe.form_dict.description,
                    "amount": frappe.form_dict.amount,
                }
            ],
            posting_date=today(),
            company=emp_data.get("company"),
            payable_account=payable_account,
        ).insert()

        from frappe.handler import upload_file

        if "file" in frappe.request.files:
            file = upload_file()
            file.attached_to_doctype = "Expense Claim"
            file.attached_to_name = expense_doc.name
            file.save(ignore_permissions=True)

        return gen_response(200, "Expense applied Successfully", expense_doc)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def update_profile_picture():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        from frappe.handler import upload_file

        employee_profile_picture = upload_file()
        employee_profile_picture.attached_to_doctype = "Employee"
        employee_profile_picture.attached_to_name = emp_data.get("name")
        employee_profile_picture.attached_to_field = "image"
        employee_profile_picture.save(ignore_permissions=True)

        frappe.db.set_value(
            "Employee", emp_data.get("name"), "image", employee_profile_picture.file_url
        )
        if employee_profile_picture:
            frappe.db.set_value(
                "User",
                frappe.session.user,
                "user_image",
                employee_profile_picture.file_url,
            )
        return gen_response(200, "Employee profile picture updated successfully")
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_transactions(
    from_date=None, to_date=None, party_type=None, party=None, download="false"
):
    try:
        from_date = getdate(from_date)
        to_date = getdate(to_date)
        if not from_date or not to_date:
            frappe.throw(_("Select First from date and to date"))
        global_defaults = get_global_defaults()
        if not party_type:
            party_type = "Employee"
        if not party:
            emp_data = get_employee_by_user(frappe.session.user)
            party = [emp_data.get("name")]
        allowed_party_types = ["Employee", "Customer"]
        if party_type not in allowed_party_types:
            frappe.throw(
                _("Invalid party type. Allowed party types are {0}").format(
                    ", ".join(allowed_party_types)
                )
            )
        filters_report = {
            "company": global_defaults.get("default_company"),
            "from_date": from_date,
            "to_date": to_date,
            "account": [],
            "party_type": party_type,
            "party": party,
            "group_by": "Group by Party",
            "cost_center": [],
            "project": [],
            "include_dimensions": 1,
        }
        if party_type == "Employee" and isinstance(party, list) and len(party) == 1:
            filters_report["party_name"] = frappe.db.get_value(
                party_type, party[0], "employee_name"
            )
        else:
            filters_report["party_name"] = (
                ", ".join(party) if party and len(party) > 0 else ""
            )

        from frappe.desk.query_report import run

        res = run("General Ledger", filters=filters_report, ignore_prepared_report=True)
        data = []
        total = {}
        opening_balance = {}
        if res.get("result"):
            for row in res.get("result"):
                if "gl_entry" in row.keys():
                    data.append(
                        {
                            "posting_date": row.get("posting_date").strftime(
                                "%d-%m-%Y"
                            ),
                            "voucher_type": row.get("voucher_type"),
                            "voucher_no": row.get("voucher_no"),
                            "debit": fmt_money(
                                row.get("debit"),
                                currency=global_defaults.get("default_currency"),
                            ),
                            "credit": fmt_money(
                                row.get("credit"),
                                currency=global_defaults.get("default_currency"),
                            ),
                            "balance": fmt_money(
                                row.get("balance"),
                                currency=global_defaults.get("default_currency"),
                            ),
                            "party_type": row.get("party_type"),
                            "party": row.get("party"),
                        }
                    )

                    if flt(row.get("balance")) >= 0:
                        row["color"] = "red"
                    else:
                        row["color"] = "green"
                if "'Opening'" in row.values():
                    opening_balance = {
                        "account": "Opening",
                        "posting_date": from_date.strftime("%d-%m-%Y"),
                        "credit": fmt_money(
                            row.get("credit"),
                            currency=global_defaults.get("default_currency"),
                        ),
                        "debit": fmt_money(
                            row.get("debit"),
                            currency=global_defaults.get("default_currency"),
                        ),
                        "balance": fmt_money(
                            row.get("balance"),
                            currency=global_defaults.get("default_currency"),
                        ),
                    }
                if "'Total'" in row.values():
                    total = {
                        "account": "Total",
                        "posting_date": to_date.strftime("%d-%m-%Y"),
                        "credit": fmt_money(
                            row.get("credit"),
                            currency=global_defaults.get("default_currency"),
                        ),
                        "debit": fmt_money(
                            row.get("debit"),
                            currency=global_defaults.get("default_currency"),
                        ),
                        "balance": fmt_money(
                            row.get("balance"),
                            currency=global_defaults.get("default_currency"),
                        ),
                    }
            data.insert(0, opening_balance)
            data.append(total)

            from frappe.utils.print_format import report_to_pdf

            if download == "true":
                html = frappe.render_template(
                    "employee_self_service/templates/employee_statement.html",
                    {
                        "data": data,
                        "filters": filters_report,
                        "user": frappe.db.get_value(
                            "User", frappe.session.user, "full_name"
                        ),
                    },
                    is_path=True,
                )
                return report_to_pdf(html)
        return gen_response(200, "Ledger Get Successfully", data)

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_customer_list():
    try:
        customer = frappe.get_list("Customer", ["name", "customer_name"])
        return gen_response(200, "Customr list Getting Successfully", customer)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_employee_list():
    try:
        employee = frappe.get_list("Employee", ["name", "employee_name"])
        return gen_response(200, "Employee list Getting Successfully", employee)
    except Exception as e:
        return exception_handel(e)


def send_notification_for_task_assign(doc, event):
    from frappe.utils.data import strip_html

    if doc.status == "Open" and doc.reference_type == "Task":
        filters = [["Task", "name", "=", f"{doc.reference_name}"]]
        task = frappe.db.get_value(
            "Task", filters, ["subject", "description"], as_dict=1
        )
        create_push_notification(
            title=f"New Task Assigned - {task.get('subject')}",
            message=strip_html(str(task.get("description")))
            if task.get("description")
            else "",
            send_for="Single User",
            user=doc.allocated_to,
            notification_type="task_assignment",
        )


@frappe.whitelist()
@ess_validate(methods=["DELETE"])
def delete_documents(file_id=None, attached_to_name=None):
    try:
        from frappe.utils.file_manager import remove_file

        attached_to_doctype = "ESS Documents"
        remove_file(
            fid=file_id,
            attached_to_doctype=attached_to_doctype,
            attached_to_name=attached_to_name,
        )
        frappe.delete_doc(attached_to_doctype, attached_to_name, force=1)
        return gen_response(200, "you have successfully deleted ESS Document")
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def create_task(**kwargs):
    try:
        from frappe.desk.form import assign_to

        data = kwargs
        task_doc = frappe.get_doc(doctype="Task")
        task_doc.update(data)
        task_doc.insert()
        if data.get("assign_to"):
            assign_to.add(
                {
                    "assign_to": data.get("assign_to"),
                    "doctype": task_doc.doctype,
                    "name": task_doc.name,
                }
            )
        return gen_response(200, "Task has been created successfully")
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_project_list():
    try:
        project_list = frappe.get_list("Project", ["name", "project_name"])
        return gen_response(200, "Project List getting Successfully", project_list)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_user_list():
    try:
        user_list = frappe.get_list("User", ["name", "full_name", "user_image"])
        return gen_response(200, "User List getting Successfully", user_list)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_task_status_list():
    try:
        task_status = frappe.get_meta("Task").get_field("status").options or ""
        if task_status:
            task_status = task_status.split("\n")
        return gen_response(200, "Status get successfully", task_status)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET", "POST"])
def get_task_dashboard_stats():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)

        filters = {"_assign": ["like", f"%{frappe.session.user}%"]}

        total = frappe.db.count("Task", filters)
        open = frappe.db.count("Task", {**filters, "status": "Open"})
        working = frappe.db.count("Task", {**filters, "status": "Working"})
        completed = frappe.db.count("Task", {**filters, "status": "Completed"})
        overdue = frappe.db.count(
            "Task",
            {
                **filters,
                "exp_end_date": ["<", today()],
                "status": ["!=", "Completed"],
            },
        )

        stats = {
            "total": total,
            "open": open,
            "working": working,
            "completed": completed,
            "overdue": overdue,
        }
        return gen_response(200, "Task Dashboard Stats Get Successfully", stats)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET", "POST"])
def add_task_comment(task_id=None, comment=None):
    try:
        if not task_id:
            return gen_response(500, "task_id is required")
        if not comment:
            return gen_response(500, "comment is required")

        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)

        task = frappe.get_value(
            "Task",
            {"name": task_id},
            ["_assign"],
            as_dict=True,
        )
        if not task:
            return gen_response(500, "Task not found")

        if frappe.session.user not in (task.get("_assign") or ""):
            return gen_response(500, "You are not authorized to comment on this task")

        frappe.get_doc(
            {
                "doctype": "Comment",
                "reference_doctype": "Task",
                "reference_name": task_id,
                "comment_type": "Comment",
                "content": comment,
                "comment_email": frappe.session.user,
                "comment_by": frappe.db.get_value(
                    "User", frappe.session.user, "full_name"
                ),
            }
        ).insert(ignore_permissions=True)

        return gen_response(200, "Comment added successfully")
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_travel_requests():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)
        travel_requests = frappe.get_all(
            "Travel Request",
            filters={"employee": emp_data.get("name")},
            fields=[
                "name",
                "purpose_of_travel",
                "DATE_FORMAT(from_date, '%d-%m-%Y') as from_date",
                "DATE_FORMAT(to_date, '%d-%m-%Y') as to_date",
                "status",
            ],
        )
        return gen_response(200, "Travel Request Get Successfully", travel_requests)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_travel_request_details(name=None):
    try:
        if not name:
            return gen_response(500, "Travel Request name is required", [])
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)
        travel_request = frappe.get_doc("Travel Request", name)
        if travel_request.employee != emp_data.get("name"):
            return gen_response(500, "You are not authorized to view this travel request")
        return gen_response(200, "Travel Request Details Get Successfully", travel_request)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def create_travel_request(**kwargs):
    try:
        emp_data = get_employee_by_user(
            frappe.session.user, fields=["name", "company"]
        )
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)
        data = kwargs
        travel_request = frappe.get_doc(
            doctype="Travel Request",
            purpose_of_travel=data.get("purpose_of_travel"),
            travel_type=data.get("travel_type"),
            company=emp_data.get("company"),
            employee=emp_data.get("name"),
            from_date=data.get("from_date"),
            to_date=data.get("to_date"),
            destination=data.get("destination"),
        ).insert()
        return gen_response(200, "Travel Request Created Successfully", travel_request)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def cancel_travel_request(name=None):
    try:
        if not name:
            return gen_response(500, "Travel Request name is required")
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)
        travel_request = frappe.get_doc("Travel Request", name)
        if travel_request.employee != emp_data.get("name"):
            return gen_response(500, "You are not authorized to cancel this travel request")
        if travel_request.status not in ["Draft", "Pending"]:
            return gen_response(500, "Only Draft and Pending travel requests can be cancelled")
        travel_request.status = "Cancelled"
        travel_request.save(ignore_permissions=True)
        return gen_response(200, "Travel Request Cancelled Successfully")
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_travel_dashboard_stats():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")
        validate_employee_data(emp_data)

        total = frappe.db.count("Travel Request", {"employee": emp_data.get("name")})
        approved = frappe.db.count(
            "Travel Request",
            {"employee": emp_data.get("name"), "status": "Approved"},
        )
        pending = frappe.db.count(
            "Travel Request",
            {"employee": emp_data.get("name"), "status": "Pending"},
        )
        rejected = frappe.db.count(
            "Travel Request",
            {"employee": emp_data.get("name"), "status": "Rejected"},
        )

        stats = {
            "total": total,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
        }
        return gen_response(200, "Travel Dashboard Stats Get Successfully", stats)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_leave_calendar_details(leave_application=None):
    """
    Get leave calendar details for a Leave Application.
    Reuses CentralHRMS get_leave_calendar_data() logic.

    Args:
        leave_application (str): Leave Application document name

    Returns:
        dict: Calendar data including leave details, holidays, weekends, effective days, etc.
    """
    try:
        if not leave_application:
            return gen_response(500, "leave_application is required", [])

        # Load Leave Application document
        leave_doc = frappe.get_doc("Leave Application", leave_application)
        #removed condition

        # Reuse CentralHRMS get_leave_calendar_data() - exact import path
        from centralhrms.api import get_leave_calendar_data

        # Call the existing function with leave application data
        calendar_data = get_leave_calendar_data(
            employee=leave_doc.employee,
            from_date=leave_doc.from_date,
            to_date=leave_doc.to_date,
            leave_type=leave_doc.leave_type
        )

        # Add leave application specific details
        result = {
            "leave_details": {
                "name": leave_doc.name,
                "leave_type": leave_doc.leave_type,
                "from_date": str(leave_doc.from_date),
                "to_date": str(leave_doc.to_date),
                "total_leave_days": leave_doc.total_leave_days,
                "status": leave_doc.status,
                "description": leave_doc.description
            },
            "calendar_days": calendar_data.get("total_calendar_days"),
            "public_holidays": calendar_data.get("public_holidays", []),
            "weekly_offs": calendar_data.get("weekly_offs", []),
            "effective_leave_days": calendar_data.get("effective_days"),
            "bridge_policy_data": {
                "bridge_fires": calendar_data.get("bridge_fires"),
                "previous_leave": calendar_data.get("bridge_previous_leave")
            },
            "existing_leaves": calendar_data.get("existing_leaves", []),
            "sick_leave_slab": calendar_data.get("sick_slab")
        }

        return gen_response(200, "Leave Calendar Details", result)

    except frappe.DoesNotExistError:
        return gen_response(500, f"Leave Application {leave_application} does not exist")
    except frappe.PermissionError:
        return gen_response(500, "Insufficient permissions")
    except Exception as e:
        return exception_handel(e)
