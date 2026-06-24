import frappe
from frappe import _
from employee_self_service.mobile.api_utils import ess_validate
from employee_self_service.mobile.ess_admin import _apply_approval_action


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_pending_loan_approvals():
    """
    Get all pending loan applications for admin approval.
    Returns list of Loan Application records with status "Open".
    """
    try:
        applications = frappe.get_all(
            "Loan Application",
            filters={"status": "Open"},
            fields=[
                "name",
                "applicant",
                "applicant_name",
                "loan_product",
                "loan_amount",
                "posting_date",
                "repayment_method",
                "repayment_periods",
                "repayment_amount",
                "description",
                "status",
            ],
        )
        return applications
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_loan_application_approval_details(name):
    """
    Get detailed information for a specific Loan Application.

    Args:
        name: Loan Application document name

    Returns:
        dict: Loan Application details including applicant info, loan terms, and status
    """
    try:
        if not frappe.db.exists("Loan Application", name):
            frappe.throw("Loan Application not found")

        doc = frappe.get_doc("Loan Application", name)

        result = {
            "name": doc.name,
            "applicant": doc.applicant,
            "applicant_name": doc.applicant_name,
            "company": doc.company,
            "loan_product": doc.loan_product,
            "loan_amount": doc.loan_amount,
            "posting_date": doc.posting_date.strftime("%d-%m-%Y") if doc.posting_date else None,
            "repayment_method": doc.repayment_method,
            "repayment_periods": doc.repayment_periods,
            "repayment_amount": doc.repayment_amount,
            "total_payable_amount": doc.total_payable_amount,
            "total_payable_interest": doc.total_payable_interest,
            "description": doc.description,
            "status": doc.status,
            "is_secured_loan": doc.is_secured_loan,
        }
        return result
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
@ess_validate(methods=["POST"])
def approve_loan_application(name, remarks=None):
    """
    Approve a Loan Application.

    Args:
        name: Loan Application document name
        remarks: Optional remarks

    Returns:
        dict: Success response
    """
    try:
        if not frappe.db.exists("Loan Application", name):
            frappe.throw("Loan Application not found")

        _apply_approval_action("Loan Application", name, "approve", remarks)
        doc = frappe.get_doc("Loan Application", name)
        if doc.docstatus == 0:
            doc.submit()
        return {"success": True, "message": "Loan application approved successfully"}
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
@ess_validate(methods=["POST"])
def reject_loan_application(name, remarks=None):
    """
    Reject a Loan Application.

    Args:
        name: Loan Application document name
        remarks: Optional remarks

    Returns:
        dict: Success response
    """
    try:
        if not frappe.db.exists("Loan Application", name):
            frappe.throw("Loan Application not found")

        _apply_approval_action("Loan Application", name, "reject", remarks)
        return {"success": True, "message": "Loan application rejected successfully"}
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
@ess_validate(methods=["POST"])
def create_loan_from_application(name, repayment_start_date):
    """
    Create a new Loan document from an approved Loan Application.

    Args:
        name: Loan Application document name
        repayment_start_date: Date string for repayment start

    Returns:
        dict: Success response with created loan details
    """
    try:
        if not frappe.db.exists("Loan Application", name):
            frappe.throw("Loan Application not found")

        application = frappe.get_doc("Loan Application", name)

        if application.status != "Approved":
            frappe.throw("Loan Application must be Approved before creating a Loan")

        if frappe.db.exists("Loan", {"loan_application": name}):
            frappe.throw("A Loan already exists for this Loan Application")

        loan_product_doc = frappe.get_doc("Loan Product", application.loan_product)

        new_doc = frappe.get_doc(
            {
                "doctype": "Loan",
                "applicant_type": application.applicant_type,
                "applicant": application.applicant,
                "company": application.company,
                "posting_date": frappe.utils.today(),
                "loan_product": application.loan_product,
                "loan_application": application.name,
                "loan_amount": application.loan_amount,
                "is_secured_loan": application.is_secured_loan,
                "repayment_method": application.repayment_method,
                "repayment_periods": application.repayment_periods,
                "repayment_start_date": repayment_start_date,
                "monthly_repayment_amount": application.repayment_amount,
                "rate_of_interest": loan_product_doc.rate_of_interest,
                "is_term_loan": loan_product_doc.is_term_loan,
                "repayment_schedule_type": loan_product_doc.repayment_schedule_type,
                "mode_of_payment": loan_product_doc.mode_of_payment,
                "disbursement_account": loan_product_doc.disbursement_account,
                "payment_account": loan_product_doc.payment_account,
                "loan_account": loan_product_doc.loan_account,
                "interest_income_account": loan_product_doc.interest_income_account,
                "penalty_income_account": loan_product_doc.penalty_income_account,
            }
        ).insert(ignore_permissions=True)
        new_doc.submit()

        return {
            "success": True,
            "message": "Loan created successfully",
            "loan": new_doc.name,
            "status": new_doc.status,
        }
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
@ess_validate(methods=["POST"])
def disburse_loan(loan, disbursement_date, disbursed_amount=None):
    try:
        if not frappe.db.exists("Loan", loan):
            frappe.throw("Loan not found")

        loan_doc = frappe.get_doc("Loan", loan)

        if loan_doc.docstatus != 1:
            frappe.throw("Loan must be submitted (Sanctioned) before disbursement")

        if loan_doc.status == "Disbursed":
            frappe.throw("Loan is already fully disbursed")

        if frappe.db.exists("Loan Disbursement", {"against_loan": loan, "docstatus": 1}):
            frappe.throw("A disbursement already exists for this Loan")

        amount = disbursed_amount if disbursed_amount else loan_doc.loan_amount

        new_disbursement = frappe.get_doc(
            {
                "doctype": "Loan Disbursement",
                "against_loan": loan_doc.name,
                "applicant_type": loan_doc.applicant_type,
                "applicant": loan_doc.applicant,
                "company": loan_doc.company,
                "loan_product": loan_doc.loan_product,
                "is_term_loan": loan_doc.is_term_loan,
                "monthly_repayment_amount": loan_doc.monthly_repayment_amount,
                "disbursement_account": loan_doc.disbursement_account,
                "loan_account": loan_doc.loan_account,
                "disbursement_date": disbursement_date,
                "disbursed_amount": amount,
            }
        )
        new_disbursement.insert(ignore_permissions=True)
        new_disbursement.submit()

        return {
            "success": True,
            "message": "Loan disbursed successfully",
            "disbursement": new_disbursement.name,
            "disbursed_amount": amount,
        }
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_loan_admin_list():
    """
    Get all Loan records for admin monitoring across all employees.
    Returns list of Loan documents with key fields.
    """
    try:
        loans = frappe.get_all(
            "Loan",
            fields=[
                "name",
                "applicant",
                "applicant_name",
                "loan_product",
                "loan_amount",
                "disbursed_amount",
                "status",
                "monthly_repayment_amount",
                "total_payment",
                "total_principal_paid",
                "loan_application",
            ],
        )
        return loans
    except Exception as e:
        frappe.log_error()
        frappe.throw(str(e))
