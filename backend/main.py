from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from apscheduler.schedulers.background import BackgroundScheduler

from database import db
from price_service import fetch_live_prices, is_market_open


app = FastAPI()


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://16.171.0.118",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# WEBSOCKET CONNECTION MANAGER
# =========================================================

class ConnectionManager:

    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message):
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()


# =========================================================
# WEBSOCKET ENDPOINT
# =========================================================

@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):

    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# =========================================================
# PYDANTIC MODEL
# =========================================================

class OrderCreate(BaseModel):
    user_id: int = Field(gt=0)
    stock_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    action: Literal["BUY", "SELL"]


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def home():
    return {
        "message": "Paper Trading API is running"
    }


# =========================================================
# GET STOCKS
# =========================================================

@app.get("/stocks")
def get_stocks():

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT id, symbol, price
            FROM stocks
            ORDER BY symbol
        """)

        stocks = cursor.fetchall()

        return stocks

    finally:
        cursor.close()
        connection.close()


# =========================================================
# REFRESH STOCK PRICES
# =========================================================

@app.post("/stocks/refresh-prices")
async def refresh_stock_prices():

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT id, symbol
            FROM stocks
        """)

        stocks = cursor.fetchall()

        if not stocks:
            return {
                "message": "No stocks in database to refresh",
                "updated": [],
                "failed": {}
            }

        symbols = [stock["symbol"] for stock in stocks]

        live_prices, errors = fetch_live_prices(symbols)

        updated = []

        for stock in stocks:

            symbol = stock["symbol"]

            if symbol not in live_prices:
                continue

            new_price = live_prices[symbol]

            cursor.execute("""
                UPDATE stocks
                SET price = %s
                WHERE id = %s
            """, (
                new_price,
                stock["id"]
            ))

            updated.append({
                "symbol": symbol,
                "new_price": new_price
            })

        connection.commit()

        # -------------------------------------------------
        # SEND UPDATED PRICES TO ALL WEBSOCKET CLIENTS
        # -------------------------------------------------

        if updated:

            await manager.broadcast({
                "type": "price_update",
                "stocks": updated
            })

        return {
            "message": f"Refreshed {len(updated)} of {len(stocks)} stock prices",
            "updated": updated,
            "failed": errors
        }

    except Exception as error:

        connection.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Price refresh failed: {str(error)}"
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# GET ALL ORDERS
# =========================================================

@app.get("/orders")
def get_orders():

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT
                orders.id,
                orders.user_id,
                users.username,
                stocks.symbol,
                orders.quantity,
                orders.price,
                orders.action
            FROM orders
            JOIN users
                ON orders.user_id = users.id
            JOIN stocks
                ON orders.stock_id = stocks.id
            ORDER BY orders.id DESC
        """)

        orders = cursor.fetchall()

        return orders

    finally:

        cursor.close()
        connection.close()


# =========================================================
# GET USER BALANCE
# =========================================================

@app.get("/users/{user_id}/balance")
def get_balance(user_id: int):

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT id, username, balance
            FROM users
            WHERE id = %s
        """, (user_id,))

        user = cursor.fetchone()

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        return user

    finally:

        cursor.close()
        connection.close()


# =========================================================
# CREATE BUY / SELL ORDER
# =========================================================

