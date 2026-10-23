import io

import segno


def qr_svg(url):
    """Standalone SVG (usable as an <img> source) encoding ``url``."""
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=8, border=2, xmldecl=False)
    return buf.getvalue()
