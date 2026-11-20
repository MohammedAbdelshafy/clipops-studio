"""Strict origin construction for account-gated Google Cloud Shell preview.

Only the HTTPS hostname published by Cloud Shell is accepted. The Studio
itself continues to bind exclusively to loopback and retains cookie/CSRF gates.
"""
from __future__ import annotations
import re
from urllib.parse import urlsplit

_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')


def cloud_shell_origin(port: int, web_host: str) -> str:
    if type(port) is not int or not 2000 <= port <= 65000:
        raise ValueError('Cloud Shell preview port must be between 2000 and 65000')
    if not isinstance(web_host, str) or not 1 <= len(web_host) <= 220:
        raise ValueError('Cloud Shell WEB_HOST is missing or invalid')
    labels = web_host.split('.')
    if len(labels) < 3 or labels[-2:] != ['cloudshell', 'dev'] or any(not _LABEL.fullmatch(x) for x in labels):
        raise ValueError('WEB_HOST must be the exact *.cloudshell.dev hostname issued by Cloud Shell')
    return f'https://{port}-{web_host}'

def tailnet_origin(host: str) -> str:
    """Allow the exact private MagicDNS HTTPS hostname issued by Tailscale Serve."""
    if not isinstance(host, str) or not 1 <= len(host) <= 253 or not host.isascii():
        raise ValueError('Enter the exact device.tailnet.ts.net hostname')
    labels = host.split('.')
    if len(labels) != 4 or labels[-2:] != ['ts', 'net'] or any(not _LABEL.fullmatch(x) for x in labels):
        raise ValueError('Expected device.tailnet.ts.net, without URL, credentials, paths or ports')
    return f'https://{host}'


def tailnet_login(user: str) -> str:
    """Validate a single trusted owner identity from Tailscale-User-Login."""
    if not isinstance(user, str) or not 3 <= len(user) <= 254 or not user.isascii():
        raise ValueError('A Tailscale owner login is required')
    if user.count('@') != 1 or re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', user) is None:
        raise ValueError('Enter one exact Tailscale owner login, for example user@example.com')
    return user.lower()


def devtunnel_origin(url: str) -> str:
    """Validate Microsoft's private, browser-friendly dev tunnel HTTPS URL.

    Only the no-port HTTPS hostname (id-8765.region.devtunnels.ms) is
    supported, not inspection endpoints, URL tokens or arbitrary hosts.
    This validates syntax, NOT the user's access-control policy.
    """
    if not isinstance(url, str) or not 14 <= len(url) <= 253 or not url.isascii() or url != url.strip():
        raise ValueError('Enter the exact private Dev Tunnels HTTPS URL')
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError:
        raise ValueError('Invalid Dev Tunnels URL') from None
    if (parsed.scheme != 'https' or not hostname or parsed.netloc != hostname
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Use only a clean HTTPS Dev Tunnels hostname with no path, port or credentials')
    labels = hostname.split('.')
    if (len(labels) != 4 or labels[-2:] != ['devtunnels', 'ms']
            or not all(_LABEL.fullmatch(x) for x in labels)):
        raise ValueError('Expected id-8765.region.devtunnels.ms HTTPS hostname')
    name, region = labels[0], labels[1]
    match = re.fullmatch(r'([a-z0-9][a-z0-9-]{1,55})-([0-9]{4,5})', name)
    if not match or not 2000 <= int(match.group(2)) <= 65000 or name.endswith('-inspect'):
        raise ValueError('Use the actual port-forward URL (not the Dev Tunnel inspector)')
    return f'https://{hostname}'
