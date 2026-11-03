"""
Translations (gettext).

Usage in any module:
    from kerfly.i18n import _, N_, C_
    label = _("Vector cut")          # translated now
    NAMES = [N_("Vector cut")]       # marked for extraction, translate later with _()
    short = C_("toolbar", "Reload")  # translated in a context (may use a line break)

Translation files: kerfly/locale/<lang>/LC_MESSAGES/kerfly.po (+ compiled .mo).
To update them after changing strings, run:  python tools/i18n.py

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import gettext
import locale
import os
import re

DOMAIN = "kerfly"
LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")

# code -> name shown in the language list (in that language)
LANGUAGES = {
    "en": "English",
    "pl": "Polski",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
}

_translation = gettext.NullTranslations()
_current = "en"


def _(message):
    return _translation.gettext(message)


def ngettext(singular, plural, n):
    return _translation.ngettext(singular, plural, n)


def C_(context, message):
    """Translate a message in a context (e.g. short toolbar labels), so it can
    be translated differently from the same English text elsewhere."""
    return _translation.pgettext(context, message)


def N_(message):
    """Mark a string for translation without translating it yet."""
    return message


def system_language():
    """Two-letter code of the system language if Kerfly has it, else 'en'."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            code = value.split(":")[0][:2].lower()
            return code if code in LANGUAGES else "en"
    try:
        code = (locale.getlocale()[0] or "en")[:2].lower()
    except ValueError:
        code = "en"
    return code if code in LANGUAGES else "en"


def setup(language=""):
    """Activate a language ('' = system language). Returns the code used."""
    global _translation, _current
    code = language if language in LANGUAGES else system_language()
    _translation = gettext.translation(DOMAIN, LOCALE_DIR, languages=[code], fallback=True)
    _current = code
    return code


def current_language():
    return _current


# Progress and error messages produced by the unchanged K40 Whisperer laser
# modules (nano_library, egv, svg_reader). They are translated when shown.
_UPSTREAM_PATTERNS = [
    (re.compile(r"^Sending Data to Laser = ([\d.]+)%$"), N_("Sending data to laser: %s%%")),
    (re.compile(r"^Calculating CRC data and Generate Packets: ([\d.]+)%$"), N_("Preparing USB data: %s%%")),
    (re.compile(r"^Generating EGV Data: ([\d.]+)%$"), N_("Generating laser data: %s%%")),
    (re.compile(r"^Preprocessing Raster Data: ([\d.]+)%$"), N_("Preprocessing raster data: %s%%")),
    (re.compile(r"^Creating Scan Lines: ([\d.]+) %$"), N_("Creating scan lines: %s%%")),
    (re.compile(r"^Adjusting Image Darkness: ([\d.]+) %$"), N_("Adjusting image darkness: %s%%")),
    (re.compile(r"^USB Timeout #(\d+)$"), N_("USB timeout #%s")),
    (re.compile(r"^Data transmission \(CRC\) error #(\d+)$"), N_("Data transmission (CRC) error #%s")),
    (re.compile(r"^The laser cutter is not responding \((\d+) attempts\)\. Press stop to stop trying!$"),
     N_("The laser cutter is not responding (%s attempts). Press Stop to stop trying.")),
    (re.compile(r"^There are many data transmission errors \((\d+)\)\. Press stop to stop trying!$"),
     N_("There are many data transmission errors (%s). Press Stop to stop trying.")),
]
_UPSTREAM_EXACT = {
    "CRC data and Packets are Ready": N_("USB data ready"),
    "Waiting for the laser to finish.": N_("Waiting for the laser to finish."),
    "Laser stopped responding after operation was complete.":
        N_("The laser stopped responding after the job was complete."),
    "Action Stopped by User.": N_("Stopped by the user."),
    "Action stopped by User.": N_("Stopped by the user."),
    "Converting TEXT to PATHS.": N_("Converting text to paths."),
    "Creating Halftone Image.": N_("Creating halftone image."),
    "Generating EGV data...": N_("Generating laser data…"),
    "Vector Cut: Determining Cut Order....": N_("Vector cut: determining cut order…"),
    "Vector Engrave: Determining Cut Order....": N_("Vector engrave: determining order…"),
    "No laser data was generated.": N_("No laser data was generated."),
}


def tr_message(message):
    """Translate a message that may come from the K40 Whisperer laser modules."""
    if not message:
        return message
    exact = _UPSTREAM_EXACT.get(message)
    if exact is not None:
        return _(exact)
    for pattern, template in _UPSTREAM_PATTERNS:
        m = pattern.match(message)
        if m:
            return _(template) % m.group(1)
    return _(message)
