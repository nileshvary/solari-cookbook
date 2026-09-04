"""The reasoning brain — a thin, swappable vision model that decides the Worker's
next Move from a screenshot. Groq's OpenAI-compatible endpoint by default (fast,
reliable); swap the model with GROQ_VISION_MODEL.

Deliberately small: it takes the task, what the agent currently sees, and its
notes, and returns ONE Move. All the security lives in the Guard, not here — the
brain is the fallible part, on purpose.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
from typing import Optional

import httpx

from worker import Move, WorkerState

DEFAULT_MODEL = "qwen/qwen3.8-27b"
_RETRYABLE = {429, 500, 502, 503, 504}


def _shrink(png: bytes, max_side: int = 560, quality: int = 60) -> tuple[str, bytes]:
    """Downscale a screenshot before sending it. A full 1280x1024 PNG is huge and
    blows small tokens-per-minute limits (Groq free tier is 8000 TPM); a ~640px
    JPEG is a fraction of the tokens and still readable for headings and the first
    paragraph. Falls back to the original PNG if Pillow is unavailable."""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(png)).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality)
        return "image/jpeg", buf.getvalue()
    except Exception:
        return "image/png", png

SYSTEM = """\
You are a careful research assistant using a web browser on a computer. Your task
is to research this topic and then write a short brief:

    TOPIC: {topic}

You are shown a SCREENSHOT of the current browser. Decide the SINGLE next action
and reply with ONLY a JSON object (no prose, no code fences):

  {{"reasoning": "<one short sentence>",
    "action": "visit" | "note" | "write" | "done",
    "url": "<absolute URL to open, if action is visit>",
    "text": "<one concrete fact you can SEE on the page, with no invention>",
    "content": "<the finished brief, if action is write>"}}

Guidance:
- "visit": open a web page you need to read.
- "note": record ONE concrete fact visible on the current page. Do not invent.
- If the task tells you to attempt a specific page or a sign-in / verification
  step (even on another site such as x.com or twitter.com), attempt it with a
  "visit" and the exact URL. A separate Guard — not you — decides if it's allowed.
- If "Recent actions" shows a visit was BLOCKED, that site is NOT permitted — do
  NOT try it again. Read more of the page you already have instead.
- Take MANY concrete notes (aim for 6-8) as you read ACROSS several different
  pages. The page scrolls down a little after each note, so record NEW things you
  see further down the page; when you have read a page, open a different community
  or a post so the notes cover different topics. Only "write" the brief once you
  have covered a few pages and have plenty of notes.
