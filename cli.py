from __future__ import annotations

import sys

import click

from bot.client import BinanceFuturesTestnetClient
from bot.config import load_credentials
from bot.exceptions import (
    BinanceAPIError,
    ConfigurationError,
    NetworkError,
    TradingBotError,
    ValidationError,
)
from bot.logging_config import get_logger, setup_logging
from bot.orders import place_order
from bot.validators import build_order_request

logger = get_logger("cli")


def _get_client() -> BinanceFuturesTestnetClient:
    """Load credentials and construct the API client, or exit cleanly."""
    try:
        api_key, api_secret, base_url = load_credentials()
    except ConfigurationError as exc:
        click.secho(f"Configuration error: {exc}", fg="red", err=True)
        logger.error("Configuration error: %s", exc)
        sys.exit(1)
    return BinanceFuturesTestnetClient(api_key, api_secret, base_url=base_url)


def _print_request_summary(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str,
    price: str | None,
    stop_price: str | None,
    time_in_force: str,
) -> None:
    click.secho("\n--- Order Request Summary ---", bold=True)
    click.echo(f"  Symbol:         {symbol}")
    click.echo(f"  Side:           {side}")
    click.echo(f"  Type:           {order_type}")
    click.echo(f"  Quantity:       {quantity}")
    if price:
        click.echo(f"  Price:          {price}")
    if stop_price:
        click.echo(f"  Stop Price:     {stop_price}")
    if order_type in ("LIMIT", "STOP_LIMIT"):
        click.echo(f"  Time In Force:  {time_in_force}")
    click.echo("")


def _print_order_result(result) -> None:
    if result.success:
        click.secho("--- Order Response ---", bold=True)
        click.echo(f"  Order ID:       {result.order_id}")
        click.echo(f"  Symbol:         {result.symbol}")
        click.echo(f"  Status:         {result.status}")
        click.echo(f"  Side:           {result.side}")
        click.echo(f"  Type:           {result.order_type}")
        click.echo(f"  Executed Qty:   {result.executed_qty}")
        click.echo(f"  Original Qty:   {result.orig_qty}")
        if result.avg_price is not None:
            click.echo(f"  Avg Price:      {result.avg_price}")
        if result.price:
            click.echo(f"  Price:          {result.price}")
        click.echo("")
        click.secho(
            f"✔ SUCCESS: Order {result.order_id} placed ({result.status}).",
            fg="green",
            bold=True,
        )
    else:
        click.echo("")
        click.secho(
            f"✘ FAILURE: Order was rejected -- {result.error_message}",
            fg="red",
            bold=True,
        )


@click.group()
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Print DEBUG-level logs to the console (full detail always goes to the log file regardless).",
)
def cli(verbose: bool) -> None:
    """
    Simplified Trading Bot -- place orders on Binance Futures Testnet (USDT-M).

    All requests, responses, and errors are logged to logs/trading_bot.log
    regardless of console verbosity.
    """
    import logging

    logger_obj = setup_logging(level=logging.DEBUG)
    if verbose:
        # Bump the console handler (index 1, the file handler is index 0)
        # up to DEBUG too, for troubleshooting.
        for handler in logger_obj.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.FileHandler
            ):
                handler.setLevel(logging.DEBUG)


