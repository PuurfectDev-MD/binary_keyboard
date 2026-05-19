import board
import busio
import usb_hid
import time
import displayio
import terminalio
from adafruit_display_text import label
import adafruit_ssd1306
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

# ── I2C bus (shared by MCP23017 + SSD1306) ───────────────────────────
i2c = busio.I2C(scl=board.P1_15, sda=board.P1_13)

# ── OLED SSD1306 128x64 (default I2C address 0x3C) ───────────────────
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)

def oled_clear():
    oled.fill(0)

def oled_show(title, bits, value, char_preview, sent_history):
    """Render the full display layout."""
    oled.fill(0)

    # Row 0: static title (y=0)
    oled.text("BINARY KEYBOARD", 0, 0, 1)

    # Row 1: horizontal line separator (y=9)
    oled.hline(0, 9, 128, 1)

    # Row 2: bit pattern + decimal (y=13)
    bit_str = f"{value:08b}"           # e.g. "01000001"
    oled.text(f"{bit_str} ({value})", 0, 13, 1)

    # Row 3: mapped character preview (y=27)
    if char_preview:
        oled.text(f"-> '{char_preview}'", 0, 27, 1)
    else:
        oled.text("-> (no mapping)", 0, 27, 1)

    # Row 4: horizontal line separator (y=40)
    oled.hline(0, 40, 128, 1)

    # Row 5: last sent characters (y=44)
    history_str = "".join(sent_history[-14:])   # fit ~14 chars on width
    oled.text(f"Sent:{history_str}", 0, 44, 1)

    # Row 6: button hint (y=55)
    oled.text("B0=SND B1=ENT", 0, 55, 1)

    oled.show()


# ── MCP23017 (address 0x20, set by A0/A1/A2 all to GND) ──────────────
mcp = MCP23017(i2c, address=0x20)

# ── Port A: 8 binary toggle switches (GPA0–GPA7) ─────────────────────
switches = []
for pin_num in range(8):
    pin = mcp.get_pin(pin_num)
    pin.direction = Direction.INPUT
    pin.pull = Pull.UP
    switches.append(pin)

# ── Port B: action buttons (GPB0–GPB3 = MCP pins 8–11) ───────────────
BTN_SEND      = mcp.get_pin(8)     # GPB0 — send binary byte
BTN_ENTER     = mcp.get_pin(9)     # GPB1 — enter
BTN_BACKSPACE = mcp.get_pin(10)    # GPB2 — backspace
BTN_SPACE     = mcp.get_pin(11)    # GPB3 — space

for btn in [BTN_SEND, BTN_ENTER, BTN_BACKSPACE, BTN_SPACE]:
    btn.direction = Direction.INPUT
    btn.pull = Pull.UP

# ── USB HID Keyboard ──────────────────────────────────────────────────
kbd = Keyboard(usb_hid.devices)

# ── Sent history (rolling buffer of last 14 chars) ────────────────────
sent_history = []

# ── Character mapping ─────────────────────────────────────────────────
def char_to_keycode(char):
    if 'a' <= char <= 'z':
        return getattr(Keycode, char.upper()), False
    if 'A' <= char <= 'Z':
        return getattr(Keycode, char), True

    digit_map = {
        '0': (Keycode.ZERO, False),  '1': (Keycode.ONE, False),
        '2': (Keycode.TWO, False),   '3': (Keycode.THREE, False),
        '4': (Keycode.FOUR, False),  '5': (Keycode.FIVE, False),
        '6': (Keycode.SIX, False),   '7': (Keycode.SEVEN, False),
        '8': (Keycode.EIGHT, False), '9': (Keycode.NINE, False),
    }
    if char in digit_map:
        return digit_map[char]

    symbol_map = {
        ' ': (Keycode.SPACE, False),
        '\n': (Keycode.ENTER, False),
        '.': (Keycode.PERIOD, False),        ',': (Keycode.COMMA, False),
        '!': (Keycode.ONE, True),            '@': (Keycode.TWO, True),
        '#': (Keycode.THREE, True),          '$': (Keycode.FOUR, True),
        '%': (Keycode.FIVE, True),           '^': (Keycode.SIX, True),
        '&': (Keycode.SEVEN, True),          '*': (Keycode.EIGHT, True),
        '(': (Keycode.NINE, True),           ')': (Keycode.ZERO, True),
        '-': (Keycode.MINUS, False),         '_': (Keycode.MINUS, True),
        '=': (Keycode.EQUALS, False),        '+': (Keycode.EQUALS, True),
        '[': (Keycode.LEFT_BRACKET, False),  ']': (Keycode.RIGHT_BRACKET, False),
        '{': (Keycode.LEFT_BRACKET, True),   '}': (Keycode.RIGHT_BRACKET, True),
        ';': (Keycode.SEMICOLON, False),     ':': (Keycode.SEMICOLON, True),
        "'": (Keycode.QUOTE, False),         '"': (Keycode.QUOTE, True),
        '/': (Keycode.FORWARD_SLASH, False), '?': (Keycode.FORWARD_SLASH, True),
        '\\': (Keycode.BACKSLASH, False),    '|': (Keycode.BACKSLASH, True),
        '`': (Keycode.GRAVE_ACCENT, False),  '~': (Keycode.GRAVE_ACCENT, True),
        '<': (Keycode.COMMA, True),          '>': (Keycode.PERIOD, True),
    }
    return symbol_map.get(char, (None, False))


