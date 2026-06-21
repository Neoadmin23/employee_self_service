import frappe
from frappe import _
from employee_self_service.mobile.v1.api_utils import (
	gen_response,
	ess_validate,
	get_employee_by_user,
	convert_timezone,
	get_system_timezone,
)
from frappe.utils import today, add_days, getdate


def _get_current_employee(fields=None):
	"""
	Get the Employee record linked to the currently logged-in user.

	Args:
		fields: List of fields to fetch from Employee. Defaults to ["name", "employee_name", "company"].

	Returns:
		dict: Employee document as a dictionary.

	Raises:
		frappe.DoesNotExistError: If no Employee is linked to the current user.
	"""
	if fields is None:
		fields = ["name", "employee_name", "company"]

	emp_data = get_employee_by_user(frappe.session.user, fields=fields)
	if not emp_data:
		frappe.throw(_("No Employee record linked to your user account. Please contact HR."))
	return emp_data


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_attendance_report(from_date=None, to_date=None, status=None):
	"""
	Get attendance records for the logged-in employee.

	Args:
		from_date: Start date for the report (optional). Defaults to 30 days ago.
		to_date: End date for the report (optional). Defaults to today.
		status: Filter by attendance status (optional). Values: Present, Absent, Half Day, On Leave.

	Returns:
		JSON response with summary and attendance data.
	"""
	try:
		emp_data = _get_current_employee()

		if not from_date:
			from_date = add_days(today(), -30)
		else:
			from_date = getdate(from_date)

		if not to_date:
			to_date = today()
		else:
			to_date = getdate(to_date)

		attendance_fields = [
			"name",
			"attendance_date",
			"status",
			"in_time",
			"out_time",
			"working_hours",
			"late_entry",
			"early_exit",
		]

		filters = {
			"employee": emp_data.get("name"),
			"attendance_date": ["between", [from_date, to_date]],
			"docstatus": 1,
		}
		if status:
			filters["status"] = status

		attendance_list = frappe.get_all(
			"Attendance",
			filters=filters,
			fields=attendance_fields,
			order_by="attendance_date desc",
		)

		summary = _calculate_attendance_summary(attendance_list)

		attendance_data = []
		user_time_zone = frappe.db.get_value("User", frappe.session.user, "time_zone")
		system_timezone = get_system_timezone()

		convert_tz = user_time_zone and user_time_zone != system_timezone

		for attendance in attendance_list:
			attendance_data.append({
				"date": attendance.attendance_date.strftime("%Y-%m-%d"),
				"status": attendance.status,
				"in_time": _format_time(attendance.in_time, convert_tz, system_timezone, user_time_zone) if attendance.in_time else None,
				"out_time": _format_time(attendance.out_time, convert_tz, system_timezone, user_time_zone) if attendance.out_time else None,
				"working_hours": round(attendance.working_hours, 2) if attendance.working_hours else 0,
				"late_entry": attendance.late_entry,
				"early_exit": attendance.early_exit,
			})

		return gen_response(200, "Attendance report fetched successfully", {
			"summary": summary,
			"attendance": attendance_data,
		})
	except Exception:
		frappe.log_error(
			title=_("ESS Reports: get_attendance_report Error"),
			message=frappe.get_traceback(),
		)
		return gen_response(500, _("Failed to fetch attendance report. Please try again."))


def _calculate_attendance_summary(attendance_list):
	"""
	Calculate attendance summary counts from a list of attendance records.

	Args:
		attendance_list: List of Attendance documents.

	Returns:
		dict: Summary with present_count, absent_count, leave_count, half_day_count, total.
	"""
	summary = {
		"present_count": 0,
		"absent_count": 0,
		"leave_count": 0,
		"half_day_count": 0,
		"total": 0,
	}

	for attendance in attendance_list:
		summary["total"] += 1
		record_status = attendance.get("status")

		if record_status == "Present":
			summary["present_count"] += 1
		elif record_status == "Absent":
			summary["absent_count"] += 1
		elif record_status == "Half Day":
			summary["half_day_count"] += 1
		elif record_status == "On Leave":
			summary["leave_count"] += 1

	return summary


def _format_time(time_value, convert_tz, from_tz, to_tz):
	"""
	Format a datetime value to a time string, optionally converting timezone.

	Args:
		time_value: Datetime value to format.
		convert_tz: Whether to convert timezone.
		from_tz: Source timezone.
		to_tz: Target timezone.

	Returns:
		str: Formatted time string (HH:MM AM/PM).
	"""
	if convert_tz:
		time_value = convert_timezone(time_value, from_tz, to_tz)

	if hasattr(time_value, "strftime"):
		return time_value.strftime("%I:%M %p")
	return str(time_value)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_employee_checkins(from_date=None, to_date=None):
	"""
	Get check-in records for the logged-in employee.

	Args:
		from_date: Start date for the report (optional). Defaults to 30 days ago.
		to_date: End date for the report (optional). Defaults to today.

	Returns:
		JSON response with check-in data.
	"""
	try:
		emp_data = _get_current_employee()

		if not from_date:
			from_date = add_days(today(), -30)
		else:
			from_date = getdate(from_date)

		if not to_date:
			to_date = today()
		else:
			to_date = getdate(to_date)

		checkin_fields = [
			"employee_name",
			"time",
			"log_type",
			"shift",
			"location",
		]

		checkin_filters = [
			["Employee Checkin", "employee", "=", emp_data.get("name")],
			["Employee Checkin", "time", "between", [from_date, to_date]],
		]

		checkin_list = frappe.get_all(
			"Employee Checkin",
			filters=checkin_filters,
			fields=checkin_fields,
			order_by="time desc",
		)

		user_time_zone = frappe.db.get_value("User", frappe.session.user, "time_zone")
		system_timezone = get_system_timezone()

		convert_tz = user_time_zone and user_time_zone != system_timezone

		checkin_data = []
		for checkin in checkin_list:
			checkin_data.append({
				"employee_name": checkin.employee_name,
				"time": _format_checkin_time(checkin.time, convert_tz, system_timezone, user_time_zone),
				"log_type": checkin.log_type,
				"shift": checkin.shift,
				"location": checkin.location,
			})

		return gen_response(200, "Check-in report fetched successfully", {
			"checkins": checkin_data,
		})
	except Exception:
		frappe.log_error(
			title=_("ESS Reports: get_employee_checkins Error"),
			message=frappe.get_traceback(),
		)
		return gen_response(500, _("Failed to fetch check-in report. Please try again."))


def _format_checkin_time(time_value, convert_tz, from_tz, to_tz):
	"""
	Format a check-in time value, optionally converting timezone.

	Args:
		time_value: Datetime value to format.
		convert_tz: Whether to convert timezone.
		from_tz: Source timezone.
		to_tz: Target timezone.

	Returns:
		str: Formatted datetime string (YYYY-MM-DD HH:MM).
	"""
	if convert_tz and time_value:
		time_value = convert_timezone(time_value, from_tz, to_tz)

	if time_value and hasattr(time_value, "strftime"):
		return time_value.strftime("%Y-%m-%d %H:%M")
	return str(time_value)