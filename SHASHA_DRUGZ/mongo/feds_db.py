# feds_db.py
from datetime import datetime
import pytz

# this expects your project to already provide a `database` module that exposes `dbname`
# which is the usual pattern in HB-Cute / SHASHA_DRUGZ forks.
from SHASHA_DRUGZ.mongo import dbname
from config import OWNER_ID

# normalize SUDO list from config
try:
    SUDO = list(map(int, SUDOERS))
except Exception:
    # fallback: empty list if not configured properly
    SUDO = []

fedsdb = dbname.get_collection("federation") if hasattr(dbname, "get_collection") else dbname["federation"]


async def get_fed_info(fed_id: str):
    """Return fed document or False"""
    get = await fedsdb.find_one({"fed_id": str(fed_id)})
    return False if get is None else get


async def get_fed_id(chat_id: int):
    """Return fed_id if chat belongs to any federation, else False"""
    get = await fedsdb.find_one({"chat_ids.chat_id": int(chat_id)})
    if not get:
        return False
    # return fed_id
    return get.get("fed_id", False)


async def get_feds_by_owner(owner_id: int):
    cursor = fedsdb.find({"owner_id": int(owner_id)})
    feds = await cursor.to_list(length=None)
    if not feds:
        return False
    return [{"fed_id": fed["fed_id"], "fed_name": fed["fed_name"]} for fed in feds]


async def transfer_owner(fed_id: str, current_owner_id: int, new_owner_id: int) -> bool:
    """Transfer ownership only if current_owner_id matches stored owner"""
    fed = await get_fed_info(fed_id)
    if not fed:
        return False
    if int(fed.get("owner_id")) != int(current_owner_id):
        # only actual stored owner can transfer (superusers can operate via other codepaths)
        return False
    result = await fedsdb.update_one(
        {"fed_id": str(fed_id), "owner_id": int(current_owner_id)},
        {"$set": {"owner_id": int(new_owner_id)}},
    )
    return result.modified_count > 0


async def set_log_chat(fed_id: str, log_group_id: int):
    await fedsdb.update_one({"fed_id": str(fed_id)}, {"$set": {"log_group_id": int(log_group_id)}}, upsert=True)
    return True


async def get_fed_name(fed_id: str):
    """Return fed name by fed_id"""
    get = await fedsdb.find_one({"fed_id": str(fed_id)})
    return False if get is None else get.get("fed_name")


async def is_user_fed_owner(fed_id: str, user_id: int) -> bool:
    """True if user is federation owner or global sudo/owner"""
    getfed = await get_fed_info(fed_id)
    if not getfed:
        return False
    owner_id = int(getfed.get("owner_id"))
    u = int(user_id)
    return u == owner_id or u in SUDO or u == int(OWNER_ID)


async def search_fed_by_id(fed_id: str):
    get = await fedsdb.find_one({"fed_id": str(fed_id)})
    return get if get is not None else False


async def chat_join_fed(fed_id: str, chat_name: str, chat_id: int):
    """Add chat to a federation's chat_ids"""
    result = await fedsdb.update_one(
        {"fed_id": str(fed_id)},
        {"$addToSet": {"chat_ids": {"chat_id": int(chat_id), "chat_name": chat_name}}},
        upsert=True,
    )
    return result.modified_count > 0


async def chat_leave_fed(chat_id: int) -> bool:
    result = await fedsdb.update_one(
        {"chat_ids.chat_id": int(chat_id)},
        {"$pull": {"chat_ids": {"chat_id": int(chat_id)}}},
    )
    return result.modified_count > 0


async def user_join_fed(fed_id: str, user_id: int) -> bool:
    result = await fedsdb.update_one(
        {"fed_id": str(fed_id)}, {"$addToSet": {"fadmins": int(user_id)}}, upsert=True
    )
    return result.modified_count > 0


async def user_demote_fed(fed_id: str, user_id: int) -> bool:
    result = await fedsdb.update_one(
        {"fed_id": str(fed_id)}, {"$pull": {"fadmins": int(user_id)}}
    )
    return result.modified_count > 0


async def search_user_in_fed(fed_id: str, user_id: int) -> bool:
    getfed = await search_fed_by_id(fed_id)
    if not getfed:
        return False
    return int(user_id) in [int(x) for x in getfed.get("fadmins", [])]


async def chat_id_and_names_in_fed(fed_id: str):
    getfed = await search_fed_by_id(fed_id)
    if getfed is None or "chat_ids" not in getfed:
        return [], []
    chat_ids = [int(chat["chat_id"]) for chat in getfed["chat_ids"]]
    chat_names = [chat.get("chat_name", "") for chat in getfed["chat_ids"]]
    return chat_ids, chat_names


async def add_fban_user(fed_id: str, user_id: int, reason: str):
    current_date = datetime.now(pytz.timezone("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M")
    await fedsdb.update_one(
        {"fed_id": fed_id},
        {
            "$push": {
                "banned_users": {
                    "user_id": int(user_id),
                    "reason": reason,
                    "date": current_date,
                }
            }
        },
        upsert=True,
    )
    return True


async def remove_fban_user(fed_id: str, user_id: int):
    await fedsdb.update_one(
        {"fed_id": fed_id}, {"$pull": {"banned_users": {"user_id": int(user_id)}}}
    )
    return True


async def check_banned_user(fed_id: str, user_id: int):
    """Return dict(reason,date) if banned, else False"""
    result = await fedsdb.find_one({"fed_id": fed_id, "banned_users.user_id": int(user_id)})
    if result and "banned_users" in result:
        for user in result["banned_users"]:
            if int(user.get("user_id")) == int(user_id):
                return {"reason": user.get("reason"), "date": user.get("date")}
    return False
