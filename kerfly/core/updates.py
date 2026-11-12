"""
Is there a newer Kerfly? One request to GitHub's public list of releases
(the latest published release; tags without a release are skipped). Nothing
about the user or the work is sent: only the usual request with the program
name and version, so GitHub sees the computer's address, as with any page.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import json
import os
import re
import ssl
import urllib.request

LATEST_URL = "https://api.github.com/repos/cyryllo/Kerfly/releases/latest"
RELEASES_URL = "https://github.com/cyryllo/Kerfly/releases"
CHECK_EVERY_S = 24 * 3600            # at most once a day at start

# certificate bundles of the usual systems: the AppImage carries an OpenSSL built on Ubuntu,
# which looks for them only where Ubuntu keeps them
CA_FILES = ("/etc/ssl/certs/ca-certificates.crt",      # Debian, Ubuntu, Arch, Gentoo
            "/etc/pki/tls/certs/ca-bundle.crt",         # Fedora, RHEL
            "/etc/ssl/ca-bundle.pem",                   # openSUSE
            "/etc/ssl/cert.pem")                        # macOS, Alpine


class Release:
    def __init__(self, version, url, name=""):
        self.version = version           # "1.3.4"
        self.url = url                   # the release page
        self.name = name or "Kerfly " + version


def version_tuple(text):
    """'v1.3.10' -> (1, 3, 10); anything after the numbers is ignored."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", str(text).strip())
    if not m:
        raise ValueError("not a version: %r" % (text,))
    return tuple(int(p) for p in m.group(1).split("."))


def is_newer(candidate, current):
    a, b = version_tuple(candidate), version_tuple(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def parse_latest(data):
    """A Release from GitHub's JSON answer (dict), or None for a draft / pre-release."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    version_tuple(tag)                   # raises for something that is not a version
    return Release(tag.lstrip("v"), data.get("html_url") or RELEASES_URL, data.get("name") or "")


def _context():
    ctx = ssl.create_default_context()
    if not ctx.get_ca_certs():
        for path in CA_FILES:
            if os.path.isfile(path):
                ctx.load_verify_locations(cafile=path)
                break
    return ctx


def latest_release(current_version, timeout=6.0):
    """The latest published release, or raises OSError / ValueError (no internet,
    GitHub not answering, an unexpected answer)."""
    request = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Kerfly/%s (update check)" % current_version})
    with urllib.request.urlopen(request, timeout=timeout, context=_context()) as answer:
        data = json.loads(answer.read().decode("utf-8"))
    release = parse_latest(data)
    if release is None:
        raise ValueError("no published release")
    return release


def newer_release(current_version, skipped="", timeout=6.0, fetch=None):
    """The latest release if it is newer than this one and not skipped by the
    user, else None. fetch: replaces latest_release (tests)."""
    release = (fetch or latest_release)(current_version, timeout=timeout)
    if not is_newer(release.version, current_version):
        return None
    if skipped and not is_newer(release.version, skipped):
        return None
    return release
