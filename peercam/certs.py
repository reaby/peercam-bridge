"""TLS certificate for the LAN (phone) listener.

Phones only allow camera access on HTTPS pages. By default a self-signed
certificate is generated, so each device accepts a warning once. To avoid the
warning, put a trusted certificate (e.g. from mkcert) in the cert dir as
``lan.pem`` / ``lan-key.pem`` and it is used instead.
"""

import datetime
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .log import get_logger

log = get_logger("certs")

CUSTOM_CERT, CUSTOM_KEY = "lan.pem", "lan-key.pem"
SELF_CERT, SELF_KEY = "selfsigned.pem", "selfsigned-key.pem"
VALID_DAYS = 397
RENEW_BEFORE = datetime.timedelta(days=14)


def ensure_certificate(cert_dir, ips):
    """Return (cert_path, key_path, is_custom), generating a self-signed cert
    when none exists, it is expiring, or it doesn't cover the current IPs."""
    cert_dir = Path(cert_dir)
    custom_cert, custom_key = cert_dir / CUSTOM_CERT, cert_dir / CUSTOM_KEY
    if custom_cert.is_file() and custom_key.is_file():
        return custom_cert, custom_key, True

    cert_path, key_path = cert_dir / SELF_CERT, cert_dir / SELF_KEY
    if not _is_usable(cert_path, key_path, ips):
        cert_dir.mkdir(parents=True, exist_ok=True)
        _generate(cert_path, key_path, ips)
        log.info("Generated self-signed certificate for %s", ", ".join(ips) or "localhost")
    return cert_path, key_path, False


def _is_usable(cert_path, key_path, ips):
    if not (cert_path.is_file() and key_path.is_file()):
        return False
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (ValueError, x509.ExtensionNotFound):
        return False
    covered = set(san.get_values_for_type(x509.IPAddress))
    wanted = {ipaddress.ip_address(ip) for ip in ips}
    remaining = cert.not_valid_after_utc - datetime.datetime.now(datetime.timezone.utc)
    return wanted <= covered and remaining > RENEW_BEFORE


def _generate(cert_path, key_path, ips):
    key = ec.generate_private_key(ec.SECP256R1())
    host = socket.gethostname()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"PeerCam Bridge ({host})")])
    alt_names = [
        x509.DNSName("localhost"),
        x509.DNSName(host),
        x509.DNSName(f"{host}.local"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ] + [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
