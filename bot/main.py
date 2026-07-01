from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from itertools import product
from typing import Dict, Any

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.backtest.engine import BacktestEngine
from bot.core.utils import get_logger
from bot.webhook_server import run_webhook_server


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value)


def run_backtest(args) -> None:
    config = load_config(args.config)
    symbols = config["symbols"]
    if args.symbols:
        wanted = set(args.symbols.split(","))
        symbols = [s for s in symbols if s["symbol"] in wanted]

    engine = BacktestEngine(config)
    result = engine.run(symbols, parse_date(args.start), parse_date(args.end), args.tf)

    print("Backtest Metrics")
    for k, v in result.metrics.items():
        print(f"{k}: {v}")
    print(f"Trades: {len(result.trades)}")


def run_trade(args) -> None:
    config = load_config(args.config)
    enable_live = config["broker"].get("enable_live_trading", False)
    env_flag = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
    if args.mode != "paper" and (not enable_live or not env_flag):
        raise SystemExit("Live trading blocked. Set ENABLE_LIVE_TRADING=true and enable_live_trading in config.")

    logger = get_logger("trade")
    logger.info("paper_trade_start")
    # For now, reuse backtest engine as a replayable paper runner.
    symbols = config["symbols"]
    if args.symbols:
        wanted = set(args.symbols.split(","))
        symbols = [s for s in symbols if s["symbol"] in wanted]
    engine = BacktestEngine(config)
    result = engine.run(symbols, parse_date(args.start), parse_date(args.end), args.tf)
    print("Paper trade complete")
    for k, v in result.metrics.items():
        print(f"{k}: {v}")


def run_optimize(args) -> None:
    config = load_config(args.config)
    opt = config.get("optimize", {})
    if not opt:
        raise SystemExit("No optimize grid defined in config")

    params = opt.get("params", {})
    if not params:
        raise SystemExit("No optimize params defined")

    keys = list(params.keys())
    values = [params[k] for k in keys]
    best = None
    best_score = float("-inf")

    for combo in product(*values):
        for k, v in zip(keys, combo):
            config["strategy"][k] = v
        engine = BacktestEngine(config)
        result = engine.run(config["symbols"], parse_date(args.start), parse_date(args.end), args.tf)
        score = result.metrics.get(opt.get("metric", "total_pnl"), 0.0)
        if score > best_score:
            best_score = score
            best = {k: v for k, v in zip(keys, combo)}

    print("Best params:")
    print(best)
    print(f"Best score: {best_score}")


def run_webhook(args) -> None:
    config = load_config(args.config)
    config.setdefault("webhook", {})
    if args.execute:
        config["webhook"]["execute_orders"] = True
    run_webhook_server(config, host=args.host, port=args.port)


def main() -> None:
    parser = argparse.ArgumentParser(prog="bot")
    parser.add_argument("--config", default="bot/config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    backtest = sub.add_parser("backtest")
    backtest.add_argument("--symbols", default="")
    backtest.add_argument("--start", required=True)
    backtest.add_argument("--end", required=True)
    backtest.add_argument("--tf", default="1m")

    trade = sub.add_parser("trade")
    trade.add_argument("--mode", default="paper")
    trade.add_argument("--symbols", default="")
    trade.add_argument("--start", required=True)
    trade.add_argument("--end", required=True)
    trade.add_argument("--tf", default="1m")

    optimize = sub.add_parser("optimize")
    optimize.add_argument("--start", required=True)
    optimize.add_argument("--end", required=True)
    optimize.add_argument("--tf", default="1m")

    webhook = sub.add_parser("webhook")
    webhook.add_argument("--host", default="127.0.0.1")
    webhook.add_argument("--port", type=int, default=8080)
    webhook.add_argument(
        "--execute",
        action="store_true",
        help="Arm paper order submission. Also requires VELEZ_EXECUTE_ORDERS=true.",
    )

    args = parser.parse_args()
    if args.command == "backtest":
        run_backtest(args)
    elif args.command == "trade":
        run_trade(args)
    elif args.command == "optimize":
        run_optimize(args)
    elif args.command == "webhook":
        run_webhook(args)


if __name__ == "__main__":
    main()
