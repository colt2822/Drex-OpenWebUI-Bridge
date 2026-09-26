# Drex Chat for OpenWebUI

Drex Chat for OpenWebUI lets you use Nace.AI Drex from normal chat prompts. Instead of manually writing Drex's typed API payloads, type an ordinary closed-decision question. The bridge converts it into a validated Drex request and formats the result as a readable answer with confidence and probabilities.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![OpenWebUI](https://img.shields.io/badge/OpenWebUI-OpenAI--compatible-purple)

## Demo

**You:**

> My central air conditioner is running, but the house is still 82 degrees and the vents are blowing warm air. The plumbing and lights are working normally.
>
> Which service category best fits this request: HVAC, plumbing, electrical, or something else?

**Drex Chat:**

```text
Selected: HVAC
Decision confidence: 98.0%

Probability distribution:
- HVAC: 98.5%
- something else: 1.2%
- electrical: 0.3%
- plumbing: <0.1%
```

This output came from an actual integration test. Results vary by request; these exact probabilities are not guaranteed.

## Why

The native Drex API accepts typed, structured decision requests. OpenWebUI users expect to type a normal prompt. Drex Chat bridges those interfaces so users do not have to write JSON.

## How it works

```text
OpenWebUI → Drex Chat → deterministic parser → typed Drex request
          → Nace.AI Drex → deterministic formatter → readable answer
```

No second language model is used to translate prompts. The supported explicit-choice path is parsed and formatted locally.

## Features

- Normal English input; no manual JSON
- Human-readable selected option, decision confidence, and probability distribution
- Deterministic local parsing and formatting
- No additional LLM for supported explicit-choice prompts
- Validated provider responses and safely sanitized API errors
- OpenAI-compatible chat completions endpoint for OpenWebUI

## Requirements

- Python 3.10 or newer
- OpenWebUI 0.11.1 (tested)
- A Nace.AI Drex API key

## Installation

This project runs as a small OpenAI-compatible server. Add it in OpenWebUI as an OpenAI connection.

1. Clone this repository and install its dependencies:

   ```sh
   git clone https://github.com/colt2822/Drex-OpenWebUI-Bridge.git
   cd Drex-OpenWebUI-Bridge
   python -m venv .venv
   . .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -e .
   ```

2. Set the Drex key in the server environment. For local development, copy `.env.example` to `.env` and load it with your preferred environment manager. The bridge itself reads `DREX_API_KEY` from its process environment; it does not automatically load `.env`.

   ```sh
   export DREX_API_KEY='your_drex_api_key_here'
   ```

3. Start the bridge. It binds to the loopback interface by default:

   ```sh
   drex-chat-bridge
   ```

   The API is available at `http://127.0.0.1:8000/v1`.

   If OpenWebUI runs in Docker, the bridge must listen on an interface Docker can reach. Configure both a bridge key and a reachable bind address before starting it:

   ```sh
   export BRIDGE_API_KEY='choose-a-long-random-value'
   HOST=0.0.0.0 drex-chat-bridge
   ```

   Restrict port 8000 to the OpenWebUI host or private container network with your firewall. Do not expose it directly to the public internet.

4. In OpenWebUI, open **Admin Panel → Settings → Connections → OpenAI Connections**, choose **Add Connection**, and enter:

   - **URL:** `http://host.docker.internal:8000/v1` when OpenWebUI runs in Docker on the same host; otherwise use the bridge host address reachable from OpenWebUI.
   - **API key:** use the same value as `BRIDGE_API_KEY` when configured. This is required for the Docker setup above.

   Save, then choose **Drex Chat** from the model picker. If OpenWebUI is itself running directly on the host, use `http://127.0.0.1:8000/v1`.

Do not expose the bridge directly to the public internet. For remote or shared deployments, put it behind a TLS reverse proxy and configure `BRIDGE_API_KEY`.

## Configuration

Required:

```dotenv
DREX_API_KEY=your_drex_api_key_here
```

Optional:

```dotenv
BRIDGE_API_KEY=                   # Require matching Bearer auth from OpenWebUI
HOST=127.0.0.1
PORT=8000
```

`DREX_API_KEY` stays on the server. The bridge does not send it to the browser or include it in logs or error messages. `.env` is excluded from Git.

## Usage

Ask a closed question and state the alternatives clearly:

- “Which database should I choose for a local embedded application: SQLite, PostgreSQL, MySQL, or MongoDB?”
- “A customer says the AC is blowing warm air. Is this HVAC, plumbing, electrical, or something else?”
- “Which deployment option should I use: local, cloud, or hybrid? I need low latency but centralized backups.”

## Supported prompts

Version 1 supports explicit-choice decisions with two or more options. The parser extracts labels from a final choice list after a colon or from a few recognized choice phrases. It preserves the full prompt as decision context and normalizes option identifiers internally, then restores the labels in the answer.

## Current limitations

- Designed for closed decisions, not general-purpose chat.
- State your alternatives explicitly; ambiguous requests are answered with concise guidance to add choices.
- Essay writing, coding, summaries, and research are not routed to another model.
- Yes/no, ranking, and scoring prompts are not supported.
- The bridge shows choice confidence and probabilities; other Drex question types are not exposed.
- This parser is deliberately small and deterministic. It may reject valid phrasings it does not recognize.

## Development

```sh
pip install -e '.[test]'
pytest
```

Provider tests use mocks; the test suite does not call the paid Drex API. Run the server locally with `uvicorn drex_chat.app:app --reload`.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

Unofficial community integration for Nace.AI Drex and OpenWebUI. Drex is a product of Nace.AI. OpenWebUI is a separate project. This repository is not an official Nace.AI or OpenWebUI project unless they later explicitly endorse it.
