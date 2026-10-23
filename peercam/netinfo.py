import ipaddress
import socket


def lan_ips():
    """IPv4 addresses phones can reach, the default-route interface first."""
    ips = []
    primary = _primary_ip()
    if primary:
        ips.append(primary)
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        infos = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips and _usable(ip):
            ips.append(ip)
    return ips


def _primary_ip():
    # Connecting a UDP socket sends nothing; it just asks the OS which
    # interface would route outward.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return ip if _usable(ip) else None


def _usable(ip):
    addr = ipaddress.ip_address(ip)
    return not (addr.is_loopback or addr.is_link_local or addr.is_unspecified)
