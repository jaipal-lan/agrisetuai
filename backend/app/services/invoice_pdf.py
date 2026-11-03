"""Tax-invoice / receipt PDF for a settled-or-in-progress order.

Pilot: fpdf2 core fonts are latin-1 only, so text is sanitised to latin-1 and
money is rendered as "Rs." (no unicode rupee sign). This is a commercial
document, not a statutory tax invoice — the disclaimer says so.
"""
from __future__ import annotations

from fpdf import FPDF


def _safe(s) -> str:
    return str(s if s is not None else "").encode("latin-1", "replace").decode("latin-1")


def _money(v) -> str:
    try:
        return f"Rs. {float(v):,.2f}"
    except (TypeError, ValueError):
        return "Rs. 0.00"


def build_invoice_pdf(*, order, buyer_name: str, seller_name: str,
                      commodity_name: str, paid: bool) -> bytes:
    q = order.quote or {}
    t = order.accepted_terms or {}

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(31, 122, 51)
    pdf.cell(0, 10, "AgriSetuAI", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, "Verified farm-to-market marketplace", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 14)
    title = "RECEIPT" if paid else "INVOICE"
    pdf.cell(0, 10, f"{title}  -  {_safe(order.public_id)}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    created = order.created_at.strftime("%d %b %Y, %H:%M") if getattr(order, "created_at", None) else ""
    pdf.cell(0, 6, f"Date: {_safe(created)}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Status: {_safe(order.status)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Parties
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(95, 6, "Seller (farmer)", new_x="RIGHT", new_y="TOP")
    pdf.cell(0, 6, "Buyer", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 6, _safe(seller_name or "-"), new_x="RIGHT", new_y="TOP")
    pdf.cell(0, 6, _safe(buyer_name or "-"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Line item
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(235, 243, 235)
    pdf.cell(80, 8, "Item", border=1, fill=True)
    pdf.cell(35, 8, "Quantity", border=1, fill=True, align="R")
    pdf.cell(35, 8, "Price/unit", border=1, fill=True, align="R")
    pdf.cell(0, 8, "Amount", border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    qty = t.get("quantity", 0)
    unit = t.get("unit", "kg")
    ppu = t.get("price_per_unit", 0)
    pdf.cell(80, 8, _safe(commodity_name or "Produce"), border=1)
    pdf.cell(35, 8, f"{_safe(qty)} {_safe(unit)}", border=1, align="R")
    pdf.cell(35, 8, _money(ppu), border=1, align="R")
    pdf.cell(0, 8, _money(q.get("product_value", 0)), border=1, align="R",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Charge breakdown
    def row(label, value, bold=False, big=False):
        pdf.set_font("Helvetica", "B" if bold else "", 12 if big else 10)
        pdf.cell(150, 7, _safe(label), align="R")
        pdf.cell(0, 7, _money(value), align="R", new_x="LMARGIN", new_y="NEXT")

    row("Product value", q.get("product_value", 0))
    if float(q.get("packing_fee", 0) or 0):
        row("Packing", q.get("packing_fee", 0))
    if float(q.get("inspection_fee", 0) or 0):
        row("Inspection", q.get("inspection_fee", 0))
    if float(q.get("transport_charge", 0) or 0):
        row("Transport", q.get("transport_charge", 0))
    if float(q.get("service_fee", 0) or 0):
        row("Service fee", q.get("service_fee", 0))
    if float(q.get("tax", 0) or 0):
        row("Tax", q.get("tax", 0))
    pdf.ln(1)
    row("Buyer pays", q.get("buyer_total", order.buyer_total or 0), bold=True, big=True)

    pdf.ln(3)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    if q.get("seller_commission") is not None:
        pct = q.get("seller_commission_pct", "")
        pdf.cell(150, 6, f"Seller commission ({_safe(pct)}%)", align="R")
        pdf.cell(0, 6, "- " + _money(q.get("seller_commission", 0)), align="R",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.cell(150, 6, "Seller receives", align="R")
    pdf.cell(0, 6, _money(q.get("seller_payable", order.seller_payable or 0)), align="R",
             new_x="LMARGIN", new_y="NEXT")

    # Footer / disclaimer
    pdf.ln(8)
    pdf.set_text_color(120, 120, 120)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4,
        _safe("This is a system-generated commercial document for the above AgriSetuAI "
              "trade and is not a statutory tax invoice. Quality figures, where shown, "
              "reflect field inspection, not laboratory testing. Amounts in INR."))
    return bytes(pdf.output())
