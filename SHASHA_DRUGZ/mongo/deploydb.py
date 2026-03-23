import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from bson.objectid import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import DuplicateKeyError, OperationFailure

from SHASHA_DRUGZ.core.mongo import mongodb

# Collections
deploy_bots_col: AsyncIOMotorCollection = mongodb.deploy_bots
deploy_sessions_col: AsyncIOMotorCollection = mongodb.deploy_sessions
pending_payments_col: AsyncIOMotorCollection = mongodb.pending_payments
refunds_col: AsyncIOMotorCollection = mongodb.deploy_refunds
deploy_chats_col: AsyncIOMotorCollection = mongodb.deploy_chats
deploy_users_col: AsyncIOMotorCollection = mongodb.deploy_users

# ---------- INDEXES (safe creation) ----------
async def ensure_indexes():
    """Create unique indexes for data integrity, handling existing non‑unique indexes."""
    # Helper to drop index if exists and is not unique
    async def ensure_unique_index(collection, key, unique=True):
        indexes = await collection.index_information()
        # MongoDB auto‑names indexes by key, e.g. "token_1"
        index_name = f"{key}_1"
        if index_name in indexes:
            # If it already exists and is already unique, keep it
            if indexes[index_name].get("unique"):
                return
            # Otherwise drop it (non‑unique or other)
            await collection.drop_index(index_name)
        try:
            await collection.create_index(key, unique=unique)
        except DuplicateKeyError:
            # This happens if there are duplicate values in the collection.
            # We'll print a warning and create a non‑unique index instead.
            print(f"⚠️ Cannot create unique index on {key} because duplicates exist. Creating non‑unique index.")
            await collection.create_index(key, unique=False)

    # Deployed bots: bot_id and token must be unique
    await ensure_unique_index(deploy_bots_col, "bot_id")
    await ensure_unique_index(deploy_bots_col, "token")

    # Compound unique indexes for per‑bot data
    try:
        await deploy_users_col.create_index(
            [("user_id", 1), ("bot_id", 1)],
            unique=True
        )
    except DuplicateKeyError:
        print("⚠️ Duplicate (user_id, bot_id) entries found. Creating non‑unique index.")
        await deploy_users_col.create_index([("user_id", 1), ("bot_id", 1)])

    try:
        await deploy_chats_col.create_index(
            [("chat_id", 1), ("bot_id", 1)],
            unique=True
        )
    except DuplicateKeyError:
        print("⚠️ Duplicate (chat_id, bot_id) entries found. Creating non‑unique index.")
        await deploy_chats_col.create_index([("chat_id", 1), ("bot_id", 1)])

    # Optional: index on owner_id for faster queries
    await deploy_bots_col.create_index("owner_id")

# ---------- SESSION ----------
async def save_deploy_session(user_id: int, data: dict):
    await deploy_sessions_col.update_one(
        {"_id": user_id}, {"$set": data}, upsert=True
    )

async def get_deploy_session(user_id: int) -> dict:
    session = await deploy_sessions_col.find_one({"_id": user_id})
    return session or {}

async def clear_deploy_session(user_id: int):
    await deploy_sessions_col.delete_one({"_id": user_id})

# ---------- DEPLOYED BOTS ----------
async def save_deployed_bot(bot_data: dict):
    bot_data["created_at"] = datetime.utcnow()
    bot_data["status"] = "active"
    await deploy_bots_col.insert_one(bot_data)

async def get_deployed_bot_by_token(token: str) -> Optional[dict]:
    return await deploy_bots_col.find_one({"token": token})

async def get_deployed_bot_by_id(bot_id: int) -> Optional[dict]:
    return await deploy_bots_col.find_one({"bot_id": bot_id})

async def get_deployed_bot_by_username(username: str) -> Optional[dict]:
    return await deploy_bots_col.find_one({"username": username})

async def get_deployed_bots_by_user(user_id: int) -> List[dict]:
    cursor = deploy_bots_col.find({"owner_id": user_id})
    return await cursor.to_list(length=None)

async def get_all_deployed_bots() -> List[dict]:
    cursor = deploy_bots_col.find()
    return await cursor.to_list(length=None)

async def update_deployed_bot(bot_id: int, update: dict):
    await deploy_bots_col.update_one({"bot_id": bot_id}, {"$set": update})

async def delete_deployed_bot(bot_id: int):
    await deploy_bots_col.delete_one({"bot_id": bot_id})

