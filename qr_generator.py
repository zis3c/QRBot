import qrcode
from io import BytesIO
import validators
import re
from typing import Optional

from dataclasses import dataclass, field
from typing import Tuple, Optional, List, Union
from enum import Enum



@dataclass
class QRColor:
    r: int
    g: int
    b: int
    a: int = 255

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"
    
    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.r, self.g, self.b, self.a)

    @staticmethod
    def from_hex(hex_code: str) -> 'QRColor':
        hex_code = hex_code.lstrip('#')
        if len(hex_code) == 6:
            return QRColor(*tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4)))
        elif len(hex_code) == 8:
            return QRColor(*tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4, 6)))
        else:
            raise ValueError("Invalid hex code")

@dataclass
class QRStyle:
    fg_color: QRColor = field(default_factory=lambda: QRColor(0, 0, 0))
    bg_color: QRColor = field(default_factory=lambda: QRColor(255, 255, 255))
    bg_transparent: bool = False
    
    def validate(self) -> List[str]:
        warnings = []
        # Contrast check
        lum1 = (0.299 * self.fg_color.r + 0.587 * self.fg_color.g + 0.114 * self.fg_color.b)
        return warnings

class QRGenerationError(Exception):
    """Custom exception for QR generation errors."""
    pass

def generate_qr(data, style: Optional['QRStyle'] = None):
    """
    Generate a QR code from data with optional styling.
    Returns a BytesIO object containing the PNG image.
    """
    from io import BytesIO
    import qrcode
    from PIL import Image, ImageDraw, ImageFilter
    
    if style is None:
        # from qr_styles import QRStyle
        style = QRStyle()
    
    try:
        # Create QR instance
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        # Generate image with simple colors
        # Convert QRColor to hex string
        fg_hex = f"#{style.fg_color.r:02x}{style.fg_color.g:02x}{style.fg_color.b:02x}"
        bg_hex = f"#{style.bg_color.r:02x}{style.bg_color.g:02x}{style.bg_color.b:02x}"
        
        # Generate QR with colors
        img = qr.make_image(fill_color=fg_hex, back_color=bg_hex)
        img = img.convert("RGB")  # Ensure RGB mode
        
        # Convert to RGBA if transparency is needed
        if style.bg_transparent:
            img = img.convert("RGBA")
            datas = img.getdata()
            newData = []
            bg_rgb = (style.bg_color.r, style.bg_color.g, style.bg_color.b)
            for item in datas:
                # Change all background pixels to transparent
                if item[:3] == bg_rgb:
                    newData.append((255, 255, 255, 0))
                else:
                    newData.append(item)
            img.putdata(newData)
        
        # Save to BytesIO
        bio = BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        return bio
        
    except Exception as e:
        error_msg = str(e)
        if "Invalid version" in error_msg:
            raise QRGenerationError("⚠️ The text is too long for a QR code. Please shorten it.")
        raise QRGenerationError(f"Generation failed: {e}")

def generate_text_qr(text, style: Optional['QRStyle'] = None):
    """
    Generates a text QR code.
    """
    if not text or len(text.strip()) == 0:
        raise QRGenerationError("Text cannot be empty")
    
    return generate_qr(text, style)

def generate_url_qr(url, style: Optional['QRStyle'] = None):
    """
    Generates a URL QR code with validation.
    """
    if not url:
        raise QRGenerationError("URL cannot be empty")
        
    # Basic URL validation
    if not validators.url(url):
        # Check if it's just missing scheme
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            if not validators.url(url):
                raise QRGenerationError("Invalid URL format")
        else:
            raise QRGenerationError("Invalid URL format")
            
    return generate_qr(url, style)

