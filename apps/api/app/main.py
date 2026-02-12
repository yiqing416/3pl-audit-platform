from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Body, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
import csv, io, json, re
from typing import Optional, Dict, Any

from .db import engine, Base, get_db
from .models import InvoiceUpload, InvoiceLineItem, FeeTypeMap  # <-- add FeeTypeMap
from dotenv import load_dotenv
load_dotenv()

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
    pass

# Canonical fields your backend logic understands (independent of CSV header names)
CANONICAL_FIELDS = {"fee_type_raw", "amount", "order_ref", "tracking_ref"}


# -------------------------
# Helpers
# -------------------------
def parse_money_to_cents(s: str) -> int:
    """
    Convert '$1,234.56', '(12.34)', '-12.34' into integer cents.
    Raises ValueError if invalid.
    """
    if s is None:
        raise ValueError("amount missing")
    t = s.strip()
    if not t:
        raise ValueError("amount empty")

    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative = True
        t = t[1:-1].strip()

    t = t.replace("$", "").replace(",", "").strip()
    if t.startswith("-"):
        negative = True
        t = t[1:].strip()

    if not re.match(r"^\d+(\.\d{1,2})?$", t):
        raise ValueError(f"invalid amount format: {s}")

    if "." in t:
        dollars, cents = t.split(".", 1)
        cents = (cents + "00")[:2]
    else:
        dollars, cents = t, "00"

    value = int(dollars) * 100 + int(cents)
    return -value if negative else value