@cli.command()
@click.option("--symbol", required=True, help="Trading pair, e.g. BTCUSDT")
@click.option(
    "--side",
    required=True,
    type=click.Choice(["BUY", "SELL"], case_sensitive=False),
    help="Order side.",
)
@click.option(
    "--type",
    "order_type",
    required=True,
    type=click.Choice(["MARKET", "LIMIT", "STOP_LIMIT"], case_sensitive=False),
    help="Order type.",
)
@click.option("--quantity", required=True, help="Order quantity (base asset units).")
@click.option(
    "--price",
    default=None,
    help="Limit price. Required for LIMIT and STOP_LIMIT orders.",
)
@click.option(
    "--stop-price",
    default=None,
    help="Stop trigger price. Required for STOP_LIMIT orders.",
)
@click.option(
    "--time-in-force",
    default="GTC",
    type=click.Choice(["GTC", "IOC", "FOK"], case_sensitive=False),
    help="Time in force for LIMIT/STOP_LIMIT orders (default: GTC).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt.",
)
def place(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str,
    price: str | None,
    stop_price: str | None,
    time_in_force: str,
    yes: bool,
) -> None:
    """Validate input and place a MARKET, LIMIT, or STOP_LIMIT order."""
    try:
        request = build_order_request(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
        )
    except ValidationError as exc:
        click.secho(f"Invalid input: {exc}", fg="red", err=True)
        logger.warning("CLI validation failed: %s", exc)
        sys.exit(1)

    _print_request_summary(
        request.symbol,
        request.side,
        request.order_type,
        str(request.quantity),
        str(request.price) if request.price else None,
        str(request.stop_price) if request.stop_price else None,
        request.time_in_force,
    )

    if not yes:
        if not click.confirm("Submit this order to Binance Futures Testnet?"):
            click.echo("Cancelled.")
            logger.info("Order cancelled by user before submission.")
            return

    client = _get_client()

    try:
        result = place_order(client, request)
    except NetworkError as exc:
        click.secho(f"Network error: {exc}", fg="red", err=True)
        click.secho(
            "The order may or may not have reached Binance -- check the "
            "'account' command or Binance testnet UI before retrying.",
            fg="yellow",
        )
        sys.exit(1)
    except BinanceAPIError as exc:
        # Shouldn't normally reach here (place_order catches this), but
        # kept as a safety net so no exchange error ever surfaces as a
        # raw traceback.
        click.secho(f"Binance API error [{exc.code}]: {exc.msg}", fg="red", err=True)
        sys.exit(1)

    _print_order_result(result)

    if not result.success:
        sys.exit(1)


@cli.command()
def account() -> None:
    """Fetch and display Futures Testnet account balances/positions."""
    client = _get_client()
    try:
        info = client.get_account_info()
    except NetworkError as exc:
        click.secho(f"Network error: {exc}", fg="red", err=True)
        sys.exit(1)
    except BinanceAPIError as exc:
        click.secho(f"Binance API error [{exc.code}]: {exc.msg}", fg="red", err=True)
        sys.exit(1)

    click.secho("--- Account Overview ---", bold=True)
    click.echo(f"  Total Wallet Balance:      {info.get('totalWalletBalance')}")
    click.echo(f"  Total Unrealized Profit:   {info.get('totalUnrealizedProfit')}")
    click.echo(f"  Total Margin Balance:      {info.get('totalMarginBalance')}")
    click.echo(f"  Available Balance:         {info.get('availableBalance')}")

    non_zero_assets = [
        a for a in info.get("assets", []) if float(a.get("walletBalance", 0)) != 0
    ]
    if non_zero_assets:
        click.secho("\n  Non-zero asset balances:", bold=True)
        for asset in non_zero_assets:
            click.echo(
                f"    {asset['asset']}: {asset['walletBalance']}"
            )


@cli.command()
@click.option("--symbol", required=True, help="Trading pair, e.g. BTCUSDT")
def price(symbol: str) -> None:
    """Fetch the current mark price for a symbol (useful for sanity-checking before a LIMIT order)."""
    try:
        symbol = symbol.strip().upper()
    except AttributeError:
        pass

    client = _get_client()
    try:
        result = client.get_symbol_price(symbol)
    except NetworkError as exc:
        click.secho(f"Network error: {exc}", fg="red", err=True)
        sys.exit(1)
    except BinanceAPIError as exc:
        click.secho(f"Binance API error [{exc.code}]: {exc.msg}", fg="red", err=True)
        sys.exit(1)

    click.echo(f"{result.get('symbol')}: {result.get('price')}")


def main() -> None:
    """
    Top-level entry point wrapping the Click CLI with a catch-all handler.

    Ensures that any TradingBotError (or truly unexpected exception) that
    slips past the per-command handlers is logged and reported cleanly,
    rather than dumping a raw Python traceback on the user.
    """
    try:
        cli()
    except TradingBotError as exc:
        logger.error("Unhandled application error: %s", exc)
        click.secho(f"Error: {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 -- final safety net by design
        logger.exception("Unexpected error")
        click.secho(f"Unexpected error: {exc}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
