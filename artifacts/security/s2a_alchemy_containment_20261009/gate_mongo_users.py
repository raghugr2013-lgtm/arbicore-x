
import asyncio, json, os
async def main():
  from motor.motor_asyncio import AsyncIOMotorClient
  c=AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
  admin=c["admin"]
  try:
    users=await admin.command("usersInfo")
    names=sorted([u.get("user") for u in users.get("users",[])])
  except Exception as e:
    names=[f"error:{type(e).__name__}"]
  try:
    ax=await c["arbicore_x"].command("usersInfo")
    ax_names=sorted([u.get("user") for u in ax.get("users",[])])
  except Exception as e:
    ax_names=[f"error:{type(e).__name__}"]
  print(json.dumps({"admin_users":names,"arbicore_x_users":ax_names}))
asyncio.run(main())