def build_field_map(headers: list[str], user_map: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Return {canonical_field: header_name}.
    If user_map is missing, try a basic heuristic guess.
    """
    headers_clean = [h.strip() for h in headers]
    header_set = set(headers_clean)
    header_lower = {h: h.lower() for h in headers_clean}

    # If provided, validate
    if user_map:
        for k, v in user_map.items():
            if k not in CANONICAL_FIELDS:
                raise HTTPException(400, f"Unknown canonical field in field_map: {k}")
            if v not in header_set:
                raise HTTPException(400, f"Header '{v}' not found in CSV headers.")
        return user_map

    # Simple heuristic fallback (you can improve later)
    candidates = {
        "fee_type_raw": ["fee", "fee type", "charge type", "accessorial", "surcharge"],
        "amount": ["amount", "charge", "total", "fee amount", "cost"],
        "order_ref": ["order", "order id", "order_ref", "reference"],
        "tracking_ref": ["tracking", "tracking id", "tracking_ref", "tracking number"],
    }

    fmap: Dict[str, str] = {}
    for canonical, keys in candidates.items():
        for h in headers_clean:
            hl = header_lower[h]
            if any(k in hl for k in keys):
                fmap[canonical] = h
                break

    return fmap


def match_fee_type(fee_raw: str, maps: list["FeeTypeMap"]) -> Optional[str]:
    """
    Match fee_raw against FeeTypeMap rules (ordered by priority desc).
    """
    s = (fee_raw or "").strip()
    sl = s.lower()

    for m in maps:
        if not m.enabled:
            continue

        p = (m.pattern or "").strip()
        if not p:
            continue

        if m.match_type == "exact":
            if sl == p.lower():
                return m.normalized_type

        elif m.match_type == "contains":
            if p.lower() in sl:
                return m.normalized_type

        elif m.match_type == "regex":
            if re.search(p, s, flags=re.IGNORECASE):
                return m.normalized_type

    return None


# -------------------------
# Health
# -------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# -------------------------
# Upload: supports field_map
# -------------------------
@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    field_map_json: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    field_map = json.loads(field_map_json) if field_map_json else None
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row.")

    headers = [h.strip() for h in reader.fieldnames]
    fmap = build_field_map(headers, field_map)

    # Require at least fee_type_raw + amount meaning
    if "fee_type_raw" not in fmap or "amount" not in fmap:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Missing required canonical mappings.",
                "required": ["fee_type_raw", "amount"],
                "detected_field_map": fmap,
                "hint": "Provide field_map as JSON body: {fee_type_raw: 'YourHeader', amount: 'YourHeader', ...}",
                "headers": headers,
            },
        )

    # Create invoice record (store headers + field map so later logic knows meanings)
    invoice = InvoiceUpload(
        filename=file.filename or "uploaded.csv",
        headers_json=json.dumps(headers),
        field_map_json=json.dumps(fmap),
        total_rows=0,
        valid_rows=0,
        invalid_rows=0,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    inserted = 0
    invalid = 0
    preview_valid = []
    preview_invalid = []

    for row_number, row in enumerate(reader, start=2):  # start=2 because header line is row 1
        try:
            fee = (row.get(fmap["fee_type_raw"]) or "").strip()
            amt_raw = (row.get(fmap["amount"]) or "").strip()

            if not fee:
                raise ValueError("fee_type_raw empty")
            if not amt_raw:
                raise ValueError("amount empty")

            amount_cents = parse_money_to_cents(amt_raw)

            order_ref = None
            tracking_ref = None
            if "order_ref" in fmap:
                order_ref = (row.get(fmap["order_ref"]) or "").strip() or None
            if "tracking_ref" in fmap:
                tracking_ref = (row.get(fmap["tracking_ref"]) or "").strip() or None

            item = InvoiceLineItem(
                invoice_id=invoice.id,
                row_number=row_number,
                fee_type_raw=fee,
                amount_raw=amt_raw,
                amount_cents=amount_cents,
                order_ref=order_ref,
                tracking_ref=tracking_ref,
                is_valid=True,
                raw_row_json=json.dumps(row),
            )
            db.add(item)
            inserted += 1

            if len(preview_valid) < 10:
                preview_valid.append(
                    {
                        "row_number": row_number,
                        "fee_type_raw": fee,
                        "amount_raw": amt_raw,
                        "amount_cents": amount_cents,
                        "order_ref": order_ref,
                        "tracking_ref": tracking_ref,
                    }
                )

        except Exception as e:
            invalid += 1
            bad = InvoiceLineItem(
                invoice_id=invoice.id,
                row_number=row_number,
                fee_type_raw=(row.get(fmap.get("fee_type_raw", "")) or "").strip() if fmap.get("fee_type_raw") else "",
                amount_raw=(row.get(fmap.get("amount", "")) or "").strip() if fmap.get("amount") else "",
                is_valid=False,
                error_code="ROW_PARSE_ERROR",
                error_detail=str(e),
                raw_row_json=json.dumps(row),
            )
            db.add(bad)

            if len(preview_invalid) < 10:
                preview_invalid.append(
                    {
                        "row_number": row_number,
                        "error": str(e),
                        "raw": row,
                    }
                )

    invoice.total_rows = inserted + invalid
    invoice.valid_rows = inserted
    invoice.invalid_rows = invalid
    db.commit()

    return {
        "invoice_id": invoice.id,
        "filename": invoice.filename,
        "headers": headers,
        "field_map": fmap,
        "valid_rows": inserted,
        "invalid_rows": invalid,
        "preview_valid": preview_valid,
        "preview_invalid": preview_invalid,
    }


# -------------------------
# Invoice metadata
# -------------------------
@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(InvoiceUpload, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {
        "invoice_id": invoice.id,
        "filename": invoice.filename,
        "created_at": invoice.created_at.isoformat(),
        "headers": json.loads(invoice.headers_json or "[]"),
        "field_map": json.loads(invoice.field_map_json or "{}"),
        "total_rows": invoice.total_rows or 0,
        "valid_rows": invoice.valid_rows or 0,
        "invalid_rows": invoice.invalid_rows or 0,
    }


# -------------------------
# Invoice items (for UI)
# -------------------------
@app.get("/invoices/{invoice_id}/items")
def list_items(
    invoice_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    is_valid: Optional[bool] = Query(None),
    fee_type_norm: Optional[str] = Query(None),
    missing_ref: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == invoice_id)

    if is_valid is not None:
        q = q.filter(InvoiceLineItem.is_valid == is_valid)

    if fee_type_norm is not None:
        if fee_type_norm == "__NULL__":
            q = q.filter(InvoiceLineItem.fee_type_norm.is_(None))
        else:
            q = q.filter(InvoiceLineItem.fee_type_norm == fee_type_norm)

    if missing_ref:
        q = q.filter(
            (InvoiceLineItem.tracking_ref.is_(None)) & (InvoiceLineItem.order_ref.is_(None))
        )

    total = q.count()
    rows = q.order_by(InvoiceLineItem.row_number.asc()).offset(offset).limit(limit).all()

    return {
        "invoice_id": invoice_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "row_number": r.row_number,
                "fee_type_raw": r.fee_type_raw,
                "fee_type_norm": r.fee_type_norm,
                "amount_raw": r.amount_raw,
                "amount_cents": r.amount_cents,
                "order_ref": r.order_ref,
                "tracking_ref": r.tracking_ref,
                "is_valid": r.is_valid,
                "error_code": r.error_code,
                "error_detail": r.error_detail,
            }
            for r in rows
        ],
    }


# -------------------------
# Save/update field map for an invoice
# -------------------------
@app.post("/invoices/{invoice_id}/field-map")
def save_field_map(
    invoice_id: int,
    field_map: Dict[str, str] = Body(...),
    db: Session = Depends(get_db),
):
    invoice = db.get(InvoiceUpload, invoice_id)
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    headers = json.loads(invoice.headers_json or "[]")
    fmap = build_field_map(headers, field_map)
    if "fee_type_raw" not in fmap or "amount" not in fmap:
        raise HTTPException(400, "field_map must include fee_type_raw and amount")

    invoice.field_map_json = json.dumps(fmap)
    db.commit()
    return {"invoice_id": invoice_id, "field_map": fmap}


# -------------------------
# Fee mapping rules (editable)
# -------------------------
@app.get("/fee-maps")
def list_fee_maps(db: Session = Depends(get_db)):
    rows = db.query(FeeTypeMap).order_by(FeeTypeMap.priority.desc()).all()
    return [
        {
            "id": r.id,
            "pattern": r.pattern,
            "match_type": r.match_type,
            "normalized_type": r.normalized_type,
            "priority": r.priority,
            "enabled": r.enabled,
        }
        for r in rows
    ]


@app.post("/fee-maps")
def create_fee_map(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    pattern = (payload.get("pattern") or "").strip()
    normalized_type = (payload.get("normalized_type") or "").strip()
    match_type = (payload.get("match_type") or "contains").strip()
    priority = int(payload.get("priority") or 0)
    enabled = bool(payload.get("enabled", True))

    if not pattern or not normalized_type:
        raise HTTPException(400, "pattern and normalized_type are required")
    if match_type not in {"contains", "regex", "exact"}:
        raise HTTPException(400, "match_type must be contains|regex|exact")

    row = FeeTypeMap(
        pattern=pattern,
        match_type=match_type,
        normalized_type=normalized_type,
        priority=priority,
        enabled=enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


# -------------------------
# Normalize fee types for an invoice
# -------------------------
@app.post("/invoices/{invoice_id}/normalize")
def normalize_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(InvoiceUpload, invoice_id)
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    maps = db.query(FeeTypeMap).order_by(FeeTypeMap.priority.desc()).all()

    q = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id,
        InvoiceLineItem.is_valid == True,
    )

    updated = 0
    unknown = 0
    for item in q:
        norm = match_fee_type(item.fee_type_raw, maps)
        item.fee_type_norm = norm
        if norm:
            updated += 1
        else:
            unknown += 1

    db.commit()
    return {"invoice_id": invoice_id, "normalized": updated, "unknown": unknown}


# -------------------------
# MVP Audit (no persisted findings yet)
# -------------------------
@app.post("/invoices/{invoice_id}/audit")
def audit_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """
    MVP audit:
    - Unknown fee type (fee_type_norm is null)
    - Duplicate charges by (fee_type_norm, amount_cents, ref_key)
      where ref_key = tracking_ref or order_ref (must exist to count duplicates)
    """
    # unknown fee type
    unknown_count = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id,
        InvoiceLineItem.is_valid == True,
        InvoiceLineItem.fee_type_norm.is_(None),
    ).count()

    items = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id,
        InvoiceLineItem.is_valid == True,
    ).all()

    seen = set()
    dup_count = 0
    for it in items:
        ref_key = it.tracking_ref or it.order_ref
        if not ref_key:
            continue
        key = (it.fee_type_norm or "", it.amount_cents, ref_key)
        if key in seen:
            dup_count += 1
        else:
            seen.add(key)

    return {
        "invoice_id": invoice_id,
        "unknown_fee_type_rows": unknown_count,
        "duplicate_rows": dup_count,
        "note": "Next step: persist findings into an AuditFindings table.",
    }
