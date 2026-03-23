from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pathlib import Path

def generate_invoice(data: dict):
    invoices_dir = Path("invoices")
    invoices_dir.mkdir(exist_ok=True)

    file_path = invoices_dir / f"invoice_{data['invoice_id']}.pdf"

    c = canvas.Canvas(str(file_path), pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 50, "BOT DEPLOYMENT INVOICE")

    c.setFont("Helvetica", 11)
    y = h - 100

    for k, v in data.items():
        c.drawString(50, y, f"{k}: {v}")
        y -= 18

    c.showPage()
    c.save()
    return file_path