async def get_expired_bots() -> List[dict]:
    """Return bots whose expiry date has passed and status is active."""
    cursor = deploy_bots_col.find({
        "expiry_date": {"$lt": datetime.utcnow()},
        "status": "active"
    })
    return await cursor.to_list(length=None)

async def get_bots_expiring_soon(days: int = 2) -> List[dict]:
    now = datetime.utcnow()
    soon = now + timedelta(days=days)
    cursor = deploy_bots_col.find({
        "expiry_date": {"$gte": now, "$lte": soon},
        "status": "active"
    })
    return await cursor.to_list(length=None)

async def update_bot_expiry(bot_id: int, new_expiry: datetime):
    await deploy_bots_col.update_one(
        {"bot_id": bot_id},
        {"$set": {"expiry_date": new_expiry}}
    )

async def delete_all_deployed_bots():
    """Dangerous – only for owner."""
    await deploy_bots_col.delete_many({})

# ---------- PAYMENTS ----------
async def create_pending_payment(user_id: int, data: dict) -> str:
    data["user_id"] = user_id
    data["created_at"] = datetime.utcnow()
    data["status"] = "pending"
    result = await pending_payments_col.insert_one(data)
    return str(result.inserted_id)

async def get_pending_payment(payment_id: str) -> Optional[dict]:
    return await pending_payments_col.find_one({"_id": ObjectId(payment_id)})

async def update_pending_payment(payment_id: str, update: dict):
    await pending_payments_col.update_one({"_id": ObjectId(payment_id)}, {"$set": update})

async def delete_pending_payment(payment_id: str):
    await pending_payments_col.delete_one({"_id": ObjectId(payment_id)})

async def get_pending_payments_by_user(user_id: int) -> List[dict]:
    cursor = pending_payments_col.find({"user_id": user_id, "status": "pending"})
    return await cursor.to_list(length=None)

# ---------- REFUNDS ----------
async def create_refund(data: dict):
    await refunds_col.insert_one(data)

async def get_refund(payment_id: str) -> Optional[dict]:
    return await refunds_col.find_one({"payment_id": payment_id})

# ---------- PER‑BOT DATA ----------
async def add_served_chat_deploy(chat_id: int, bot_id: int):
    try:
        await deploy_chats_col.insert_one({"chat_id": chat_id, "bot_id": bot_id})
    except DuplicateKeyError:
        pass  # already exists

async def remove_served_chat_deploy(chat_id: int, bot_id: int):
    await deploy_chats_col.delete_one({"chat_id": chat_id, "bot_id": bot_id})

async def get_served_chats_deploy(bot_id: int) -> List[dict]:
    cursor = deploy_chats_col.find({"bot_id": bot_id})
    return await cursor.to_list(length=None)

async def add_served_user_deploy(user_id: int, bot_id: int):
    try:
        await deploy_users_col.insert_one({"user_id": user_id, "bot_id": bot_id})
    except DuplicateKeyError:
        pass

async def remove_served_user_deploy(user_id: int, bot_id: int):
    await deploy_users_col.delete_one({"user_id": user_id, "bot_id": bot_id})

async def get_served_users_deploy(bot_id: int) -> List[dict]:
    cursor = deploy_users_col.find({"bot_id": bot_id})
    return await cursor.to_list(length=None)

# ---------- OWNER CHECK ----------
async def is_deploy_owner(bot_id: int, user_id: int) -> bool:
    bot = await get_deployed_bot_by_id(bot_id)
    return bool(bot and bot.get("owner_id") == user_id)

# ---------- BOT‑SPECIFIC COLLECTION (prevents cross‑bot settings conflicts) ----------
def get_bot_collection(bot_id: int, collection_name: str):
    """
    Returns a MongoDB collection that is unique to a specific bot.
    Use this for any settings that should not be shared across bots.
    Example: settings_col = get_bot_collection(bot_id, "settings")
    """
    return mongodb[f"bot_{bot_id}_{collection_name}"]

# ---------- CLEANUP EXPIRED BOT (ALL DATA) ----------
async def cleanup_expired_bot(bot_id: int):
    """Remove bot and all its associated data."""
    await deploy_bots_col.delete_one({"bot_id": bot_id})
    await deploy_chats_col.delete_many({"bot_id": bot_id})
    await deploy_users_col.delete_many({"bot_id": bot_id})
    # also delete pending payments? optional
    # noinspection PyBroadException
    try:
        from SHASHA_DRUGZ.plugins.PREMIUM.deploy import DEPLOYED_CLIENTS
        client = DEPLOYED_CLIENTS.pop(bot_id, None)
        if client:
            await client.stop()
    except Exception:
        pass
