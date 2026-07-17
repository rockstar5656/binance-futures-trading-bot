# Trading Bot — Binance Futures Testnet (USDT-M)

**Submitted for:** Primetrade.ai internship assignment
**Author:** _[your name]_ · _[your email]_ · _[your GitHub / LinkedIn]_

A structured Python CLI for placing MARKET, LIMIT, and STOP-LIMIT orders on
Binance Futures Testnet, built with a clean separation between the API
client, order logic, input validation, and CLI layers — with full
request/response/error logging to file.

**Status: verified end-to-end against the live testnet.** Both required
order types were placed successfully; real order IDs and confirmed fills
below. Happy to walk through any part of the design or trade-offs live —
reach out anytime.

---

## Proof of a working run

```
$ python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01 -y
✔ SUCCESS: Order 22266586314 placed (NEW).

$ python cli.py account
BTC: 0.01000000   ← position confirmed after the market order filled
USDT: 4999.74841560

$ python cli.py place --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.01 --price 90000 -y
✔ SUCCESS: Order 22267053257 placed (NEW).   ← resting limit order, as expected
```

Both runs are captured in full in `logs/trading_bot.log`, including the
signed request parameters (secret redacted) and raw Binance response for
each. **Before zipping this up, confirm `logs/trading_bot.log` on your
machine has both entries** — it's the log file from your own runs above,
and it's what should ship with this submission.

---

## What this demonstrates

This assignment is a small system, but it's used here as a chance to show
how I structure and validate one, not just get it running:

- **Layered architecture** — a signed REST client, an order-logic layer, a
  validation layer, and a CLI layer, each independently testable. The CLI
  never talks to Binance directly; it goes through `orders.py`, which goes
  through `client.py`.
- **67 unit tests, all passing, zero network dependency.** The signing
  logic specifically is checked against Binance's own officially-published
  HMAC-SHA256 worked example (same key, secret, and parameters as their
  docs) — see `tests/test_client.py::test_signature_matches_binance_documented_example`.
  That test is why I was confident the signing implementation was correct
  before ever making a live call.
