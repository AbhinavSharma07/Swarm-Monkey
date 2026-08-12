from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from sample_app.app.pricing import quote

app = FastAPI(title="sample-app: order quote service")


class QuoteRequest(BaseModel):
    quantity: int
    unit_price: float
    is_member: bool = False


class QuoteResponse(BaseModel):
    total: float


@app.post("/quote", response_model=QuoteResponse)
def get_quote(request: QuoteRequest) -> QuoteResponse:
    try:
        total = quote(request.quantity, request.unit_price, request.is_member)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return QuoteResponse(total=total)