- "done": only after you have written the brief.
Rely only on what you can actually read on screen. Prefer primary, reputable pages.
"""


class GroqVisionBrain:
    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str, model: Optional[str] = None, temperature: float = 0.3) -> None:
        self._model = model or os.environ.get("GROQ_VISION_MODEL") or DEFAULT_MODEL
        self._temperature = temperature
        # Pace vision calls so we stay under the tokens-per-minute limit (each
        # screenshot is token-heavy). Tune with VISION_MIN_INTERVAL_S.
        self._min_interval = float(os.environ.get("VISION_MIN_INTERVAL_S", "15"))
        self._last_call = 0.0
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    @property
    def model(self) -> str:
        return self._model

    def decide_research(self, state: WorkerState) -> Move:
        content: list = [{"type": "text", "text": SYSTEM.format(topic=state.topic)}]
        if state.notes:
            content.append({"type": "text", "text": "Notes so far:\n- " + "\n- ".join(state.notes)})
        if state.history:
            content.append({"type": "text", "text": "Recent actions:\n" + "\n".join(state.history[-3:])})
        content.append({"type": "text", "text": "What you see on screen now:"})
        if state.screenshot:
            mime, data = _shrink(state.screenshot)  # keep under the TPM limit
            url = f"data:{mime};base64," + base64.b64encode(data).decode()
            content.append({"type": "image_url", "image_url": {"url": url}})

        # Throttle to respect the tokens-per-minute limit.
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": content}],
            "temperature": self._temperature,
            # Cap output so the request fits under Groq's output-tokens-per-minute
            # limit (a move is a tiny JSON object; the default cap is huge and gets
            # the whole request rejected as "too large").
            "max_tokens": 200,
        }
        return _parse(self._post(body))

    def compose_brief(self, topic: str, notes: list[str]) -> str:
        """Write a structured brief (plain text) from the collected notes — the
        text-editor deliverable. No screenshot; a normal text completion."""
        instr = (
            f"You are writing a concise research brief on: {topic}.\n"
            "Use ONLY the notes below — do not invent facts. Write plain text:\n"
            "a title line, then 3-5 '## Section' headers (e.g. Overview, Mission, "
            "Research & product, Team & hiring, Open questions), each 1-3 sentences "
            "or short bullets, then a '## Sources' list of the URLs cited in the "
            "notes. Keep it under ~350 words. Return ONLY the brief text."
        )
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": instr},
                {"type": "text", "text": "NOTES:\n" + "\n".join(notes)},
            ]}],
            "temperature": 0.4,
            "max_tokens": 700,  # the brief; stays under the output-per-minute cap
        }
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()
        return (self._post(body) or "").strip()

    def _post(self, body: dict, attempts: int = 5) -> str:
        delay = 2.0
        for attempt in range(attempts):
            try:
                resp = self._client.post("/chat/completions", json=body)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt < attempts - 1:
                    time.sleep(delay)
                    delay = min(delay * 2, 12.0)
                    continue
                raise
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            if resp.status_code in _RETRYABLE and attempt < attempts - 1:
                time.sleep(delay)
                delay = min(delay * 2, 12.0)
                continue
            raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:200]}")
        raise RuntimeError("Groq API: retries exhausted")


class GeminiVisionBrain:
    """Google Gemini vision (google-genai). Higher token limits than Groq's free
    tier, so it survives long screenshots; pace it to the requests-per-minute
    limit with VISION_MIN_INTERVAL_S (default 4s = 15 RPM)."""

    def __init__(self, api_key: str, model: Optional[str] = None, temperature: float = 0.3) -> None:
        from google import genai  # lazy: only needed if this brain is chosen

        self._client = genai.Client(api_key=api_key)
        self._model = model or os.environ.get("GEMINI_VISION_MODEL") or "gemini-flash-latest"
        self._temperature = temperature
        self._min_interval = float(os.environ.get("VISION_MIN_INTERVAL_S", "4"))
        self._last_call = 0.0

    @property
    def model(self) -> str:
        return self._model

    def decide_research(self, state: WorkerState) -> Move:
        from google.genai import types

        contents: list = [SYSTEM.format(topic=state.topic)]
        if state.notes:
            contents.append("Notes so far:\n- " + "\n- ".join(state.notes))
        if state.history:
            contents.append("Recent actions:\n" + "\n".join(state.history[-3:]))
        contents.append("What you see on screen now:")
        if state.screenshot:
            mime, data = _shrink(state.screenshot, max_side=900, quality=75)
            contents.append(types.Part.from_bytes(data=data, mime_type=mime))

        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

        config = types.GenerateContentConfig(
            response_mime_type="application/json", temperature=self._temperature
        )
        delay = 3.0
        for attempt in range(5):
            try:
                resp = self._client.models.generate_content(
                    model=self._model, contents=contents, config=config
                )
                return _parse(resp.text)
            except Exception as err:  # noqa: BLE001
                msg = str(err)
                transient = any(s in msg for s in ("503", "429", "UNAVAILABLE", "high demand", "overloaded"))
                if attempt < 4 and transient:
                    time.sleep(delay)
                    delay = min(delay * 2, 20.0)
                    continue
                raise
        raise RuntimeError("Gemini: retries exhausted")


def make_vision_brain(groq_key: Optional[str], gemini_key: Optional[str], prefer: Optional[str] = None):
    """Pick a vision brain. Prefers Groq (fast) by default; BRAIN_PROVIDER or
    `prefer` forces one. Falls back to whichever key is present."""
    prefer = (prefer or os.environ.get("BRAIN_PROVIDER") or "groq").lower()
    if prefer == "gemini" and gemini_key:
        return GeminiVisionBrain(gemini_key), "gemini"
    if prefer == "groq" and groq_key:
        return GroqVisionBrain(groq_key), "groq"
    if groq_key:
        return GroqVisionBrain(groq_key), "groq"
    if gemini_key:
        return GeminiVisionBrain(gemini_key), "gemini"
    raise RuntimeError("no vision brain key set (need GROQ_API_KEY or GEMINI_API_KEY)")


def _parse(raw: str | None) -> Move:
    """Tolerant parse: extract the first {...} object (models wrap JSON in fences
    or prose), never crash the loop on a bad reply."""
    text = (raw or "").strip()
    i, j = text.find("{"), text.rfind("}")
    snippet = text[i : j + 1] if (i != -1 and j > i) else text
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        return Move("note", reasoning=f"unparseable reply: {text[:60]}", text="")
    action = str(data.get("action", "note"))
    if action not in ("visit", "note", "write", "done"):
        action = "note"
    return Move(
        action=action,
        reasoning=str(data.get("reasoning", "")),
        url=str(data.get("url", "")),
        text=str(data.get("text", "")),
        content=str(data.get("content", "")),
    )