@app.post("/orders")
def create_order(order: OrderCreate):

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # -------------------------------------------------
        # CHECK USER
        # -------------------------------------------------

        cursor.execute("""
            SELECT id, username, balance
            FROM users
            WHERE id = %s
        """, (order.user_id,))

        user = cursor.fetchone()

        if not user:

            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        # -------------------------------------------------
        # CHECK STOCK
        # -------------------------------------------------

        cursor.execute("""
            SELECT id, symbol, price
            FROM stocks
            WHERE id = %s
        """, (order.stock_id,))

        stock = cursor.fetchone()

        if not stock:

            raise HTTPException(
                status_code=404,
                detail="Stock not found"
            )

        stock_price = float(stock["price"])

        total_value = stock_price * order.quantity

        # =================================================
        # BUY
        # =================================================

        if order.action == "BUY":

            # Check balance

            if float(user["balance"]) < total_value:

                raise HTTPException(
                    status_code=400,
                    detail="Insufficient virtual balance"
                )

            # Check existing holding

            cursor.execute("""
                SELECT id, quantity, average_price
                FROM holdings
                WHERE user_id = %s
                AND stock_id = %s
            """, (
                order.user_id,
                order.stock_id
            ))

            holding = cursor.fetchone()

            if holding:

                old_quantity = holding["quantity"]
                old_average_price = float(
                    holding["average_price"]
                )

                new_quantity = old_quantity + order.quantity

                new_average_price = (
                    (
                        old_quantity * old_average_price
                    )
                    +
                    (
                        order.quantity * stock_price
                    )
                ) / new_quantity

                cursor.execute("""
                    UPDATE holdings
                    SET quantity = %s,
                        average_price = %s
                    WHERE id = %s
                """, (
                    new_quantity,
                    new_average_price,
                    holding["id"]
                ))

            else:

                cursor.execute("""
                    INSERT INTO holdings
                    (
                        user_id,
                        stock_id,
                        quantity,
                        average_price
                    )
                    VALUES (%s, %s, %s, %s)
                """, (
                    order.user_id,
                    order.stock_id,
                    order.quantity,
                    stock_price
                ))

            # Deduct balance

            cursor.execute("""
                UPDATE users
                SET balance = balance - %s
                WHERE id = %s
            """, (
                total_value,
                order.user_id
            ))

        # =================================================
        # SELL
        # =================================================

        elif order.action == "SELL":

            cursor.execute("""
                SELECT id, quantity, average_price
                FROM holdings
                WHERE user_id = %s
                AND stock_id = %s
            """, (
                order.user_id,
                order.stock_id
            ))

            holding = cursor.fetchone()

            if not holding:

                raise HTTPException(
                    status_code=400,
                    detail="You do not own this stock"
                )

            if holding["quantity"] < order.quantity:

                raise HTTPException(
                    status_code=400,
                    detail="Insufficient stock quantity"
                )

            remaining_quantity = (
                holding["quantity"] - order.quantity
            )

            if remaining_quantity == 0:

                cursor.execute("""
                    DELETE FROM holdings
                    WHERE id = %s
                """, (
                    holding["id"],
                ))

            else:

                cursor.execute("""
                    UPDATE holdings
                    SET quantity = %s
                    WHERE id = %s
                """, (
                    remaining_quantity,
                    holding["id"]
                ))

            # Add money back to virtual balance

            cursor.execute("""
                UPDATE users
                SET balance = balance + %s
                WHERE id = %s
            """, (
                total_value,
                order.user_id
            ))

        # =================================================
        # INSERT ORDER HISTORY
        # =================================================

        cursor.execute("""
            INSERT INTO orders
            (
                user_id,
                stock_id,
                quantity,
                price,
                action
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            order.user_id,
            order.stock_id,
            order.quantity,
            stock_price,
            order.action
        ))

        connection.commit()

        return {
            "message": f"{order.action} order successful",
            "symbol": stock["symbol"],
            "quantity": order.quantity,
            "price": stock_price,
            "total_value": total_value
        }

    except HTTPException:

        connection.rollback()
        raise

    except Exception as error:

        connection.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Order failed: {str(error)}"
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# GET USER PORTFOLIO
# =========================================================

@app.get("/users/{user_id}/portfolio")
def get_portfolio(user_id: int):

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT
                holdings.id,
                holdings.stock_id,
                stocks.symbol,
                holdings.quantity,
                holdings.average_price,
                stocks.price AS current_price
            FROM holdings
            JOIN stocks
                ON holdings.stock_id = stocks.id
            WHERE holdings.user_id = %s
        """, (
            user_id,
        ))

        holdings = cursor.fetchall()

        portfolio = []

        for holding in holdings:

            quantity = holding["quantity"]

            average_price = float(
                holding["average_price"]
            )

            current_price = float(
                holding["current_price"]
            )

            invested_value = (
                quantity * average_price
            )

            current_value = (
                quantity * current_price
            )

            pnl = (
                current_value - invested_value
            )

            portfolio.append({
                "stock_id": holding["stock_id"],
                "symbol": holding["symbol"],
                "quantity": quantity,
                "average_price": average_price,
                "current_price": current_price,
                "invested_value": invested_value,
                "current_value": current_value,
                "pnl": pnl
            })

        return portfolio

    finally:

        cursor.close()
        connection.close()


# =========================================================
# GET USER ORDER HISTORY
# =========================================================

@app.get("/users/{user_id}/orders")
def get_user_orders(user_id: int):

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT
                orders.id,
                stocks.symbol,
                orders.quantity,
                orders.price,
                orders.action
            FROM orders
            JOIN stocks
                ON orders.stock_id = stocks.id
            WHERE orders.user_id = %s
            ORDER BY orders.id DESC
        """, (
            user_id,
        ))

        orders = cursor.fetchall()

        return orders

    finally:

        cursor.close()
        connection.close()


# =========================================================
# AUTOMATIC PRICE REFRESH
# =========================================================

scheduler = BackgroundScheduler()


def automatic_price_refresh():

    """
    Runs automatically every 5 minutes.

    Prices are refreshed only when
    the NSE market is open.
    """

    if not is_market_open():

        print("Market is closed. Skipping price refresh.")

        return

    print(
        "Market is open. Starting automatic price refresh..."
    )

    try:

        # Because refresh_stock_prices() is async,
        # run it inside an async event loop.

        import asyncio

        result = asyncio.run(
            refresh_stock_prices()
        )

        print(
            "Automatic price refresh completed:"
        )

        print(result)

    except Exception as error:

        print(
            f"Automatic price refresh failed: {error}"
        )


# =========================================================
# START SCHEDULER
# =========================================================

@app.on_event("startup")
def start_scheduler():

    scheduler.add_job(
        automatic_price_refresh,
        "interval",
        minutes=5,
        id="stock_price_refresh",
        replace_existing=True
    )

    scheduler.start()

    print(
        "Price refresh scheduler started."
    )


# =========================================================
# STOP SCHEDULER
# =========================================================

@app.on_event("shutdown")
def stop_scheduler():

    scheduler.shutdown()

    print(
        "Price refresh scheduler stopped."
    )