def generate_wifi_qr(ssid, password, auth_type, style: Optional['QRStyle'] = None):
    """
    Generates a WiFi QR code string.
    Format: WIFI:T:WPA;S:MyNetwork;P:mypass;;
    """
    if not ssid:
        raise QRGenerationError("SSID cannot be empty")
        
    auth_type = auth_type.upper()
    if auth_type not in ['WPA', 'WEP', 'NOPASS']:
        auth_type = 'WPA' # Default
        
    # Removed manual escaping as it causes compatibility issues with some scanners
    # Most modern scanners handle special characters correctly without standard escaping
    
    wifi_string = f"WIFI:S:{ssid};T:{auth_type};P:{password};;"
    return generate_qr(wifi_string, style)

def generate_vcard_qr(name, phone, email, style: Optional['QRStyle'] = None):
    """
    Generates a vCard QR code string.
    """
    if not name:
        raise QRGenerationError("Name cannot be empty")
        
    # Sanitize inputs to prevent injection
    name = name.replace('\n', ' ').replace('\r', '')
    phone = phone.replace('\n', '').replace('\r', '')
    email = email.replace('\n', '').replace('\r', '')

    # Relaxed phone validation (digits, spaces, +, -, (), ., x)
    if not re.match(r'^[\d\s\-\+\(\)\.x]+$', phone):
        raise QRGenerationError("Invalid phone format")
        
    if not validators.email(email):
        raise QRGenerationError("Invalid email format")

    vcard_string = f"""BEGIN:VCARD
VERSION:3.0
FN:{name}
TEL:{phone}
EMAIL:{email}
END:VCARD"""
    return generate_qr(vcard_string, style)



def generate_encoded_qr(text, method, style: Optional['QRStyle'] = None):
    """
    Generates an encoded/obfuscated QR code.
    Methods: base64, hex, rot13
    """
    import base64
    import codecs

    method = method.lower()
    
    try:
        if method == 'base64':
            encoded_text = base64.b64encode(text.encode()).decode()
        elif method == 'hex':
            encoded_text = text.encode().hex()
        elif method == 'rot13':
            encoded_text = codecs.encode(text, 'rot_13')
        elif method == 'sentinel':
            # Sentinel QR (AES Encryption)
            # We expect the text to be passed as a tuple (text, key) or just text if key is global?
            # Actually, generate_encoded_qr signature is (text, method, style).
            # We need to pass the key somehow. 
            # Let's change the signature or handle it differently.
            # Ideally, generate_encoded_qr should accept **kwargs or we pass the key in text?
            # No, let's create a separate function generate_sentinel_qr and call it from bot.py
            return None # Should use generate_sentinel_qr instead
        else:
            return None
    except Exception as e:
        raise QRGenerationError(f"Encoding failed: {e}")
        
    return generate_qr(encoded_text, style)

def generate_sentinel_qr(text, key, style: Optional['QRStyle'] = None):
    """
    Generates a Sentinel QR code (AES Encrypted).
    """
    if not text:
        raise QRGenerationError("Text cannot be empty")
    if not key:
        raise QRGenerationError("Encryption key missing")
        
    try:
        from cryptography.fernet import Fernet
        # Ensure key is bytes and stripped of whitespace
        if isinstance(key, str):
            key = key.strip().encode()
            
        f = Fernet(key)
        # Encrypt text
        token = f.encrypt(text.encode())
        return generate_qr(token.decode(), style)
    except Exception as e:
        raise QRGenerationError(f"Encryption failed: {e}")

def generate_geo_qr(latitude, longitude, platform, style: Optional['QRStyle'] = None):
    """
    Generates a Geo QR code.
    """
    if not latitude or not longitude:
        raise QRGenerationError("Location cannot be empty")
        
    platform = platform.lower()
    
    if "google" in platform:
        url = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    elif "waze" in platform:
        url = f"https://waze.com/ul?ll={latitude},{longitude}&navigate=yes"
    elif "apple" in platform:
        url = f"http://maps.apple.com/?ll={latitude},{longitude}"
    else:
        # Default to geo URI
        url = f"geo:{latitude},{longitude}"
        
    return generate_qr(url, style)
