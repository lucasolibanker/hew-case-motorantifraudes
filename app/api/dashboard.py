"""Dashboard mínimo. HTML gerado aqui, sem frontend separado.

autoescape ligado: o detalhe da regra contém texto nosso, mas o e-mail e o
IP do cliente também aparecem na página. Sem escape, um e-mail com HTML
viraria script no navegador de quem opera o painel.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.money import from_cents
from app.storage.postgres import Database

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    db: Database = request.app.state.db
    rows = []
    for row in db.list_recent():
        reasons = row.get("reasons") or []
        rows.append(
            {
                "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "amount": from_cents(int(row["amount_cents"])),
                "currency": str(row["currency"]).strip(),
                "pan_last4": row["pan_last4"],
                "risk_score": row.get("risk_score") if row.get("risk_score") is not None else "—",
                "decision": row.get("decision") or "—",
                "status": row["status"],
                "reasons": reasons,
                "observed_ip": row["observed_ip"],
                "client_ip": row["client_ip"],
                "customer_id": row["customer_id"],
            }
        )
    return templates.TemplateResponse(request, "dashboard.html", {"rows": rows})
