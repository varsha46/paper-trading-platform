
import os

import mysql.connector
import mysql.connector.pooling

from dotenv import load_dotenv

load_dotenv()

db = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="paper_pool",
    pool_size=5,
    host=os.getenv("MYSQL_HOST"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE")
)
