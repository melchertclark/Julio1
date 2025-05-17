# Julio1

This project is a FastAgent example.

## Setup

1.  Install dependencies: `pip install -r requirements.txt` (Assuming a requirements.txt will be created)
2.  Configure `fastagent.config.yaml` and `fastagent.secrets.yaml`.
3.  Run the agent: `python agent.py`

## Usage

The agent is defined in `agent.py`. It includes an agent named "url_fetcher" with the following functionality:
"Given a URL, list the first 10 urls in the page, and then fetch the content of the first 3 urls. return the content of those urls in full."

It uses servers defined in `fastagent.config.yaml` under the name "fetch". 