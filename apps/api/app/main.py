from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import csv, io, json

from .db import engine, Base, get_db
from .models import InvoiceUpload, InvoiceLineItem

app = FastAPI(title="3PL Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row.")

    headers = {h.strip() for h in reader.fieldnames}
    required = {"fee_type_raw", "amount"}
    missing = required - headers
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {sorted(missing)}")

    # 1) create invoice upload record
    invoice = InvoiceUpload(filename=file.filename or "uploaded.csv")
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    # 2) parse + insert line items
    inserted = 0
    preview = []

    for row in reader:
        fee = (row.get("fee_type_raw") or "").strip()
        amt = (row.get("amount") or "").strip()
        if not fee or not amt:
            continue

        item = InvoiceLineItem(
            invoice_id=invoice.id,
            fee_type_raw=fee,
            amount_raw=amt,
            order_ref=(row.get("order_ref") or "").strip() or None,
            tracking_ref=(row.get("tracking_ref") or "").strip() or None,
            raw_row_json=json.dumps(row),
        )
        db.add(item)
        inserted += 1

        if len(preview) < 10:
            preview.append({
                "fee_type_raw": fee,
                "amount": amt,
                "order_ref": item.order_ref,
                "tracking_ref": item.tracking_ref,
            })

    db.commit()

    return {
        "invoice_id": invoice.id,
        "filename": invoice.filename,
        "headers": list(reader.fieldnames),
        "inserted_rows": inserted,
        "preview": preview,
    }

@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(InvoiceUpload, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    count = db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == invoice_id).count()

    return {
        "invoice_id": invoice.id,
        "filename": invoice.filename,
        "created_at": invoice.created_at.isoformat(),
        "line_item_count": count,
    }

