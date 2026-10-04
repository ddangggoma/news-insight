"""Card engines: Antigravity CLI (Gemini Flash, primary) and local Qwen via LM Studio (fallback).

Both run without tools and only see public item metadata plus the stored excerpt (D18).
Each engine answers two structured-output tasks: full cards (`generate`) and taxonomy labels
for existing cards (`classify`, title and summary only, used by the backfill).
"""

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from news_insight.cards.schemas import (
    CardInput,
    LabelInput,
    card_batch_schema,
    card_instructions,
    label_batch_schema,
    label_instructions,
)
from news_insight.classify.taxonomy import Taxonomy, get_taxonomy
from news_insight.digest.claude import safe_env

Runner = Callable[..., subprocess.CompletedProcess[str]]
QUOTA_MARKERS = ("quota", "rate limit", "rate_limit", "resource_exhausted", "exhausted", "429")
USAGE_LINE = re.compile(r"^Gemini Models\t(Weekly|Five Hour) Limit Remaining\t(\d+)%", re.M)


class EngineError(Exception):
    """The engine failed for this batch (the items stay pending)."""


class QuotaExhausted(EngineError):
    """Antigravity reported that its usage limit is spent; switch to the fallback."""


@dataclass(frozen=True)
class Quota:
    """Remaining percentage of the Antigravity Gemini limits (None when unknown)."""

    weekly: int | None
    five_hour: int | None

    def usable(self, *, min_weekly: int, min_five_hour: int) -> bool:
        return (
            self.weekly is not None
            and self.five_hour is not None
            and self.weekly > min_weekly
            and self.five_hour > min_five_hour
        )

    def as_dict(self) -> dict[str, int | None]:
        return {"weekly": self.weekly, "five_hour": self.five_hour}


def parse_usage(text: str) -> Quota:
    found = {kind: int(value) for kind, value in USAGE_LINE.findall(text)}
    return Quota(weekly=found.get("Weekly"), five_hour=found.get("Five Hour"))


@dataclass(frozen=True)
class EngineOutput:
    raw: Any
    model: str


class CardEngine(Protocol):
    name: str

    def generate(self, inputs: list[CardInput]) -> EngineOutput: ...


class LabelEngine(Protocol):
    """An engine that classifies existing cards from their Korean title and summary."""

    name: str

    def classify(self, inputs: list[LabelInput]) -> EngineOutput: ...


class MeteredEngine(CardEngine, Protocol):
    """An engine with a usage limit it can report (Antigravity)."""

    def usage(self) -> Quota: ...


class MeteredLabelEngine(LabelEngine, Protocol):
    def usage(self) -> Quota: ...


@dataclass(frozen=True)
class Task:
    """One structured-output request: instructions, JSON payload and output schema."""

    name: str
    instructions: str
    payload: str
    schema: dict[str, Any]


def _payload(inputs: Sequence[BaseModel]) -> str:
    return json.dumps([card.model_dump() for card in inputs], ensure_ascii=False)


def card_task(inputs: list[CardInput], taxonomy: Taxonomy) -> Task:
    return Task("cards", card_instructions(taxonomy), _payload(inputs), card_batch_schema(taxonomy))


def label_task(inputs: list[LabelInput], taxonomy: Taxonomy) -> Task:
    return Task(
        "labels", label_instructions(taxonomy), _payload(inputs), label_batch_schema(taxonomy)
    )


class AgyEngine:
    """`agy -p` in an empty directory. Headless mode auto-denies every tool permission."""

    name = "agy"

    def __init__(
        self,
        *,
        executable: str,
        model: str,
        timeout_seconds: int,
        runner: Runner = subprocess.run,
        taxonomy: Taxonomy | None = None,
    ) -> None:
        self._executable = executable
        self._model = model
        self._timeout = timeout_seconds
        self._runner = runner
        self._taxonomy = taxonomy or get_taxonomy()

    def _run(self, args: list[str]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="cards-") as workdir:
            try:
                completed = self._runner(
                    [self._executable, *args],
                    capture_output=True,
                    text=True,
                    timeout=self._timeout + 60,
                    cwd=workdir,
                    env=safe_env(os.environ),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise EngineError(f"agy timed out after {self._timeout}s") from exc
            except OSError as exc:
                raise EngineError(f"cannot run agy: {exc}") from exc
        output = completed.stdout.strip()
        if completed.returncode != 0 and not output:
            detail = completed.stderr[-300:]
            if any(marker in detail.lower() for marker in QUOTA_MARKERS):
                raise QuotaExhausted(f"agy quota: {detail}")
            raise EngineError(f"agy exited {completed.returncode}: {detail}")
        try:
            envelope = json.loads(output)
        except ValueError as exc:
            raise EngineError("agy returned non-JSON output") from exc
        if not isinstance(envelope, dict):
            raise EngineError("agy returned an unexpected envelope")
        return envelope

    def usage(self) -> Quota:
        envelope = self._run(["-p", "/usage", "--output-format", "json"])
        return parse_usage(str(envelope.get("response", "")))

    def generate(self, inputs: list[CardInput]) -> EngineOutput:
        return self._complete(card_task(inputs, self._taxonomy))

    def classify(self, inputs: list[LabelInput]) -> EngineOutput:
        return self._complete(label_task(inputs, self._taxonomy))

    def _complete(self, task: Task) -> EngineOutput:
        prompt = f"{task.instructions}\n입력:\n{task.payload}"
        envelope = self._run(
            [
                "-p",
                prompt,
                "--model",
                self._model,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(task.schema),
                "--disable-slash-commands",
                "--print-timeout",
                f"{self._timeout}s",
            ]
        )
        status = str(envelope.get("status", ""))
        if status != "SUCCESS":
            detail = json.dumps(envelope, ensure_ascii=False)[:300]
            if any(marker in detail.lower() for marker in QUOTA_MARKERS):
                raise QuotaExhausted(f"agy quota: {detail}")
            raise EngineError(f"agy status {status}: {detail}")
        structured = envelope.get("structured_output")
        if isinstance(structured, str):
            try:
                structured = json.loads(structured)
            except ValueError as exc:
                raise EngineError("agy structured_output is not JSON") from exc
        if not isinstance(structured, dict):
            raise EngineError("agy returned no structured output")
        return EngineOutput(raw=structured, model=self._model)


class QwenEngine:
    """LM Studio OpenAI-compatible endpoint, reasoning off, JSON-schema constrained."""

    name = "qwen"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: int,
        client: httpx.Client | None = None,
        taxonomy: Taxonomy | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/v1/chat/completions"
        self._model = model
        self._client = client or httpx.Client(timeout=timeout_seconds, trust_env=False)
        self._taxonomy = taxonomy or get_taxonomy()

    def generate(self, inputs: list[CardInput]) -> EngineOutput:
        return self._complete(card_task(inputs, self._taxonomy))

    def classify(self, inputs: list[LabelInput]) -> EngineOutput:
        return self._complete(label_task(inputs, self._taxonomy))

    def _complete(self, task: Task) -> EngineOutput:
        body = {
            "model": self._model,
            "temperature": 0,
            "reasoning_effort": "none",
            "messages": [
                {"role": "system", "content": task.instructions},
                {"role": "user", "content": task.payload},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": task.name, "strict": True, "schema": task.schema},
            },
        }
        try:
            response = self._client.post(self._url, json=body)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return EngineOutput(raw=json.loads(content), model=self._model)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise EngineError(f"qwen failed: {exc}") from exc
