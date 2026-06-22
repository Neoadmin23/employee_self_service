import frappe

from employee_self_service.mobile.api_utils import (
    ess_validate,
    exception_handel,
    gen_response,
    get_employee_by_user,
)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_employee_documents():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")

        documents = frappe.get_all(
            "ESS Documents",
            filters={"employee_no": emp_data.get("name")},
            fields=[
                "name",
                "title",
                "attachement",
                "creation",
                "document_category",
                "document_type",
            ],
            order_by="creation desc",
        )

        if not documents:
            return gen_response(200, "No documents found.", [])

        for doc in documents:
            file_url = doc.get("attachement") or ""

            if file_url and not file_url.startswith("http"):
                file_url = f"{frappe.utils.get_url()}{file_url}"

            file_name = file_url.rsplit("/", 1)[-1] if file_url else ""

            if file_name and "." in file_name:
                file_extension = file_name.rsplit(".", 1)[-1].lower()
            else:
                file_extension = ""

            doc["document_name"] = doc.get("document_type")
            doc["file_url"] = file_url
            doc["file_name"] = file_name
            doc["file_extension"] = file_extension
            doc.pop("title", None)
            doc.pop("attachement", None)

        return gen_response(200, "Employee documents fetched successfully", documents)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_document_categories():
    try:
        categories = frappe.get_all(
            "Document Category",
            fields=["name", "category_name"],
            order_by="category_name asc",
        )

        if not categories:
            return gen_response(200, "No document categories found.", [])

        return gen_response(200, "Document categories fetched successfully", categories)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_document_types():
    try:
        document_category = frappe.form_dict.get("document_category")

        if not document_category:
            return gen_response(500, "document_category is required")

        if not frappe.db.exists("Document Category", document_category):
            return gen_response(500, "Invalid document category")

        document_types = frappe.get_all(
            "Document Type",
            filters={"document_category": document_category},
            fields=["name", "document_type_name"],
            order_by="document_type_name asc",
        )

        if not document_types:
            return gen_response(200, "No document types found.", [])

        return gen_response(200, "Document types fetched successfully", document_types)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def upload_employee_document():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return gen_response(500, "Employee does not exists")

        document_category = frappe.form_dict.get("document_category")
        document_type = frappe.form_dict.get("document_type")

        if not document_category:
            return gen_response(500, "document_category is required")
        if not document_type:
            return gen_response(500, "document_type is required")

        if not frappe.db.exists("Document Category", document_category):
            return gen_response(500, "Invalid document category")

        if not frappe.db.exists(
            "Document Type",
            {"document_type_name": document_type, "document_category": document_category},
        ):
            return gen_response(500, "Invalid document type for selected category")

        duplicate = frappe.db.exists(
            "ESS Documents",
            {"employee_no": emp_data.get("name"), "document_type": document_type},
        )
        if duplicate:
            return gen_response(500, f"{document_type} already uploaded for this employee")

        from frappe.handler import upload_file

        file_doc = upload_file()
        if not file_doc or not file_doc.file_url:
            return gen_response(500, "File upload failed")

        file_name = file_doc.file_name
        title = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

        try:
            ess_document = frappe.get_doc(
                {
                    "doctype": "ESS Documents",
                    "employee_no": emp_data.get("name"),
                    "title": title,
                    "document_category": document_category,
                    "document_type": document_type,
                }
            ).insert(ignore_permissions=True)

            file_doc.attached_to_doctype = "ESS Documents"
            file_doc.attached_to_name = ess_document.name
            file_doc.attached_to_field = "attachement"
            file_doc.save(ignore_permissions=True)

            ess_document.attachement = file_doc.file_url
            ess_document.save(ignore_permissions=True)

            file_url = file_doc.file_url
            if file_url and file_url.startswith("/"):
                file_url = f"{frappe.utils.get_url()}{file_url}"

            return gen_response(
                200,
                "Document uploaded successfully",
                {
                    "name": ess_document.name,
                    "document_category": document_category,
                    "document_type": document_type,
                    "document_name": document_type,
                    "file_url": file_url,
                },
            )
        except Exception as e:
            if file_doc and file_doc.name:
                frappe.delete_doc("File", file_doc.name, ignore_permissions=True)
            raise e

    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def download_employee_document():
    try:
        employee = get_employee_by_user(frappe.session.user)
        document_id = frappe.form_dict.get("document_id")

        if not document_id:
            return gen_response(500, "document_id is required")

        document = frappe.get_all(
            "ESS Documents",
            filters={"name": document_id, "employee_no": employee.name},
            fields=["name", "document_type"],
        )

        if not document:
            return gen_response(404, "Document not found.", [])

        document = document[0]

        file_doc = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "ESS Documents",
                "attached_to_name": document.name,
            },
            fields=["name", "file_name", "file_url"],
        )

        if not file_doc:
            return gen_response(404, "File not found.", [])

        file_doc = file_doc[0]

        file_url = file_doc.file_url
        if file_url and file_url.startswith("/"):
            file_url = f"{frappe.utils.get_url()}{file_url}"

        return gen_response(
            200,
            "File details fetched successfully",
            {
                "document_id": document.name,
                "document_name": document.document_type,
                "file_name": file_doc.file_name,
                "file_url": file_url,
            },
        )
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["POST"])
def delete_employee_document():
    try:
        employee = get_employee_by_user(frappe.session.user)
        document_id = frappe.form_dict.get("document_id")

        if not document_id:
            return gen_response(500, "document_id is required")

        document = frappe.get_all(
            "ESS Documents",
            filters={"name": document_id, "employee_no": employee.name},
            fields=["name"],
        )

        if not document:
            return gen_response(404, "Document not found.", [])

        document = document[0]

        file_docs = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "ESS Documents",
                "attached_to_name": document.name,
            },
            fields=["name"],
        )

        for file_doc in file_docs:
            frappe.delete_doc(
                "File",
                file_doc.name,
                ignore_permissions=True,
            )

        frappe.delete_doc("ESS Documents", document.name, ignore_permissions=True)
        frappe.db.commit()

        return gen_response(200, "Document deleted successfully", {})
    except Exception as e:
        return exception_handel(e)
