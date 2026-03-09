#!/usr/bin/env python3
"""
API REST para el dashboard de gastos.
Usa PostgreSQL (Railway) como base de datos.
"""

import os
import io
import psycopg2
import psycopg2.extras
from datetime import date
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ─── Rutas ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/api/gastos")
def gastos():
    mes = request.args.get("mes") or date.today().strftime("%Y-%m")
    anio, m = mes.split("-")

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT TO_CHAR(fecha, 'YYYY-MM-DD') as fecha, categoria, descripcion, CAST(monto AS FLOAT) as monto
        FROM gastos
        WHERE EXTRACT(YEAR FROM fecha) = %s AND EXTRACT(MONTH FROM fecha) = %s
        ORDER BY fecha DESC, created_at DESC
    """, (anio, m))
    rows = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT categoria, CAST(SUM(monto) AS FLOAT) as total
        FROM gastos
        WHERE EXTRACT(YEAR FROM fecha) = %s AND EXTRACT(MONTH FROM fecha) = %s
        GROUP BY categoria ORDER BY total DESC
    """, (anio, m))
    por_cat = {r["categoria"]: r["total"] for r in cur.fetchall()}

    total = sum(r["monto"] for r in rows)
    conn.close()

    return jsonify({"mes": mes, "gastos": rows, "por_categoria": por_cat, "total": total})

@app.route("/api/exportar")
def exportar():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    mes = request.args.get("mes") or date.today().strftime("%Y-%m")
    anio, m = mes.split("-")

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT fecha, categoria, descripcion, CAST(monto AS FLOAT) as monto
        FROM gastos WHERE EXTRACT(YEAR FROM fecha) = %s AND EXTRACT(MONTH FROM fecha) = %s
        ORDER BY fecha DESC
    """, (anio, m))
    gastos = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT categoria, CAST(SUM(monto) AS FLOAT) as total, COUNT(*) as qty
        FROM gastos WHERE EXTRACT(YEAR FROM fecha) = %s AND EXTRACT(MONTH FROM fecha) = %s
        GROUP BY categoria ORDER BY total DESC
    """, (anio, m))
    resumen = [dict(r) for r in cur.fetchall()]
    conn.close()

    wb = openpyxl.Workbook()
    h_fill  = PatternFill(start_color="2D3748", end_color="2D3748", fill_type="solid")
    h_font  = Font(color="FFFFFF", bold=True, size=11)
    alt_fill = PatternFill(start_color="EDF2F7", end_color="EDF2F7", fill_type="solid")
    thin = Side(style="thin", color="CBD5E0")
    brd  = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws = wb.active
    ws.title = f"Gastos {mes}"
    for col, (h, w) in enumerate(zip(["Fecha","Categoría","Descripción","Monto ($)"], [14,22,35,15]), 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = h_font; c.fill = h_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = brd
        ws.column_dimensions[get_column_letter(col)].width = w

    total = 0
    for i, g in enumerate(gastos, 2):
        fecha_fmt = g["fecha"].strftime("%d/%m/%Y") if hasattr(g["fecha"], 'strftime') else str(g["fecha"])
        fill = alt_fill if i % 2 == 0 else None
        for col, val in enumerate([fecha_fmt, g["categoria"], g["descripcion"], g["monto"]], 1):
            c = ws.cell(row=i, column=col, value=val)
            c.border = brd
            c.alignment = Alignment(vertical="center")
            if fill: c.fill = fill
            if col == 4:
                c.number_format = '#,##0.00'
                c.alignment = Alignment(horizontal="right", vertical="center")
        total += g["monto"]

    last = len(gastos) + 2
    ws.cell(row=last, column=3, value="TOTAL").font = Font(bold=True)
    c = ws.cell(row=last, column=4, value=total)
    c.font = Font(bold=True); c.number_format = '#,##0.00'
    c.fill = PatternFill(start_color="BEE3F8", end_color="BEE3F8", fill_type="solid")

    ws2 = wb.create_sheet("Resumen categorías")
    for col, (h, w) in enumerate(zip(["Categoría","Total ($)","Nro. gastos","% del total"], [24,16,14,14]), 1):
        c = ws2.cell(row=1, column=col, value=h)
        c.font = h_font; c.fill = h_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws2.column_dimensions[get_column_letter(col)].width = w

    total_cat = sum(r["total"] for r in resumen)
    for i, r in enumerate(resumen, 2):
        fill = alt_fill if i % 2 == 0 else None
        ws2.cell(row=i, column=1, value=r["categoria"]).fill = fill or PatternFill()
        c = ws2.cell(row=i, column=2, value=r["total"])
        c.number_format = '#,##0.00'
        ws2.cell(row=i, column=3, value=r["qty"])
        c = ws2.cell(row=i, column=4, value=r["total"]/total_cat if total_cat else 0)
        c.number_format = '0.0%'

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"gastos_{mes.replace('-','')}.xlsx"
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
