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


@frappe.whitelist()
@ess_validate(methods=["POST"])
def translate_dynamic_text(texts, target_lang="ar"):
    """
    Translate dynamic text using Google Translate.
    
    Args:
        texts: List of strings to translate
        target_lang: Target language code (default: "ar" for Arabic)
    
    Returns:
        dict: Key-value format with original text as key and translated text as value
    """
    try:
        frappe.logger().info(f"Translation request received: {len(texts) if texts else 0} texts for {target_lang}")
        
        # Normalize incoming texts parameter
        if isinstance(texts, str):
            try:
                texts = json.loads(texts)
            except Exception:
                texts = [texts]
        
        if not texts:
            return gen_response(200, "Translation completed", {})
        
        # Remove duplicate texts
        texts = list(set(texts))
        
        # Import googletrans
        try:
            from googletrans import Translator
        except ImportError:
            frappe.logger().error("googletrans package not installed")
            return gen_response(500, "Translation service not available")
        
        translator = Translator()
        result = {}
        cache_hits = 0
        translated_count = 0
        skipped_count = 0
        failed_count = 0
        
        for text in texts:
            # Type safety: skip non-string values
            if not isinstance(text, str):
                text = str(text) if text is not None else ""
            
            if _should_skip_translation(text):
                result[text] = text
                skipped_count += 1
                continue
            
            # Long text protection
            if len(text) > 3000:
                result[text] = text
                skipped_count += 1
                continue
            
            # Check cache
            cache_key = f"translation:{target_lang}:{text}"
            cached_translation = frappe.cache().get_value(cache_key)
            
            if cached_translation:
                result[text] = cached_translation
                cache_hits += 1
                continue
            
            # Translate
            try:
                translation = translator.translate(text, dest=target_lang)
                translated_text = translation.text
                result[text] = translated_text
                
                # Cache the translation with 30 days expiry
                frappe.cache().set_value(
                    cache_key,
                    translated_text,
                    expires_in_sec=86400 * 30
                )
                translated_count += 1
            except Exception as e:
                frappe.logger().error(f"Translation failed for '{text}': {str(e)}")
                result[text] = text
                failed_count += 1
        
        frappe.logger().info(
            f"Translation completed: translated={translated_count}, cached={cache_hits}, "
            f"skipped={skipped_count}, failed={failed_count}"
        )
        
        return gen_response(200, "Translation completed", result)
    
    except Exception as e:
        frappe.logger().error(f"Translation API error: {str(e)}")
        return exception_handel(e)


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
