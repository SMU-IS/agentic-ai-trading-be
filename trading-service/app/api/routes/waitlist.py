from app.core.services import services
from app.core.trading_db_client import MongoDBClient
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter()

mongo_client: MongoDBClient = services.trading_db


class WaitlistRequest(BaseModel):
    email: EmailStr


@router.post("")
def join_waitlist(
    body: WaitlistRequest, client: MongoDBClient = Depends(lambda: mongo_client)
):
    try:
        result = client.add_to_waitlist(body.email)
        if not result["success"]:
            raise HTTPException(status_code=409, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
