import os
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST","localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT",6379))
REDIS_DB= int(os.getenv("REDIS_DB_MAIN",0))

#redis_client = redis.Redis(host=REDIS_HOST,db=REDIS_DB,decode_responses=True,port=REDIS_PORT)
redis_client = redis.Redis(host='localhost',db=0,decode_responses=True,port=6379)

