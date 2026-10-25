"""What every model provider has in common.

PESTO talks to a model in one way: a prompt goes in, text and token counts come
out. A provider adapter is the only code that knows how a vendor's API wants
that done (its client, its parameters, its retries, how it reports being cut
off), and it hands back an `LLMResult`. Nothing past this module, the flow
blocks, the parsers, scoring, ever sees a vendor's response object or a vendor's
words for why a model stopped.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

# Why a model stopped, in PESTO's words. An adapter maps its vendor's to these.
STOP_END = "end_turn"          # it finished its answer
STOP_MAX_TOKENS = "max_tokens"  # it was cut off by the length limit
STOP_REFUSAL = "refusal"       # a safety system ended the turn
# Any other vendor reason is passed through unchanged, for the log: no code
# branches on it.


class LLMOverloadedError(Exception):
    """The API was still overloaded (or unreachable) after every retry."""


class MissingAPIKeyError(RuntimeError):
    """No API key was found in the environment or in .env."""


@dataclass
class LLMResult:
    """One answer, whichever provider gave it.

    `output_tokens` is what the provider bills as output, which for a model that
    thinks first includes the thinking. `reasoning_tokens` says how much of that
    was thinking, where the provider reports it, and is for information only.
    """
    text: Optional[str]
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: Optional[str] = None
    reasoning_tokens: int = 0

    def as_dict(self):
        """The dict the rest of PESTO has always been handed."""
        return {"text": self.text, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "stop_reason": self.stop_reason, "flex": False}


class Provider(ABC):
    """A model vendor.

    Subclasses set the class attributes and implement `complete` and
    `check_key`. Everything vendor-specific stays in the subclass.
    """
    name: str = ""             # the prefix of a model spec: "anthropic:..."
    label: str = ""            # how it is written to a person: "Anthropic"
    key_env: str = ""          # the environment variable holding its API key
    key_url: str = ""          # where a person gets a key
    key_example: str = "..."   # what a key looks like, for the help text
    host: str = ""             # the one host the key is sent to
    sdk: str = ""              # the Python package, which names its own errors

    def __init__(self):
        self._client = None
        self._client_lock = threading.Lock()

    # ---- key and client -------------------------------------------------
    def api_key(self):
        from ...credentials import api_key
        return api_key(self.key_env)

    def missing_key_error(self):
        return MissingAPIKeyError(
            f"{self.key_env} is not set. Get a key at {self.key_url}, "
            f"then: export {self.key_env}={self.key_example}")

    def client(self):
        """The vendor's client, built once for the process."""
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    key = self.api_key()
                    if not key:
                        raise self.missing_key_error()
                    self._client = self.build_client(key)
        return self._client

    def reset(self):
        """Forget the client, so the next call reads the key again."""
        self._client = None

    @abstractmethod
    def build_client(self, key):
        """The vendor's SDK client for this key."""

    def validate_model(self, model):
        """Raise ValueError if this provider cannot run `model`, without calling
        it. The default accepts anything: the API will say if it is wrong."""

    def canonical_model(self, model):
        """`model` written so that two spellings of the same call are one string.

        This is what goes into a cache key. A provider whose calls depend on
        more than the model id (OpenAI's reasoning effort) spells all of it out,
        so that a default changing later cannot make an old key mean something
        else."""
        return model

    # ---- the call -------------------------------------------------------
    @abstractmethod
    def complete(self, model: str, prompt: str, temperature: float,
                 max_tokens: int) -> LLMResult:
        """One prompt, one answer. `model` is the vendor's own model id.

        `max_tokens` is the room asked for. What counts against it is the
        vendor's business, and an adapter may add headroom for the model's own
        thinking so that a thinking model is not cut off before it answers.
        """

    @abstractmethod
    def check_key(self, key: str) -> bool:
        """True if the vendor accepts the key. Must cost nothing."""
