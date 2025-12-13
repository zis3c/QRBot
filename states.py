from aiogram.fsm.state import State, StatesGroup

class TextQRStates(StatesGroup):
    waiting_for_text = State()

class UrlQRStates(StatesGroup):
    waiting_for_url = State()

class WifiQRStates(StatesGroup):
    waiting_for_ssid = State()
    waiting_for_password = State()
    waiting_for_auth_type = State()

class VCardQRStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_email = State()

class EncodeQRStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_method = State()
    waiting_for_sentinel_password = State()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

class BanUserStates(StatesGroup):
    waiting_for_user_id = State()

class UnbanUserStates(StatesGroup):
    waiting_for_user_id = State()

class UnpenaltyUserStates(StatesGroup):
    waiting_for_user_id = State()

class GeoQRStates(StatesGroup):
    waiting_for_location = State()
    waiting_for_platform = State()


class ColorQRStates(StatesGroup):
    waiting_for_bg_choice = State()
    waiting_for_bg_custom = State()
    waiting_for_fg_choice = State()
    waiting_for_fg_custom = State()
    waiting_for_confirmation = State()

class QRReaderStates(StatesGroup):
    waiting_for_image = State()
    waiting_for_password = State()
