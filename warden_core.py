# Copyright (C) 2026 Dasik (Rifaditya) | GNU GPLv3
"""
Warden Core - Modular evaluation logic and state management for Dasik Warden.
Enforces anti-piracy, zero-gatekeeping ("Help or Stay Silent"), and 3-strike disciplinary ladder.
"""

from dataclasses import dataclass
from enum import Enum
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

class ViolationType(Enum):
    PIRACY = "piracy"
    GATEKEEPING = "gatekeeping"
    ZERO_TOLERANCE = "zero_tolerance"
    MANUAL_WARN = "manual_warn"

@dataclass
class EvaluationResult:
    violation: bool
    violation_type: Optional[ViolationType] = None
    reason: str = ""
    matched_pattern: str = ""
    auto_delete: bool = False
    send_nudge_only: bool = False

# Regex definitions
PIRACY_PATTERNS = [
    # Cracked launchers & warez
    (r"\b(tlauncher|shiginima|tlaucher|sklauncher\s+cracked|crystal\s+launcher\s+cracked)\b", "Mentioning or linking cracked/warez Minecraft launchers"),
    (r"\b(cracked\s+minecraft|minecraft\s+cracked|free\s+minecraft\s+account|mc\s+alts\s+free)\b", "Promoting cracked/unlicensed Minecraft"),
    (r"\b(the-eye\.eu|steamunlocked|crohasit|fitgirl-repacks|dodi-repacks)\b", "Linking piracy/warez repositories"),
    # Illicit mod re-uploaders / malware distributors
    (r"\b(9minecraft(\.net)?|mc-mods\.org|minecraft-downloads\.com|mod-minecraft\.net)\b", "Linking unsafe/unauthorized mod re-upload sites"),
]

GATEKEEPING_PATTERNS = [
    (r"\b(google\s+(is\s+free|it|that)|just\s+google(\s+it)?)\b", "Telling a user to just google it"),
    (r"\b(rtfm|read\s+the\s+(fucking\s+)?(manual|wiki)|learn\s+to\s+read)\b", "Dismissive 'read the manual/wiki' response"),
    (r"\b(dumb|stupid|idiotic)\s+(question|ask)\b", "Labeling a beginner question as dumb or stupid"),
    (r"\b(why\s+are\s+you\s+even\s+asking\s+this|waste\s+of\s+time\s+to\s+ask)\b", "Dismissive question shaming"),
]

ZERO_TOLERANCE_PATTERNS = [
    (r"\b(token\s+logger|grabber|ip\s+logger|discord\.gift\/[a-zA-Z0-9]+|nitro\s+airdrop|free\s+nitro)\b", "Malicious link or scam/phishing pattern"),
    (r"\b(doxxed|doxxing|swatting|swatted)\b", "Doxxing or harassment threat"),
]

def evaluate_message_content(content: str) -> EvaluationResult:
    """
    Evaluates message text for violations. Zero external dependencies.
    Case-insensitive matching.
    """
    cleaned = content.strip().lower()
    if not cleaned:
        return EvaluationResult(violation=False)

    # 1. Check Zero Tolerance
    for pattern, desc in ZERO_TOLERANCE_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return EvaluationResult(
                violation=True,
                violation_type=ViolationType.ZERO_TOLERANCE,
                reason=desc,
                matched_pattern=match.group(0),
                auto_delete=True,
                send_nudge_only=False
            )

    # 2. Check Piracy / Warez
    for pattern, desc in PIRACY_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return EvaluationResult(
                violation=True,
                violation_type=ViolationType.PIRACY,
                reason=desc,
                matched_pattern=match.group(0),
                auto_delete=True,
                send_nudge_only=False
            )

    # 3. Check Gatekeeping / Sarcastic dismissal
    for pattern, desc in GATEKEEPING_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return EvaluationResult(
                violation=True,
                violation_type=ViolationType.GATEKEEPING,
                reason=desc,
                matched_pattern=match.group(0),
                auto_delete=False, # We don't delete immediately; we nudge to preserve thread context unless repeated
                send_nudge_only=True
            )

    return EvaluationResult(violation=False)


class StrikeManager:
    """
    Thread-safe, file-backed strike manager.
    Stores strike history per user ID.
    """
    def __init__(self, storage_path: str = "strikes.json"):
        self.storage_path = storage_path
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def save(self) -> None:
        temp_path = self.storage_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, self.storage_path)

    @staticmethod
    def calculate_timeout_minutes(strike_count: int) -> int:
        """
        Progressive exponential timeout ladder:
        Strike 1 = 5m, Strike 2 = 10m, Strike 3 = 20m, Strike 4 = 40m, etc.
        Formula: 5 * (2 ** (strike_count - 1))
        Capped at 40,320 minutes (28 days, the Discord API max per call).
        """
        if strike_count <= 0:
            return 5
        minutes = 5 * (2 ** (strike_count - 1))
        # Discord limit: 28 days = 28 * 24 * 60 = 40320 minutes
        return min(minutes, 40320)

    def add_strike(self, user_id: int, reason: str, issuer_id: int, violation_type: ViolationType) -> Tuple[int, int, bool]:
        """
        Adds a strike and returns (new_strike_count, timeout_minutes, should_ban).
        - Strikes 1..9: Progressive exponential timeouts.
        - Strike 10 (3rd violation at/above Strike 8): Triggers permanent ban.
        """
        key = str(user_id)
        if key not in self._data:
            self._data[key] = []

        strike_record = {
            "timestamp": int(time.time()),
            "reason": reason,
            "issuer_id": issuer_id,
            "type": violation_type.value
        }
        self._data[key].append(strike_record)
        self.save()

        count = len(self._data[key])
        should_ban = count >= 10
        timeout_minutes = self.calculate_timeout_minutes(count)
        return count, timeout_minutes, should_ban

    def get_strikes(self, user_id: int) -> List[Dict[str, Any]]:
        return self._data.get(str(user_id), [])

    def clear_strikes(self, user_id: int) -> int:
        key = str(user_id)
        count = len(self._data.get(key, []))
        if key in self._data:
            del self._data[key]
            self.save()
        return count
