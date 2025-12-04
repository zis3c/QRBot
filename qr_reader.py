import cv2
import numpy as np
from pyzbar.pyzbar import decode, ZBarSymbol

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
            
        # Helper to process and detect with pyzbar
        def try_detect_pyzbar(image):
            decoded_objects = decode(image, symbols=[ZBarSymbol.QRCODE])
            if decoded_objects:
                valid_codes = [obj.data.decode('utf-8') for obj in decoded_objects if obj.data]
                if len(valid_codes) > 1: return 'multiple', None
                elif len(valid_codes) == 1: return 'success', valid_codes[0]
            return None, None

        # 1. Try Original with pyzbar
        status, data = try_detect_pyzbar(img)
        if status: return status, data
        
        # 2. Try Grayscale with pyzbar
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        status, data = try_detect_pyzbar(gray)
        if status: return status, data
        
        # 3. Try Thresholding (Otsu) with pyzbar
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        status, data = try_detect_pyzbar(thresh)
        if status: return status, data
        
        # 4. Try Resize (Upscale) with pyzbar
        upscaled = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        status, data = try_detect_pyzbar(upscaled)
        if status: return status, data

        # 5. Try Inverted (for white on black)
        inverted = cv2.bitwise_not(gray)
        status, data = try_detect_pyzbar(inverted)
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

def format_response(content, qr_type):
    """
    Formats the response string based on QR type.
    """
    response = f"🔍 *QR Code Detected*\n\n"
    
    if qr_type == 'URL':
        response += f"*Type:* URL 🌐\n"
        response += f"*Content:* {content}\n\n"
        response += f"Suggested Action: Open the link."
        
    elif qr_type == 'WiFi':
        wifi_data = parse_wifi_string(content)
        response += f"*Type:* WiFi Network 📶\n\n"
        response += f"*Details:*\n"
        response += f"SSID: `{wifi_data['SSID']}`\n"
        response += f"Password: `{wifi_data['Password']}`\n"
        response += f"Encryption: {wifi_data['Type']}\n\n"
        response += f"Suggested Action: Connect manually."
        
    elif qr_type == 'vCard':
        response += f"*Type:* Contact Card 👤\n\n"
        
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
        
        response += f"*Name:* {name}\n"
        if title: response += f"*Title:* {title}\n"
        if org: response += f"*Company:* {org}\n"
        if phone: response += f"*Phone:* {phone}\n"
        if email: response += f"*Email:* {email}\n\n"
        response += f"Suggested Action: Save contact manually."
        
    else: # Text or Generic
        response += f"*Type:* Text 📝\n"
        response += f"*Content:* {content}\n\n"
        response += f"Suggested Action: Read content."
        
    return response

def try_decrypt_sentinel(content, key):
    """
    Attempts to decrypt Sentinel QR content.
    Returns decrypted text or None.
    """
    try:
        from cryptography.fernet import Fernet
        if isinstance(key, str):
            key = key.strip().encode()
            
        f = Fernet(key)
        decrypted = f.decrypt(content.encode()).decode()
        return decrypted
    except:
        return None
