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