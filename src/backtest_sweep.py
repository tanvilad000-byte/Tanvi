import sqlite3
import pandas as pd

SHORT_WINDOWS = [3, 5, 8, 10, 15]
LONG_WINDOWS = [15, 20, 30, 50]

INSTRUMENTS = ["EURUSD", "GBPUSD", "XAUUSD"]


def load_candles(conn, instrument):
    df = pd.read_sql_query(
        "SELECT timestamp, close FROM market_candles WHERE instrument = ? ORDER BY timestamp ASC",
        conn, params=(instrument,)
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def run_strategy(df, short_window, long_window):
    df = df.copy()
    df["short_ma"] = df["close"].rolling(window=short_window).mean()
    df["long_ma"] = df["close"].rolling(window=long_window).mean()
    df["position"] = (df["short_ma"] > df["long_ma"]).astype(int)
    df["signal"] = df["position"].diff()

    trades = []
    entry_price = None
    for _, row in df.iterrows():
        if row["signal"] == 1 and entry_price is None:
            entry_price = row["close"]
        elif row["signal"] == -1 and entry_price is not None:
            pnl_pct = (row["close"] - entry_price) / entry_price * 100
            trades.append(pnl_pct)
            entry_price = None

    if not trades:
        return {"trades": 0, "win_rate": None, "total_return": 0.0}

    trades_series = pd.Series(trades)
    return {
        "trades": len(trades),
        "win_rate": (trades_series > 0).mean() * 100,
        "total_return": trades_series.sum(),
    }


def main():
    conn = sqlite3.connect("data/trading.db")

    for instrument in INSTRUMENTS:
        print(f"\n{'=' * 60}")
        print(f"{instrument}")
        print(f"{'=' * 60}")

        df = load_candles(conn, instrument)
        split_point = len(df) // 2
        train_df = df.iloc[:split_point]
        test_df = df.iloc[split_point:]

        print(f"Train period: {train_df['timestamp'].min()} to {train_df['timestamp'].max()}")
        print(f"Test period:  {test_df['timestamp'].min()} to {test_df['timestamp'].max()}")

        results = []
        for short_w in SHORT_WINDOWS:
            for long_w in LONG_WINDOWS:
                if short_w >= long_w:
                    continue
                train_result = run_strategy(train_df, short_w, long_w)
                results.append({
                    "short": short_w, "long": long_w,
                    "train_trades": train_result["trades"],
                    "train_return": train_result["total_return"],
                })

        results_df = pd.DataFrame(results).sort_values("train_return", ascending=False)
        print("\n--- All combinations, sorted by TRAIN return ---")
        print(results_df.to_string(index=False))

        best = results_df.iloc[0]
        print(f"\n--- Best on TRAIN: short={int(best['short'])}, long={int(best['long'])} ---")
        print(f"Train return: {best['train_return']:.2f}%")

        test_result = run_strategy(test_df, int(best["short"]), int(best["long"]))
        print(f"\nSame parameters on UNSEEN test data:")
        print(f"Test trades: {test_result['trades']}, Test return: {test_result['total_return']:.2f}%")

        if test_result["total_return"] <= 0:
            print("⚠️  This combination looked good on training data but LOST on unseen data.")
            print("    That's a strong sign of overfitting, not a real edge.")
        else:
            print("This combination held up on unseen data — more promising, but still")
            print("only one test period. Not enough to trust yet.")

    conn.close()


if __name__ == "__main__":
    main()
