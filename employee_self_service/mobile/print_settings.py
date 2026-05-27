# Copyright (c) 2026, Nesscale Solutions Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def validate_admin_permission():
	"""
	Check if current session user is an active ESS Admin User.
	
	Throws:
		frappe.ValidationError: If user is not authorized
	"""
	user = frappe.session.user
	if not frappe.db.exists(
		"ESS Admin User",
		{"user": user, "is_active": 1}
	):
		frappe.throw(_("Not authorized"))


@frappe.whitelist()
def get_salary_slip_print_formats():
	"""
	Return all Print Format records which belong to Salary Slip.
	
	Returns:
		dict: Response with success status and list of print formats
	"""
	try:
		validate_admin_permission()
		
		print_formats = frappe.get_all(
			"Print Format",
			filters={
				"doc_type": "Salary Slip"
			},
			fields=["name"],
			order_by="name asc"
		)
		
		return {
			"success": True,
			"data": print_formats
		}
	except Exception:
		frappe.log_error()
		return {
			"success": False,
			"data": []
		}


@frappe.whitelist()
def get_company_print_settings(company):
	"""
	Return current saved print setting for a company.
	
	Args:
		company (str): Company name
	
	Returns:
		dict: Response with success status and print setting data
	"""
	try:
		validate_admin_permission()
		
		setting = frappe.db.get_value(
			"ESS Company Print Settings",
			company,
			["company", "salary_slip_print_format", "is_active"],
			as_dict=True
		)
		
		if setting:
			return {
				"success": True,
				"data": {
					"company": setting.company,
					"salary_slip_print_format": setting.salary_slip_print_format,
					"is_active": setting.is_active
				}
			}
		return {
			"success": True,
			"data": None
		}
	except Exception:
		frappe.log_error()
		return {
			"success": False,
			"data": None
		}


@frappe.whitelist()
def save_company_print_settings(company, salary_slip_print_format):
	"""
	Create/update ESS Company Print Settings.
	
	Args:
		company (str): Company name
		salary_slip_print_format (str): Print format name
	
	Returns:
		dict: Response with success status and message
	"""
	try:
		validate_admin_permission()
		
		# Validate Print Format exists
		if not frappe.db.exists(
			"Print Format",
			{
				"name": salary_slip_print_format,
				"doc_type": "Salary Slip"
			}
		):
			frappe.throw(_("Invalid Salary Slip Print Format"))
		
		# Check if record exists
		if frappe.db.exists("ESS Company Print Settings", company):
			# Update existing record
			doc = frappe.get_doc("ESS Company Print Settings", company)
			doc.salary_slip_print_format = salary_slip_print_format
			doc.is_active = 1
			doc.save(ignore_permissions=True)
		else:
			# Create new record
			frappe.get_doc(
				doctype="ESS Company Print Settings",
				company=company,
				salary_slip_print_format=salary_slip_print_format,
				is_active=1
			).insert(ignore_permissions=True)
		
		frappe.db.commit()
		return {
			"success": True,
			"message": _("Print settings saved successfully")
		}
	except Exception as e:
		frappe.log_error()
		frappe.throw(str(e))


@frappe.whitelist()
def get_salary_slip_selected_print_format(company):
	"""
	Get the selected print format for a company (used for salary preview/PDF).
	
	Args:
		company (str): Company name
	
	Returns:
		dict: Response with success status and print format name
	"""
	try:
		setting = frappe.db.get_value(
			"ESS Company Print Settings",
			company,
			"salary_slip_print_format"
		)
		
		if setting:
			return {
				"success": True,
				"print_format": setting
			}
		return {
			"success": True,
			"print_format": "Standard"
		}
	except Exception:
		frappe.log_error()
		return {
			"success": True,
			"print_format": "Standard"
		}