- **Three distinct failure modes, handled differently, on purpose:**
  invalid input never reaches the network; exchange rejections are caught
  and reported cleanly with Binance's exact error code; network failures
  are treated as *unknown outcome*, not failure, since the order may have
  gone through even if the response didn't arrive. See
  [Error handling](#error-handling) below.
- **A real infrastructure discrepancy, found and resolved during testing,
  not assumed away.** Details in the next section.

---

## A debugging note worth reading

The assignment specifies `https://testnet.binancefuture.com` as the base
URL. While integrating against a real account, orders were rejected with
`-2019 Margin is insufficient` even against a freshly-funded account —
which didn't add up. Cross-checking Binance's current API documentation
directly (rather than assuming the assignment spec was still accurate)
showed the documented REST base URL for USDⓈ-M Futures testnet is actually
**`https://demo-fapi.binance.com`**, tied to Binance's newer `demo.binance.com`
account portal. The original host still resolves and *looks* like it's
working, which is what made this worth tracking down rather than shrugging
off as "flaky testnet."

Rather than hardcode either URL, `BINANCE_TESTNET_BASE_URL` is exposed as
an environment variable (see `bot/config.py`), so the fix is a one-line
`.env` change with no code touched. This is documented in
[Troubleshooting](#troubleshooting) for whoever runs this next.

---

## Project structure

```
trading_bot/
  bot/
    client.py          # Signed REST client — HMAC-SHA256 signing, request/response logging
    orders.py           # Order placement logic — translates validated input into API calls
    validators.py       # CLI input validation (runs before any network call)
    logging_config.py   # Console (INFO+) + rotating file (DEBUG+) logging
    exceptions.py        # ValidationError / BinanceAPIError / NetworkError hierarchy
    config.py           # Credential + base-URL loading from environment
  cli.py                 # CLI entry point (Click) — place / account / price commands
  tests/                 # 67 pytest tests, fully mocked, no network required
  logs/                  # trading_bot.log — request/response/error log
  requirements.txt
  pyproject.toml
  .env.example
```

---

## Setup

**1. Prerequisites** — Python 3.10+, a Binance account (no verification
needed for testnet/demo trading).

**2. Get API credentials**
Go to the Futures Testnet / Demo Trading API management page for your
account and generate an HMAC key pair with **Enable Futures** checked.
Copy both the API Key and Secret — the secret is typically shown once.

> Binance currently has more than one "testnet-like" product (classic
> Futures Testnet vs. the newer Demo Trading portal at `demo.binance.com`).
> Whichever you use, the corresponding base URL goes in `.env` — see
> [Troubleshooting](#troubleshooting) if orders fail immediately after setup.

**3. Install**
```bash
git clone <repo-url>
cd trading_bot
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**4. Configure credentials**
```bash
cp .env.example .env
```
Edit `.env`:
```
BINANCE_TESTNET_API_KEY=your_key_here
BINANCE_TESTNET_API_SECRET=your_secret_here

# Only needed if the default host 404s or auths fail for your account —
# see Troubleshooting.
# BINANCE_TESTNET_BASE_URL=https://demo-fapi.binance.com
```
`.env` is gitignored. Never commit real keys.

**5. Verify connectivity**
```bash
python cli.py account
```
A nonzero balance confirms the key, secret, and base URL are all correct.

---

## Usage

**Market order**
```bash
python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01
```
Prints a request summary, asks for confirmation, then prints the response
(`orderId`, `status`, `executedQty`, `avgPrice`). Add `-y` to skip the
confirmation prompt for scripting.

**Limit order**
```bash
python cli.py place --symbol BTCUSDT --side SELL --type LIMIT \
  --quantity 0.01 --price 90000 --time-in-force GTC -y
```
`--price` is required and validated before any network call is made.

**Stop-limit order** *(bonus — third order type)*
```bash
python cli.py place --symbol BTCUSDT --side BUY --type STOP_LIMIT \
  --quantity 0.01 --price 65000 --stop-price 64500 -y
```
Maps to Binance's `STOP` order type internally (a stop order that fills as
a limit order once triggered — see [Assumptions](#assumptions)).

**Other commands**
```bash
python cli.py account                    # balances / positions
python cli.py price --symbol BTCUSDT     # current mark price
python cli.py --verbose place ...        # stream DEBUG logs to console too
python cli.py place --help               # full flag reference
```

---

## Error handling

| Failure | Example | Where it's caught | Result |
|---|---|---|---|
| Invalid input | negative quantity, missing `--price` on a LIMIT order | `bot/validators.py`, before any network call | Clean message, exit code 1, logged at `WARNING` |
| Exchange rejection | insufficient margin, invalid symbol | `bot/orders.py`, after Binance responds | Binance's exact code + message printed and logged at `ERROR` |
| Network failure | timeout, DNS failure, connection refused | Propagates as `NetworkError` | CLI reports the outcome as *unknown* (order may have gone through) rather than assuming failure, and points to `account` to check |

Three separate exception types (`ValidationError`, `BinanceAPIError`,
`NetworkError`) back this, so each layer only ever catches what it knows
how to handle — see `bot/exceptions.py`.

---

## Testing

```bash
pip install pytest
python -m pytest tests/ -v
```
67 tests, fully mocked — no network access needed to verify the request
signing, order-parameter translation, and error-handling logic. Notably,
the signing test reproduces Binance's own documented HMAC example verbatim
and asserts an exact signature match, which is how the signing
implementation was validated correct *before* the first live call was made
against a real account.

---

## Assumptions

- **`STOP_LIMIT` maps to Binance's `STOP` type.** There's no literal
  `STOP_LIMIT` order type on Binance Futures — a stop order that fills as a
  limit order once triggered is `STOP` (vs. `STOP_MARKET`). The CLI uses
  the clearer name and translates internally.
- **`timeInForce` defaults to `GTC`** for LIMIT/STOP_LIMIT orders, matching
  Binance's own default.
- **Quantities and prices are `Decimal`, never `float`**, end to end —
  floating-point rounding could silently corrupt the signed query string.
- **`--price` is rejected outright on MARKET orders**, not silently
  ignored, on the assumption that supplying it was a mistake worth
  surfacing rather than swallowing.
- **One-way position mode is assumed** (no `positionSide` handling). Hedge
  mode accounts would need this added.
- **Leverage / margin type are not configured by this tool** — it assumes
  they're already set for the symbol via the web UI or a separate call.
- **Credentials come from environment variables**, never CLI arguments, to
  avoid leaking secrets into shell history.

---

## Troubleshooting

**Orders fail immediately, or `account` shows all zeros despite a funded account**
Your API key may belong to a different host than the one the client is
targeting. Set `BINANCE_TESTNET_BASE_URL` in `.env`:
```
BINANCE_TESTNET_BASE_URL=https://demo-fapi.binance.com
```
See [A debugging note worth reading](#a-debugging-note-worth-reading) above
for why this can happen.

**`-1021 Timestamp for this request is outside of the recvWindow`**
Local clock drift beyond Binance's 5-second signing window. Force a
resync: `sudo sntp -sS time.apple.com` (macOS) or enable automatic time
sync in system settings.

**`-2019 Margin is insufficient`**
Balance too low for the order size at current leverage. Reduce quantity or
top up the virtual balance via the account portal.

**`-1121 Invalid symbol`**
Confirm it's a valid USDT-M perpetual, e.g. `BTCUSDT` — not `BTC-USDT`.

**`Configuration error: Missing required environment variable(s)`**
Confirm the file is named `.env`, not `.env.example` — the app only reads
`.env`.