from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from database import db


app = FastAPI()
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
# REQUEST MODELS
# =========================================================

class OrderCreate(BaseModel):
    user_id: int = Field(gt=0)
    stock_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    action: Literal["BUY", "SELL"]


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return {
        "message": "Paper Trading Platform API"
    }


# =========================================================
# GET ALL STOCKS
# =========================================================

@app.get("/stocks")
def get_stocks():

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT
                id,
                symbol,
                price
            FROM stocks
        """)

        stocks = cursor.fetchall()

        return stocks

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
            SELECT
                id,
                username,
                balance
            FROM users
            WHERE id = %s
        """, (user_id,))

        user = cursor.fetchone()

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        return user

    finally:

        cursor.close()
        connection.close()


# =========================================================
# CREATE ORDER
# =========================================================

@app.post("/orders")
def create_order(order: OrderCreate):

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # -------------------------------------------------
        # 1. Check user
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                balance
            FROM users
            WHERE id = %s
        """, (order.user_id,))

        user = cursor.fetchone()

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )


        # -------------------------------------------------
        # 2. Check stock
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                symbol,
                price
            FROM stocks
            WHERE id = %s
        """, (order.stock_id,))

        stock = cursor.fetchone()

        if stock is None:
            raise HTTPException(
                status_code=404,
                detail="Stock not found"
            )


        # -------------------------------------------------
        # 3. Calculate total order value
        # -------------------------------------------------

        total_cost = stock["price"] * order.quantity


        # =================================================
        # BUY
        # =================================================

        if order.action == "BUY":

            # ---------------------------------------------
            # Check balance
            # ---------------------------------------------

            if user["balance"] < total_cost:

                raise HTTPException(
                    status_code=400,
                    detail="Insufficient balance"
                )


            # ---------------------------------------------
            # Check existing holding
            # ---------------------------------------------

            cursor.execute("""
                SELECT
                    quantity,
                    average_price
                FROM holdings
                WHERE user_id = %s
                AND stock_id = %s
            """, (
                order.user_id,
                order.stock_id
            ))

            holding = cursor.fetchone()


            # ---------------------------------------------
            # Existing holding
            # ---------------------------------------------

            if holding:

                old_quantity = holding["quantity"]
                old_average_price = holding["average_price"]

                new_quantity = old_quantity + order.quantity

                new_average_price = (
                    (
                        old_quantity * old_average_price
                    )
                    +
                    (
                        order.quantity * stock["price"]
                    )
                ) / new_quantity


                cursor.execute("""
                    UPDATE holdings
                    SET
                        quantity = %s,
                        average_price = %s
                    WHERE user_id = %s
                    AND stock_id = %s
                """, (
                    new_quantity,
                    new_average_price,
                    order.user_id,
                    order.stock_id
                ))


            # ---------------------------------------------
            # First time buying stock
            # ---------------------------------------------

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
                    stock["price"]
                ))


            # ---------------------------------------------
            # Deduct virtual money
            # ---------------------------------------------

            cursor.execute("""
                UPDATE users
                SET balance = balance - %s
                WHERE id = %s
            """, (
                total_cost,
                order.user_id
            ))


        # =================================================
        # SELL
        # =================================================

        else:

            # ---------------------------------------------
            # Find holding
            # ---------------------------------------------

            cursor.execute("""
                SELECT
                    quantity
                FROM holdings
                WHERE user_id = %s
                AND stock_id = %s
            """, (
                order.user_id,
                order.stock_id
            ))

            holding = cursor.fetchone()


            # ---------------------------------------------
            # User doesn't own stock
            # ---------------------------------------------

            if holding is None:

                raise HTTPException(
                    status_code=400,
                    detail="You do not own this stock"
                )


            # ---------------------------------------------
            # Not enough shares
            # ---------------------------------------------

            if holding["quantity"] < order.quantity:

                raise HTTPException(
                    status_code=400,
                    detail="Insufficient shares"
                )


            remaining_quantity = (
                holding["quantity"] - order.quantity
            )


            # ---------------------------------------------
            # Remove holding if quantity becomes zero
            # ---------------------------------------------

            if remaining_quantity == 0:

                cursor.execute("""
                    DELETE FROM holdings
                    WHERE user_id = %s
                    AND stock_id = %s
                """, (
                    order.user_id,
                    order.stock_id
                ))


            # ---------------------------------------------
            # Otherwise update quantity
            # ---------------------------------------------

            else:

                cursor.execute("""
                    UPDATE holdings
                    SET quantity = %s
                    WHERE user_id = %s
                    AND stock_id = %s
                """, (
                    remaining_quantity,
                    order.user_id,
                    order.stock_id
                ))


            # ---------------------------------------------
            # Add money to user balance
            # ---------------------------------------------

            cursor.execute("""
                UPDATE users
                SET balance = balance + %s
                WHERE id = %s
            """, (
                total_cost,
                order.user_id
            ))


        # =================================================
        # Save order
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
            stock["price"],
            order.action
        ))


        # =================================================
        # Commit everything
        # =================================================

        connection.commit()


        return {
            "message": "Order created successfully",
            "action": order.action,
            "symbol": stock["symbol"],
            "quantity": order.quantity,
            "price": stock["price"],
            "total_value": total_cost
        }


    except HTTPException:

        connection.rollback()
        raise


    except Exception as error:

        connection.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


    finally:

        cursor.close()
        connection.close()


# =========================================================
# GET PORTFOLIO / HOLDINGS
# =========================================================

@app.get("/users/{user_id}/portfolio")
def get_portfolio(user_id: int):

    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT
                holdings.stock_id,
                stocks.symbol,
                holdings.quantity,
                holdings.average_price,
                stocks.price AS current_price,
                (
                    holdings.quantity * stocks.price
                ) AS current_value,
                (
                    (
                        stocks.price
                        - holdings.average_price
                    )
                    * holdings.quantity
                ) AS profit_loss
            FROM holdings
            JOIN stocks
                ON holdings.stock_id = stocks.id
            WHERE holdings.user_id = %s
        """, (user_id,))

        portfolio = cursor.fetchall()

        return portfolio

    finally:

        cursor.close()
        connection.close()


# =========================================================
# GET USER TRANSACTION HISTORY
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
        """, (user_id,))

        orders = cursor.fetchall()

        return orders

    finally:

        cursor.close()
        connection.close()