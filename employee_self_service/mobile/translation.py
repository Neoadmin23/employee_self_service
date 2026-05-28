import json
import re

import frappe
from frappe import _

from employee_self_service.mobile.api_utils import (
    ess_validate,
    exception_handel,
    gen_response,
    get_ess_settings,
)


def _should_skip_translation(text: str) -> bool:
    """
    Check if text should be skipped from translation.
    Skip: numbers, emails, URLs, dates, empty strings.
    """
    if not text or not text.strip():
        return True
    
    # Skip numbers
    if text.replace(".", "").replace(",", "").replace("-", "").isdigit():
        return True
    
    # Skip emails
    if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", text):
        return True
    
    # Skip URLs
    if re.match(r"^https?://", text) or re.match(r"^www\.", text):
        return True
    
    # Skip dates (common formats)
    date_patterns = [
        r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
        r"^\d{2}/\d{2}/\d{4}$",  # DD/MM/YYYY
        r"^\d{2}-\d{2}-\d{4}$",  # DD-MM-YYYY
    ]
    for pattern in date_patterns:
        if re.match(pattern, text):
            return True
    
    return False


@frappe.whitelist(allow_guest=True)
def translate_dynamic_text(texts=None, target_language="ar"):
    """
    Translate dynamic text using Google Translate.
    
    Args:
        texts: List of strings to translate (can be JSON string or list)
        target_language: Target language code (default: "ar" for Arabic)
    
    Returns:
        list: List of objects with original and translated text
    """
    try:
        frappe.logger().info(f"Translation request received: {len(texts) if texts else 0} texts for {target_language}")
        
        # Parse incoming JSON string safely
        if isinstance(texts, str):
            try:
                texts = json.loads(texts)
            except Exception:
                texts = [texts]
        
        if not texts:
            return []
        
        # Import googletrans
        try:
            from googletrans import Translator
        except ImportError:
            frappe.log_error(frappe.get_traceback(), "googletrans package not installed")
            # Return original texts as fallback
            return [{"original": str(t), "translated": str(t)} for t in texts]
        
        translator = Translator()
        results = []
        
        for text in texts:
            try:
                # Type safety: ensure text is a string
                if not isinstance(text, str):
                    text = str(text) if text is not None else ""
                
                translated = translator.translate(
                    text,
                    dest=target_language
                )
                
                results.append({
                    "original": text,
                    "translated": translated.text
                })
                
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "Translation Item Error"
                )
                
                # Return original text as fallback
                results.append({
                    "original": text,
                    "translated": text
                })
        
        return results
    
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "translate_dynamic_text Error"
        )
        
        # Return original texts as fallback
        if texts:
            return [{"original": str(t), "translated": str(t)} for t in texts]
        return []


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_ess_language():
    try:
        ess_settings = get_ess_settings()
        data = []
        for row in ess_settings.get("ess_language"):
            data.append(
                dict(
                    language=row.get("language"),
                    direction=row.get("direction"),
                    language_name=row.get("language_name"),
                )
            )
        return gen_response(200, "Language Get Successfully", data)
    except Exception as e:
        return exception_handel(e)


@frappe.whitelist()
@ess_validate(methods=["GET"])
def get_translation(language):
    try:
        if not language:
            return gen_response(500, "Language is required.")

        ess_language_data = frappe.get_value(
            "ESS Language",
            {"language": language},
            ["language"],
            as_dict=1,
        )
        if not ess_language_data:
            return gen_response(500, "Invalid Language.")
        translation_doc = frappe.get_all(
            "Ess Translation",
            filters={"language": language},
            fields=["source_text", "translated_text"],
        )
        translation_data = {}
        for translation in translation_doc:
            translation_data[translation.get("source_text")] = translation.get(
                "translated_text"
            ) or translation.get("source_text")
        return gen_response(
            200,
            "Translation retrieved successfully",
            {
                "translation_data": translation_data,
            },
        )
    except Exception as e:
        return exception_handel(e)
