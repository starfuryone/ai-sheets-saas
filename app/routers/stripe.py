from fastapi import APIRouter
router = APIRouter()

@router.post('/webhook')
def webhook():
    # TODO: implement signature verification and idempotency
    return {"status": "ok"}
