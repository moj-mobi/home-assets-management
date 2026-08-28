from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont


PRINTERS = {
    "b21": {"name": "NIIMBOT B21", "dpi": 203},
    "b21pro": {"name": "NIIMBOT B21 Pro", "dpi": 300},
    "m2": {"name": "NIIMBOT M2", "dpi": 300},
}
LABEL_SIZES = {"50x30": (50, 30), "40x30": (40, 30), "50x20": (50, 20)}


def qr_payload(name: str, inventory_number: str) -> str:
    return f"Naziv: {name}\nInventarna št.: {inventory_number}"


def qr_png(name: str, inventory_number: str) -> bytes:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(qr_payload(name, inventory_number)); qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO(); image.save(output, format="PNG"); return output.getvalue()


def label_png(name: str, inventory_number: str, printer: str, size: str) -> bytes:
    spec = PRINTERS.get(printer, PRINTERS["b21pro"])
    width_mm, height_mm = LABEL_SIZES.get(size, LABEL_SIZES["50x30"])
    px_per_mm = spec["dpi"] / 25.4
    width, height = round(width_mm * px_per_mm), round(height_mm * px_per_mm)
    image = Image.new("1", (width, height), 1); draw = ImageDraw.Draw(image)
    margin = max(8, round(1.5 * px_per_mm)); qr_side = height - 2 * margin
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(qr_payload(name, inventory_number)); qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white").convert("1").resize((qr_side, qr_side), Image.Resampling.NEAREST)
    image.paste(qr_image, (margin, margin))
    text_x, text_width = margin + qr_side + margin, width - (margin + qr_side + 2 * margin)
    title_font = ImageFont.load_default(size=max(12, round(2.8 * px_per_mm)))
    number_font = ImageFont.load_default(size=max(11, round(2.4 * px_per_mm)))
    footer_font = ImageFont.load_default(size=max(8, round(1.7 * px_per_mm)))

    def fit_text(value, font, max_width):
        if draw.textlength(value, font=font) <= max_width: return value
        shortened = value
        while shortened and draw.textlength(shortened + "…", font=font) > max_width: shortened = shortened[:-1]
        return shortened + "…"

    draw.text((text_x, margin), fit_text(name, title_font, text_width), fill=0, font=title_font)
    number_y = margin + max(18, round(5 * px_per_mm))
    draw.text((text_x, number_y), fit_text(inventory_number, number_font, text_width), fill=0, font=number_font)
    footer = f"HAM · {spec['name']} · {width_mm}×{height_mm} mm"
    draw.text((text_x, height - margin - max(10, round(2 * px_per_mm))), fit_text(footer, footer_font, text_width), fill=0, font=footer_font)
    output = BytesIO(); image.save(output, format="PNG", dpi=(spec["dpi"], spec["dpi"])); return output.getvalue()
