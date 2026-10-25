"""The API keys: where they are read, and what is done with them.

PESTO needs the API key of each model provider a run calls: an Anthropic key by
default, an OpenAI key when a model is named `openai:...` (a run asks only for
the keys of the providers it uses). It can also use an NCBI key that raises the
PubMed rate limit from 3 to 10 requests a second. All are read here and nowhere
else, from either of:

  - the environment variables ANTHROPIC_API_KEY, OPENAI_API_KEY and NCBI_API_KEY;
  - a .env file you wrote yourself in the PESTO data directory
    (~/.local/share/pesto/.env, or $PESTO_PROJECT_ROOT/.env when that is set).
    A variable already set in the shell wins over the file.

`pesto browser` also accepts either key pasted in its page. It is then held in
the memory of that process until it stops (browser/server.py), like a key read
from the environment, and is handled exactly as below.

PESTO never writes a key to disk, never prints it, and never records it in a
saved run. The Anthropic key is handed to the official `anthropic` client in
services/providers/anthropic_provider.py, which sends it to api.anthropic.com
and nowhere else; the OpenAI key to the official `openai` client in
services/providers/openai_provider.py, which sends it to api.openai.com only.
The NCBI key is sent to eutils.ncbi.nlm.nih.gov as the `api_key` parameter NCBI
asks for, in services/pubmed_service.py. Those files are the whole audit.
"""
import os

from dotenv import load_dotenv

_loaded = False


def _load():
    global _loaded
    if not _loaded:
        from .config import PROJECT_ROOT
        load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)
        _loaded = True


def api_key(env_var):
    """The key held in this environment variable (or in .env), or None."""
    _load()
    return os.environ.get(env_var) or None


def anthropic_api_key():
    return api_key("ANTHROPIC_API_KEY")


def openai_api_key():
    return api_key("OPENAI_API_KEY")


def ncbi_api_key():
    _load()
    return os.environ.get("NCBI_API_KEY") or None
