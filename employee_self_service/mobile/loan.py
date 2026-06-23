import frappe
from frappe import _
from frappe.utils import today

from employee_self_service.mobile.api_utils import (
    ess_validate,
    exception_handel,
    gen_response,
    get_employee_by_user,
    validate_employee_data,
)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_loan_products():
    try:
        loan_products = frappe.get_all(
            "Loan Product",
            filters={"disabled": 0},
            fields=[
                "name",
                "loan_category",
                "is_term_loan",
                "rate_of_interest",
                "maximum_loan_amount",
            ],
        )
        return gen_response(
            200, "Loan Products retrieved successfully", loan_products
        )
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_my_loans():
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["name", "company"])
        if not emp_data:
            return gen_response(500, "Employee does not exist")
        validate_employee_data(emp_data)

        applications = frappe.get_all(
            "Loan Application",
            filters={
                "applicant_type": "Employee",
                "applicant": emp_data.get("name"),
            },
            fields=[
                "name",
                "loan_product",
                "loan_amount",
                "status",
                "posting_date",
                "repayment_periods",
                "repayment_amount",
            ],
        )

        loans = frappe.get_all(
            "Loan",
            filters={
                "applicant_type": "Employee",
                "applicant": emp_data.get("name"),
            },
            fields=[
                "name",
                "loan_product",
                "loan_amount",
                "disbursed_amount",
                "status",
                "total_payment",
                "total_principal_paid",
                "monthly_repayment_amount",
            ],
        )

        return gen_response(
            200, "Loans retrieved successfully", {"applications": applications, "loans": loans}
        )
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_loan_detail(loan):
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not emp_data:
            return gen_response(500, "Employee does not exist")

        loan_doc = frappe.get_doc("Loan", loan)

        if loan_doc.applicant != emp_data.get("name") or loan_doc.applicant_type != "Employee":
            raise frappe.PermissionError(
                _("You are not authorized to view this loan")
            )

        allowed_fields = [
            "name",
            "applicant",
            "applicant_name",
            "loan_product",
            "loan_category",
            "loan_amount",
            "status",
            "rate_of_interest",
            "is_term_loan",
            "repayment_method",
            "repayment_periods",
            "monthly_repayment_amount",
            "repayment_start_date",
            "disbursement_date",
            "disbursed_amount",
            "total_payment",
            "total_interest_payable",
            "total_principal_paid",
            "total_amount_paid",
            "closure_date",
            "days_past_due",
            "is_npa",
        ]

        loan_data = {field: loan_doc.get(field) for field in allowed_fields}

        return gen_response(
            200, "Loan detail retrieved successfully", loan_data
        )
    except frappe.PermissionError as e:
        return exception_handel(e)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_repayment_schedule(loan):
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not emp_data:
            return gen_response(500, "Employee does not exist")

        loan_doc = frappe.get_doc("Loan", loan)

        if loan_doc.applicant != emp_data.get("name") or loan_doc.applicant_type != "Employee":
            raise frappe.PermissionError(
                _("You are not authorized to view this loan schedule")
            )

        schedule_doc = frappe.get_all(
            "Loan Repayment Schedule",
            filters={"loan": loan, "docstatus": 1},
            fields=["name"],
            order_by="creation desc",
            limit=1,
        )
        if not schedule_doc:
            return gen_response(200, "No repayment schedule found", [])

        schedule = frappe.get_all(
            "Repayment Schedule",
            filters={"parent": schedule_doc[0]["name"]},
            fields=["payment_date","principal_amount","interest_amount","total_payment","balance_loan_amount","demand_generated"],
            order_by="idx asc",
        )

        return gen_response(
            200, "Repayment schedule retrieved successfully", schedule
        )
    except frappe.PermissionError as e:
        return exception_handel(e)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def apply_loan(loan_product, loan_amount, repayment_method, repayment_periods=None, repayment_amount=None, description=None):
    try:
        emp_data = get_employee_by_user(
            frappe.session.user, fields=["name", "company"]
        )
        if not emp_data:
            return gen_response(500, "Employee does not exist")
        validate_employee_data(emp_data)

        company = emp_data.get("company")

        loan_application = frappe.get_doc(
            {
                "doctype": "Loan Application",
                "applicant_type": "Employee",
                "applicant": emp_data.get("name"),
                "company": company,
                "posting_date": today(),
                "loan_product": loan_product,
                "loan_amount": loan_amount,
                "repayment_method": repayment_method,
                "description": description,
            }
        )

        if repayment_method == "Repay Over Number of Periods" and repayment_periods:
            loan_application.repayment_periods = repayment_periods
        if repayment_method == "Repay Fixed Amount per Period" and repayment_amount:
            loan_application.repayment_amount = repayment_amount

        loan_application.insert(ignore_permissions=True)

        return gen_response(
            200,
            "Loan application submitted successfully",
            {"name": loan_application.name, "status": loan_application.status},
        )
    except Exception as e:
        return exception_handel(e)
