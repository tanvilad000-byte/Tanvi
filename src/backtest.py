import sqlite3
import pandas as pd

SHORT_WINDOW = 5
LONG_WINDOW = 20

INSTRUMENTS = ["EURUSD", "GBPUSD", "XAUUSD"]


def load_candles(conn, instrument):
    df = pd.read_sql_query(
        "SELECT timestamp, close FROM market_candles WHERE instrument = ? ORDER BY timestamp ASC",
        conn, params=(instrument,)
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def apply_moving_average_strategy(df):
    df = df.copy()
    df["short_ma"] = df["close"].rolling(window=SHORT_WINDOW).mean()
    df["long_ma"] = df["close"].rolling(window=LONG_WINDOW).mean()

    # A signal only exists once both averages have enough data to be real
    df["position"] = 0
    df.loc[df["short_ma"] > df["long_ma"], "position"] = 1   # want to be "in" (bought)
    df.loc[df["short_ma"] <= df["long_ma"], "position"] = 0  # want to be "out" (sold/waiting)

    # A trade happens whenever position changes from the previous row
    df["signal"] = df["position"].diff()
    # signal ==  1 means we just crossed UP  -> BUY
    # signal == -1 means we just crossed DOWN -> SELL
    return df


def simulate_trades(df):
    trades = []
    entry_price = None
    entry_time = None

    for _, row in df.iterrows():
        if row["signal"] == 1 and entry_price is None:
            entry_price = row["close"]
            entry_time = row["timestamp"]
        elif row["signal"] == -1 and entry_price is not None:
            exit_price = row["close"]
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            trades.append({
                "entry_time": entry_time, "exit_time": row["timestamp"],
                "entry_price": entry_price, "exit_price": exit_price,
                "pnl_pct": pnl_pct,
            })
            entry_price = None
            entry_time = None

    return pd.DataFrame(trades)


def report_results(instrument, trades_df):
    print(f"\n=== {instrument} ===")
    if trades_df.empty:
        print("No completed trades in this period.")
        return

    total_trades = len(trades_df)
    winning_trades = (trades_df["pnl_pct"] > 0).sum()
    win_rate = winning_trades / total_trades * 100
    total_return_pct = trades_df["pnl_pct"].sum()
    avg_return_per_trade = trades_df["pnl_pct"].mean()

    print(f"Total trades:        {total_trades}")
    print(f"Win rate:            {win_rate:.1f}%")
    print(f"Total return:        {total_return_pct:.2f}% (sum of all trades, no compounding)")
    print(f"Avg return/trade:    {avg_return_per_trade:.3f}%")
    print(f"Best trade:          {trades_df['pnl_pct'].max():.3f}%")
    print(f"Worst trade:         {trades_df['pnl_pct'].min():.3f}%")


def main():
    conn = sqlite3.connect("data/trading.db")

    print("=" * 50)
    print(f"MOVING AVERAGE CROSSOVER BACKTEST")
    print(f"Short window: {SHORT_WINDOW}h | Long window: {LONG_WINDOW}h")
    print("=" * 50)
    print("NOTE: this is a simple historical simulation. It does NOT account for")
    print("spread, slippage, or fees — real results would be worse than shown here.")

    for instrument in INSTRUMENTS:
        df = load_candles(conn, instrument)
        df = apply_moving_average_strategy(df)
        trades_df = simulate_trades(df)
        report_results(instrument, trades_df)

    conn.close()


if __name__ == "__main__":
    main()
