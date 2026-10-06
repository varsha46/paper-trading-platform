import { useEffect, useState } from "react";
import "./App.css";
const API_URL = "/api";

function App() {
  const [balance, setBalance] = useState(null);
  const [stocks, setStocks] = useState([]);
  const [portfolio, setPortfolio] = useState([]);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
const [message, setMessage] = useState("");
const [messageType, setMessageType] = useState("");
const [quantities, setQuantities] = useState({});

  const loadDashboard = () => {
  fetch(`${API_URL}/users/1/balance`)
    .then((response) => response.json())
    .then((data) => setBalance(data.balance));

  fetch(`${API_URL}/stocks`)
    .then((response) => response.json())
    .then((data) => setStocks(data));

  fetch(`${API_URL}/users/1/portfolio`)
    .then((response) => response.json())
    .then((data) => setPortfolio(data));

  fetch(`${API_URL}/users/1/orders`)
    .then((response) => response.json())
    .then((data) => setOrders(data));
};

  useEffect(() => {

  // Load dashboard initially
  loadDashboard();

  // Connect to FastAfetch(`${API_URL}/users/1/orders`)PI WebSocket
  const socket = new WebSocket(
    `ws://${window.location.host}/ws/prices`
  );

  socket.onopen = () => {
    console.log("WebSocket connected");
  };

  socket.onmessage = (event) => {

    const data = JSON.parse(event.data);

    console.log("Price update received:", data);

    if (data.type === "price_update") {

      setStocks((currentStocks) =>
        currentStocks.map((stock) => {

          const updatedStock = data.stocks.find(
            (item) => item.symbol === stock.symbol
          );

          if (updatedStock) {
            return {
              ...stock,
              price: updatedStock.new_price
            };
          }

          return stock;
        })
      );

      // Reload portfolio so current value and P&L
      // also use the latest stock price.
      fetch(`${API_URL}/users/1/portfolio`)
        .then((response) => response.json())
        .then((data) => setPortfolio(data));
    }
  };

  socket.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  socket.onclose = () => {
    console.log("WebSocket disconnected");
  };

  // Close WebSocket when React component is removed
  return () => {
    socket.close();
  };

}, []);

  const placeOrder = (stockId, action) => {
  setLoading(true);
  setMessage("");
  setMessageType("");

  fetch(`${API_URL}/orders`,  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_id: 1,
      stock_id: stockId,
      quantity: quantities[stockId] || 1,
      action: action,
    }),
  })
    .then(async (response) => {
      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Order failed"
        );
      }

      return data;
    })
    .then((data) => {
      setMessage(
        `${action === "BUY" ? "Bought" : "Sold"} ${
          data.quantity
        } ${data.symbol} shares at ₹${data.price}`
      );

      setMessageType("success");

      loadDashboard();

      setTimeout(() => {
        setMessage("");
        setMessageType("");
      }, 3000);
    })
    .catch((error) => {
      setMessage(error.message);
      setMessageType("error");

      setTimeout(() => {
        setMessage("");
        setMessageType("");
      }, 3000);
    })
    .finally(() => {
      setLoading(false);
    });
};

  return (
    <div className="app">

      {/* Header */}
      <header className="header">
        <div>
          <h1>PaperTrade</h1>
          <p>Paper Trading Dashboard</p>
        </div>

        <div className="user-badge">
          👤 Varsha
        </div>
      </header>


      {/* Main Content */}
      <main className="container">

        {/* Summary Cards */}
        <section className="summary-grid">

  {/* Available Balance */}
  <div className="summary-card">
    <span>Available Balance</span>

    <h2>
      ₹{balance ?? "Loading..."}
    </h2>

    <small>Cash available for trading</small>
  </div>


  {/* Holdings */}
  <div className="summary-card">
    <span>Holdings</span>

    <h2>
      {portfolio.reduce(
        (total, item) => total + item.quantity,
        0
      )}
    </h2>

    <small>Total shares owned</small>
  </div>


  {/* Holdings Value */}
  <div className="summary-card">
    <span>Holdings Value</span>

    <h2>
  ₹
  {portfolio
    .reduce(
      (total, item) =>
        total + Number(item.current_value),
      0
    )
    .toFixed(2)}
</h2>

    <small>Current market value</small>
  </div>


  {/* Total Account Value */}
  <div className="summary-card">
    <span>Total Account Value</span>

    <h2>
      ₹
      {(
        Number(balance || 0) +
        portfolio.reduce(
          (total, item) =>
            total + Number(item.current_value),
          0
        )
      ).toFixed(2)}
    </h2>

    <small>Cash + holdings</small>
  </div>

</section>


        {/* Message */}
        {message && (
  <div className={`message ${messageType}`}>
    {message}
  </div>
)}


        {/* Market */}
<section className="section-card">

  <div className="section-header">
    <div>
      <h2>Market</h2>
      <p>Available stocks</p>
    </div>
  </div>

  <div className="stock-list">

    {stocks.map((stock) => {

      const holding = portfolio.find(
        (item) => item.stock_id === stock.id
      );

      const ownedQuantity = holding
        ? holding.quantity
        : 0;

      const selectedQuantity =
        quantities[stock.id] || 1;

      const cannotSell =
        selectedQuantity > ownedQuantity;

      return (
        <div
          className="stock-row"
          key={stock.id}
        >

          {/* Stock Information */}
          <div className="stock-info">

            <div className="stock-icon">
              {stock.symbol.charAt(0)}
            </div>

            <div>
              <strong>
                {stock.symbol}
              </strong>

              <span>
                Indian Equity
              </span>

              <small className="owned-shares">
                Owned: {ownedQuantity}
              </small>
            </div>

          </div>


          {/* Stock Price */}
          <div className="stock-price">
            ₹{stock.price}
          </div>


          {/* Quantity + Buttons */}
          <div className="stock-actions">

            <input
              type="number"
              min="1"
              value={
                quantities[stock.id] || 1
              }
              onChange={(event) => {

                const value =
                  Number(event.target.value);

                if (value >= 1) {
                  setQuantities({
                    ...quantities,
                    [stock.id]: value,
                  });
                }

              }}
            />


            {/* BUY */}
            <button
              className="buy-btn"
              disabled={loading}
              onClick={() =>
                placeOrder(
                  stock.id,
                  "BUY"
                )
              }
            >
              {loading ? "..." : "BUY"}
            </button>


            {/* SELL */}
            <button
              className="sell-btn"
              disabled={
                loading ||
                cannotSell
              }
              onClick={() =>
                placeOrder(
                  stock.id,
                  "SELL"
                )
              }
            >
              {loading ? "..." : "SELL"}
            </button>

          </div>

        </div>
      );

    })}

  </div>

</section>


        {/* Portfolio */}
        <section className="section-card">

          <div className="section-header">
            <div>
              <h2>My Portfolio</h2>
              <p>Your current holdings</p>
            </div>
          </div>


          {portfolio.length === 0 ? (

            <div className="empty-state">
              No holdings yet.
            </div>

          ) : (

            <div className="table-container">

              <table>

                <thead>
                  <tr>
                    <th>Stock</th>
                    <th>Quantity</th>
                    <th>Average Price</th>
                    <th>Current Value</th>
                    <th>P&L</th>
                  </tr>
                </thead>


                <tbody>

                  {portfolio.map((holding) => (

                    <tr
                      key={holding.stock_id}
                    >

                      <td>
                        <strong>
                          {holding.symbol}
                        </strong>
                      </td>


                      <td>
                        {holding.quantity}
                      </td>


                      <td>
                        ₹{holding.average_price}
                      </td>


                      <td>
                        ₹{holding.current_value}
                      </td>


                      <td
                        className={
                          Number(
                            holding.pnl
                          ) >= 0
                            ? "profit"
                            : "loss"
                        }
                      >
                        ₹{holding.pnl}
                      </td>

                    </tr>

                  ))}

                </tbody>

              </table>

            </div>

          )}

        </section>


        {/* Transaction History */}
        <section className="section-card">

          <div className="section-header">
            <div>
              <h2>Transaction History</h2>
              <p>Your recent orders</p>
            </div>
          </div>


          <div className="table-container">

            <table>

              <thead>
                <tr>
                  <th>Action</th>
                  <th>Stock</th>
                  <th>Quantity</th>
                  <th>Price</th>
                </tr>
              </thead>


              <tbody>

                {orders
                  .slice(0, 10)
                  .map((order) => (

                    <tr key={order.id}>

                      <td>

                        <span
                          className={
                            order.action === "BUY"
                              ? "badge buy-badge"
                              : "badge sell-badge"
                          }
                        >
                          {order.action}
                        </span>

                      </td>


                      <td>
                        {order.symbol}
                      </td>


                      <td>
                        {order.quantity}
                      </td>


                      <td>
                        ₹{order.price}
                      </td>

                    </tr>

                  ))}

              </tbody>

            </table>

          </div>

        </section>

      </main>

    </div>
  );
}

export default App;