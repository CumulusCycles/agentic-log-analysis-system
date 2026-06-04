from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.jwt import get_current_user
from ..db import mongo
from ..db.mongo import to_object_id
from ..logging_setup import get_logger
from ..schemas import UserOut

router = APIRouter(tags=["users"])
log = get_logger("users")


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str, _: dict = Depends(get_current_user)) -> UserOut:
    db = mongo.get_db()
    user = await db.users.find_one({"_id": to_object_id(user_id)})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    log.info("user_fetched", user_id=user_id, role=user["role"])
    return UserOut(
        id=str(user["_id"]),
        username=user["username"],
        role=user["role"],
        display_name=user["display_name"],
    )
