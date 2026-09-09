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


class DemeritManager:
    """
    Australian-style Demerit Points System manager.
    Tracks infraction points, 30-day point decay (rehabilitation),
    progressive timeout thresholds, and 3x 12-point suspension permanent ban.
    """
    SUSPENSION_THRESHOLD = 12
    POINT_EXPIRY_SECONDS = 30 * 24 * 60 * 60  # 30 Days

    # Point allocation matrix
    POINT_WEIGHTS = {
        ViolationType.GATEKEEPING: 1,      # Mild gatekeeping/sarcasm
        ViolationType.PIRACY: 3,           # Warez / cracked launcher / 9minecraft
        ViolationType.ZERO_TOLERANCE: 12,  # Scams, loggers, doxxing
        ViolationType.MANUAL_WARN: 2,      # Default moderator warning
    }

    def __init__(self, storage_path: str = "demerits.json"):
        self.storage_path = storage_path
        self._data: Dict[str, Dict[str, Any]] = {}
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

    def get_user_record(self, user_id: int) -> Dict[str, Any]:
        key = str(user_id)
        if key not in self._data:
            self._data[key] = {
                "history": [],
                "suspension_count": 0
            }
        return self._data[key]

    def get_active_points(self, user_id: int, current_time: Optional[int] = None) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Returns (active_points, active_records) based on 30-day decay.
        Points older than 30 days are expired.
        """
        now = current_time or int(time.time())
        record = self.get_user_record(user_id)
        active_records = []
        active_points = 0

        for item in record.get("history", []):
            age = now - item.get("timestamp", 0)
            if age < self.POINT_EXPIRY_SECONDS:
                active_records.append(item)
                active_points += item.get("points", 0)

        return active_points, active_records

    def calculate_penalty(self, active_points: int) -> Tuple[int, str]:
        """
        Maps active points to disciplinary timeout minutes:
        - 1-2 points: Caution / 0m timeout
        - 3-5 points: 15-minute timeout
        - 6-8 points: 1-hour timeout (60m)
        - 9-11 points: 6-hour timeout (360m)
        - 12+ points: 24-hour suspension timeout (1440m)
        """
        if active_points < 3:
            return 0, "Caution (Infraction Recorded)"
        elif active_points <= 5:
            return 15, "15-minute timeout"
        elif active_points <= 8:
            return 60, "1-hour timeout"
        elif active_points <= 11:
            return 360, "6-hour timeout"
        else:
            return 1440, "24-hour suspension timeout"

    def add_demerit(
        self,
        user_id: int,
        reason: str,
        issuer_id: int,
        violation_type: ViolationType,
        points: Optional[int] = None,
        custom_time: Optional[int] = None
    ) -> Tuple[int, int, str, bool]:
        """
        Adds demerit points and returns:
        (total_active_points, timeout_minutes, action_desc, should_ban)
        """
        now = custom_time or int(time.time())
        pts = points if points is not None else self.POINT_WEIGHTS.get(violation_type, 2)
        record = self.get_user_record(user_id)

        infraction = {
            "timestamp": now,
            "points": pts,
            "reason": reason,
            "issuer_id": issuer_id,
            "type": violation_type.value
        }
        record["history"].append(infraction)

        active_points, _ = self.get_active_points(user_id, now)
        timeout_minutes, action_desc = self.calculate_penalty(active_points)

        should_ban = False
        if active_points >= self.SUSPENSION_THRESHOLD:
            record["suspension_count"] = record.get("suspension_count", 0) + 1
            if record["suspension_count"] >= 3:
                should_ban = True
                action_desc = "Permanent Ban (Accumulated 12+ demerits 3 separate times)"

        self.save()
        return active_points, timeout_minutes, action_desc, should_ban

    def clear_demerits(self, user_id: int) -> int:
        key = str(user_id)
        if key in self._data:
            cleared = len(self._data[key].get("history", []))
            del self._data[key]
            self.save()
            return cleared
        return 0


# Legacy backwards-compatibility alias
StrikeManager = DemeritManager

