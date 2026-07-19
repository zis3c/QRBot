import cv2
import numpy as np
from pyzbar.pyzbar import decode, ZBarSymbol
import html
from collections import Counter

def _decode_payload(data: bytes) -> str:
    """Decode QR payload bytes without turning non-UTF-8 QR data into failures."""
    for encoding in ("utf-8-sig", "utf-8", "shift_jis", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _clean_values(values):
    cleaned = []
    for value in values:
        if not value:
            continue
        normalized = value.strip()
        if normalized:
            cleaned.append(normalized)
    return cleaned


def _result_from_values(values):
    unique_values = []
    seen = set()
    for normalized in _clean_values(values):
        if normalized not in seen:
            seen.add(normalized)
            unique_values.append(normalized)

    if len(unique_values) == 1:
        return "success", unique_values[0]
    if len(unique_values) > 1:
        return "multiple", None
    return None, None


def read_qr(image_bytes):
    """
    Reads a QR code from image bytes using pyzbar (primary) and OpenCV (backup).
    Returns a tuple (status, data).
    Status: 'success', 'multiple', 'error', 'none'
    """
    try:
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        # Decode image
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return 'error', None

        candidates = []

        def remember(values):
            candidates.extend(_clean_values(values))

        def best_candidate():
            if not candidates:
                return None, None

            counts = Counter(candidates)
            best_value, best_count = counts.most_common(1)[0]
            if best_count >= 2 or len(counts) == 1:
                return "success", best_value
            return "multiple", None
            
        # Helper to process and detect with pyzbar
        def try_detect_pyzbar(image):
            decoded_objects = decode(image, symbols=[ZBarSymbol.QRCODE])
            if decoded_objects:
                values = [_decode_payload(obj.data) for obj in decoded_objects if obj.data]
                remember(values)
                return _result_from_values(values)
            return None, None

        detector = cv2.QRCodeDetector()

        def try_detect_opencv(image):
            values = []
            try:
                ok, decoded_info, _, _ = detector.detectAndDecodeMulti(image)
                if ok:
                    values.extend(decoded_info)
            except cv2.error:
                pass

            try:
                value, _, _ = detector.detectAndDecode(image)
                if value:
                    values.append(value)
            except cv2.error:
                pass

            remember(values)
            return _result_from_values(values)

        # 1. Try Original with pyzbar
        status, data = try_detect_pyzbar(img)
        if status == "success": return status, data
        status, data = try_detect_opencv(img)
        if status == "success": return status, data
        
        # 2. Try Grayscale with pyzbar
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        status, data = try_detect_pyzbar(gray)
        if status == "success": return status, data
        status, data = try_detect_opencv(gray)
        if status == "success": return status, data
        
        # 3. Try Thresholding (Otsu) with pyzbar
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        status, data = try_detect_pyzbar(thresh)
        if status == "success": return status, data
        status, data = try_detect_opencv(thresh)
        if status == "success": return status, data
        
        # 4. Try Resize (Upscale)
        for scale in (2.0, 3.0, 4.0):
            upscaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            status, data = try_detect_pyzbar(upscaled)
            if status == "success": return status, data
            status, data = try_detect_opencv(upscaled)
            if status == "success": return status, data

        # 5. Try denoise and sharpen for camera photos / screenshots
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        sharpened = cv2.addWeighted(denoised, 1.7, cv2.GaussianBlur(denoised, (0, 0), 1.2), -0.7, 0)
        status, data = try_detect_pyzbar(sharpened)
        if status == "success": return status, data
        status, data = try_detect_opencv(sharpened)
        if status == "success": return status, data

        # 6. Try Inverted (for white on black)
        inverted = cv2.bitwise_not(gray)
        status, data = try_detect_pyzbar(inverted)
        if status == "success": return status, data
        status, data = try_detect_opencv(inverted)
        if status == "success": return status, data

        status, data = best_candidate()
        if status: return status, data

        return 'none', None
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error reading QR: {e}")
        return 'error', None

def detect_type(content):
    """
    Detects the type of QR content.
    Returns: 'URL', 'WiFi', 'vCard', 'Text'
    """
    content = content.strip()
    
    if content.startswith(('http://', 'https://')):
        return 'URL'
        
    if content.startswith('WIFI:'):
        return 'WiFi'
        
    if 'BEGIN:VCARD' in content:
        return 'vCard'
        
    return 'Text'

import re

def parse_wifi_string(content):
    """
    Parses a WiFi QR string into a dictionary using regex.
    Handles special characters and unescaped delimiters.
    Format: WIFI:T:WPA;S:MySSID;P:password123;;
    """
    # Remove WIFI: prefix
    if content.startswith('WIFI:'):
        content = content[5:]
    
    # Regex to find fields. 
    # Looks for Tag:Value followed by either ;Tag: or ;; or end of string
    # Tags: S (SSID), T (Type), P (Password), H (Hidden)
    
    wifi_data = {'SSID': 'Unknown', 'Type': 'nopass', 'Password': ''}
    
    # Extract SSID
    ssid_match = re.search(r'S:(.*?)(?:;[TPH]:|;;|$)', content)
    if ssid_match:
        wifi_data['SSID'] = ssid_match.group(1)
        
    # Extract Type
    type_match = re.search(r'T:(.*?)(?:;[SPH]:|;;|$)', content)
    if type_match:
        wifi_data['Type'] = type_match.group(1)
        
    # Extract Password
    pass_match = re.search(r'P:(.*?)(?:;[STH]:|;;|$)', content)
    if pass_match:
        wifi_data['Password'] = pass_match.group(1)
            
    return wifi_data

def _escape_html_text(value: str, limit: int = 1500) -> str:
    """Escape untrusted text before rendering in HTML parse mode."""
    text = (value or "").strip()
    if len(text) > limit:
        text = text[:limit] + "... [truncated]"
    return html.escape(text)

def format_response(content, qr_type):
    """
    Formats the response string based on QR type.
    """
    response = ""
    safe_content = _escape_html_text(content)
    
    if qr_type == 'URL':
        response += "<b>Type:</b> URL 🌐\n"
        response += f"<b>Content:</b> <code>{safe_content}</code>\n"
        
    elif qr_type == 'WiFi':
        wifi_data = parse_wifi_string(content)
        ssid = _escape_html_text(wifi_data["SSID"])
        password = _escape_html_text(wifi_data["Password"])
        auth_type = _escape_html_text(wifi_data["Type"])
        response += "<b>Type:</b> WiFi Network 📶\n\n"
        response += "<b>Details:</b>\n"
        response += f"SSID: <code>{ssid}</code>\n"
        response += f"Password: <code>{password}</code>\n"
        response += f"Encryption: {auth_type}"
        
    elif qr_type == 'vCard':
        response += "<b>Type:</b> Contact Card 👤\n\n"
        
        # Robust regex extraction
        name_match = re.search(r'FN:(.*?)(?:\n|$)', content)
        phone_match = re.search(r'TEL.*?:(.*?)(?:\n|$)', content)
        email_match = re.search(r'EMAIL.*?:(.*?)(?:\n|$)', content)
        org_match = re.search(r'ORG:(.*?)(?:\n|$)', content)
        title_match = re.search(r'TITLE:(.*?)(?:\n|$)', content)
        
        name = name_match.group(1).strip() if name_match else "Unknown"
        phone = phone_match.group(1).strip() if phone_match else ""
        email = email_match.group(1).strip() if email_match else ""
        org = org_match.group(1).strip() if org_match else ""
        title = title_match.group(1).strip() if title_match else ""
        
        response += f"<b>Name:</b> {_escape_html_text(name)}\n"
        if title: response += f"<b>Title:</b> {_escape_html_text(title)}\n"
        if org: response += f"<b>Company:</b> {_escape_html_text(org)}\n"
        if phone: response += f"<b>Phone:</b> {_escape_html_text(phone)}\n"
        if email: response += f"<b>Email:</b> {_escape_html_text(email)}"
        
    else: # Text or Generic
        response += "<b>Type:</b> Text 📝\n"
        response += f"<b>Content:</b> <code>{safe_content}</code>"
        
    return response


def try_decrypt_sentinel(content, password):
    """
    Attempts to decrypt Sentinel QR content.
    Expects content to start with SENTINEL: (optional for backward compat if we wanted, but strictly enforcing for new flow).
    """
    try:
        if content.startswith("SENTINEL:"):
            content = content[9:]

        from cryptography.fernet import Fernet

        # New format: S2:<iterations>:<salt_b64>:<token>
        if content.startswith("S2:"):
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            import base64

            _, iter_str, salt_b64, token = content.split(":", 3)
            iterations = int(iter_str)
            salt = base64.urlsafe_b64decode(salt_b64.encode())

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=iterations,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            f = Fernet(key)
            return f.decrypt(token.encode()).decode()

        # Legacy format fallback: Fernet(SHA256(password))
        import hashlib
        import base64
        digest = hashlib.sha256(password.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
        f = Fernet(key)
        return f.decrypt(content.encode()).decode()
    except Exception:
        return None

def try_detect_and_decode(content: str):
    """
    Attempts to detect and decode Base64 or Hex content.
    Returns (format_name, decoded_text) or (None, None).
    """
    import base64
    import re
    import codecs
    
    content = content.strip()
    if not content:
        return None, None
        
    # Try Hex
    # Must be even length, only hex chars, and decode to utf-8 string
    if len(content) % 2 == 0 and len(content) > 4: # Min length heuristic
        if re.match(r'^[0-9a-fA-F]+$', content):
             try:
                 decoded = bytes.fromhex(content).decode('utf-8')
                 # Heuristic: is it printable?
                 if decoded.isprintable():
                     return 'Hex', decoded
             except:
                 pass
                 
    # Try Base64
    # B64 usually ends with = or ==, length % 4 == 0, and chars are A-Za-z0-9+/
    if len(content) % 4 == 0 and len(content) > 4:
        if re.match(r'^[A-Za-z0-9+/]+={0,2}$', content):
            try:
                decoded_bytes = base64.b64decode(content)
                decoded = decoded_bytes.decode('utf-8')
                if decoded.isprintable() and decoded != content:
                    return 'Base64', decoded
            except:
                pass

    # Try ROT13
    # We only apply it if the content looks like it has letters
    if any(c.isalpha() for c in content):
         try:
             decoded = codecs.decode(content, 'rot_13')
             # ROT13 is symmetric, so we just check if it's different and printable
             if decoded != content and decoded.isprintable():
                 # Heuristic: Vowel check to avoid false positives (e.g. "superidol" -> garbage)
                 # Only show if decoded text looks "more like text" (more vowels) than the input.
                 def count_vowels(s):
                     return sum(1 for c in s if c.lower() in 'aeiou')
                 
                 if count_vowels(decoded) > count_vowels(content):
                     return 'ROT13', decoded
         except:
             pass
                
    return None, None
