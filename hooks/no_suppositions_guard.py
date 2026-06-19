#!/usr/bin/env python3
"""UserPromptSubmit guard (ships with the OpenRig plugin).

When the user's prompt is about real-world guitar gear / tone / an artist's
rig, inject a reminder that any factual claim must be backed by a MEASURED
number (the analyzer) or a source FETCHED this turn (WebSearch/WebFetch) —
never training memory. Pairs with the openrig-tone-builder HARD RULE
"no suppositions about real-world GEAR / tone / history".

Pure stdlib, no deps. Reads the hook JSON on stdin; on a gear/tone question it
prints the guard to stdout (UserPromptSubmit stdout is added to context).
Always exits 0 — a guard must never block the user's prompt.
"""

import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

prompt = str(data.get("prompt") or "").lower()

# Real-world gear / tone vocabulary (PT + EN).
GEAR = re.compile(
    r"\b(timbre|tom|tone|amp|amplifier|valvul|pedal|overdrive|distor|drive|"
    r"booster|fuzz|cab|cabinet|gabinete|pickup|captador|humbucker|single.?coil|"
    r"preset|rig|gear|setup|signal chain|cadeia de sinal|marshall|fender|mesa|"
    r"boogie|vox|orange|diezel|engl|peavey|boss|ibanez|gibson|strat|telecaster|"
    r"les ?paul|jcm|plexi|rectifier|tube ?screamer|big ?muff|ds-?1|bd-?2)\b"
)
# How-to / question framing.
ASKY = re.compile(
    r"\b(como|qual|quais|que|por que|how|what|which|why|usa|usou|used|uses|"
    r"sound|sounds|som|recri|recreate|monta|build|faz|fazer|consigo|conseguir)\b"
)

if GEAR.search(prompt) and ASKY.search(prompt):
    print(
        "GEAR/TONE FACT GUARD - this prompt is about real-world gear/tone. "
        "Do NOT state any claim about gear, amps, cabs, pedals, pickups, an "
        "artist's signal chain, an album's setup, models, specs, prices, or "
        "music history from training memory. Back every such claim with EITHER "
        "(a) a number measured with the analyzer, OR (b) a source fetched THIS "
        "turn via WebSearch/WebFetch (cite the URL). If you have neither: "
        "WebSearch first, or label it explicitly '(unverified - from memory)'. "
        "Your prior is never the basis. (openrig-tone-builder HARD RULE: no "
        "suppositions about real-world gear/tone/history.)"
    )

sys.exit(0)