def byte_to_keycode(value):
    if 32 <= value <= 126:
        return char_to_keycode(chr(value))
    return None, False


def read_byte():
    value = 0
    for bit, switch in enumerate(switches):
        if not switch.value:
            value |= (1 << bit)
    return value


def send_key(keycode, shift=False):
    if shift:
        kbd.press(Keycode.LEFT_SHIFT, keycode)
    else:
        kbd.press(keycode)
    kbd.release_all()


def get_char_preview(value):
    """Return printable char string or None."""
    if 32 <= value <= 126:
        return chr(value)
    return None


# ── Startup splash ────────────────────────────────────────────────────
oled.fill(0)
oled.text("BINARY KEYBOARD", 10, 20, 1)
oled.text("   initializing...", 0, 36, 1)
oled.show()
time.sleep(1.5)

# ── Button state tracking ─────────────────────────────────────────────
last_send      = True
last_enter     = True
last_backspace = True
last_space     = True
last_byte      = -1         # track toggle changes for live OLED refresh

print("Binary keyboard ready.")

# ── Initial display render ────────────────────────────────────────────
current_byte = read_byte()
oled_show("BINARY KEYBOARD", f"{current_byte:08b}", current_byte,
          get_char_preview(current_byte), sent_history)

# ── Main loop ─────────────────────────────────────────────────────────
while True:
    s_send      = BTN_SEND.value
    s_enter     = BTN_ENTER.value
    s_backspace = BTN_BACKSPACE.value
    s_space     = BTN_SPACE.value

    current_byte = read_byte()

    # Refresh OLED only when toggle state changes (avoid constant redraw)
    if current_byte != last_byte:
        oled_show("BINARY KEYBOARD", f"{current_byte:08b}", current_byte,
                  get_char_preview(current_byte), sent_history)
        last_byte = current_byte

    # SEND — map byte → keycode → send
    if last_send and not s_send:
        char = get_char_preview(current_byte)
        print(f"SEND → {current_byte:08b} ({current_byte}) = '{char}'")
        keycode, needs_shift = byte_to_keycode(current_byte)
        if keycode is not None:
            send_key(keycode, needs_shift)
            sent_history.append(char)
        else:
            sent_history.append("?")
        # Keep history buffer trimmed
        if len(sent_history) > 14:
            sent_history.pop(0)
        oled_show("BINARY KEYBOARD", f"{current_byte:08b}", current_byte,
                  char, sent_history)
        time.sleep(0.05)

    # ENTER
    if last_enter and not s_enter:
        print("ENTER")
        send_key(Keycode.ENTER)
        sent_history.append("↵")
        if len(sent_history) > 14:
            sent_history.pop(0)
        oled_show("BINARY KEYBOARD", f"{current_byte:08b}", current_byte,
                  get_char_preview(current_byte), sent_history)
        time.sleep(0.05)

    # BACKSPACE
    if last_backspace and not s_backspace:
        print("BACKSPACE")
        send_key(Keycode.BACKSPACE)
        if sent_history:
            sent_history.pop()          # remove last sent char
        oled_show("BINARY KEYBOARD", f"{current_byte:08b}", current_byte,
                  get_char_preview(current_byte), sent_history)
        time.sleep(0.05)

    # SPACE
    if last_space and not s_space:
        print("SPACE")
        send_key(Keycode.SPACE)
        sent_history.append("_")        # visual space indicator
        if len(sent_history) > 14:
            sent_history.pop(0)
        oled_show("BINARY KEYBOARD", f"{current_byte:08b}", current_byte,
                  get_char_preview(current_byte), sent_history)
        time.sleep(0.05)

    last_send      = s_send
    last_enter     = s_enter
    last_backspace = s_backspace
    last_space     = s_space

    time.sleep(0.01)