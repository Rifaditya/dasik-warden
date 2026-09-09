# Copyright (C) 2026 Dasik (Rifaditya) | GNU GPLv3
"""
Unit tests for Dasik Warden evaluation heuristics and strike progression.
"""

import os
import unittest
from warden_core import evaluate_message_content, ViolationType, StrikeManager

class TestWardenCore(unittest.TestCase):

    def test_benign_messages(self):
        benign_samples = [
            "Hey how do I install Fabric 0.16.10?",
            "I love the Instant Gratification mod!",
            "Can someone check my log? https://mclo.gs/abc1234",
            "What is the crafting recipe for the copper bell?",
            "Working fine on 1.21.1 and 26.2"
        ]
        for text in benign_samples:
            res = evaluate_message_content(text)
            self.assertFalse(res.violation, f"False positive triggered for: {text}")

    def test_piracy_detection(self):
        piracy_samples = [
            ("I use TLauncher and my game crashed", "tlauncher"),
            ("Download from 9minecraft here: http://9minecraft.net/mod", "9minecraft"),
            ("Where can I find free minecraft account?", "free minecraft account"),
            ("You can get fitgirl-repacks version", "fitgirl-repacks"),
            ("Check shiginima launcher", "shiginima")
        ]
        for text, matched in piracy_samples:
            res = evaluate_message_content(text)
            self.assertTrue(res.violation, f"Failed to catch piracy in: {text}")
            self.assertEqual(res.violation_type, ViolationType.PIRACY)
            self.assertTrue(res.auto_delete)
            self.assertFalse(res.send_nudge_only)

    def test_gatekeeping_detection(self):
        gatekeeping_samples = [
            "google is free bro",
            "just google it",
            "RTFM or learn to read",
            "read the wiki first",
            "what a dumb question",
            "why are you even asking this here"
        ]
        for text in gatekeeping_samples:
            res = evaluate_message_content(text)
            self.assertTrue(res.violation, f"Failed to catch gatekeeping in: {text}")
            self.assertEqual(res.violation_type, ViolationType.GATEKEEPING)
            self.assertTrue(res.send_nudge_only)

    def test_zero_tolerance_detection(self):
        malicious_samples = [
            "click here for free nitro discord.gift/aBcDeFg",
            "download this token logger script",
            "I will have you doxxed"
        ]
        for text in malicious_samples:
            res = evaluate_message_content(text)
            self.assertTrue(res.violation, f"Failed to catch zero-tolerance in: {text}")
            self.assertEqual(res.violation_type, ViolationType.ZERO_TOLERANCE)
            self.assertTrue(res.auto_delete)

    def test_strike_ladder(self):
        test_db = "test_strikes.json"
        if os.path.exists(test_db):
            os.remove(test_db)

        try:
            sm = StrikeManager(storage_path=test_db)
            user_id = 9876543210

            # Strike 1: 5m timeout
            c1, m1, b1 = sm.add_strike(user_id, "Infraction 1", 111, ViolationType.PIRACY)
            self.assertEqual(c1, 1)
            self.assertEqual(m1, 5)
            self.assertFalse(b1)

            # Strike 2: 10m timeout
            c2, m2, b2 = sm.add_strike(user_id, "Infraction 2", 111, ViolationType.GATEKEEPING)
            self.assertEqual(c2, 2)
            self.assertEqual(m2, 10)
            self.assertFalse(b2)

            # Strike 3: 20m timeout
            c3, m3, b3 = sm.add_strike(user_id, "Infraction 3", 111, ViolationType.MANUAL_WARN)
            self.assertEqual(c3, 3)
            self.assertEqual(m3, 20)
            self.assertFalse(b3)

            # Strike 4..7: exponential doubling
            for i in range(4, 8):
                c, m, b = sm.add_strike(user_id, f"Infraction {i}", 111, ViolationType.MANUAL_WARN)
                self.assertEqual(c, i)
                self.assertFalse(b)

            # Strike 8 (1st peak): 640m timeout, NO ban
            c8, m8, b8 = sm.add_strike(user_id, "Infraction 8 (1st Peak)", 111, ViolationType.MANUAL_WARN)
            self.assertEqual(c8, 8)
            self.assertEqual(m8, 640)
            self.assertFalse(b8)

            # Strike 9 (2nd peak): 1280m timeout, NO ban
            c9, m9, b9 = sm.add_strike(user_id, "Infraction 9 (2nd Peak)", 111, ViolationType.MANUAL_WARN)
            self.assertEqual(c9, 9)
            self.assertEqual(m9, 1280)
            self.assertFalse(b9)

            # Strike 10 (3rd peak): Permanent Ban!
            c10, m10, b10 = sm.add_strike(user_id, "Infraction 10 (3rd Peak)", 111, ViolationType.MANUAL_WARN)
            self.assertEqual(c10, 10)
            self.assertTrue(b10)

            # Verify fetch
            history = sm.get_strikes(user_id)
            self.assertEqual(len(history), 10)

            # Clear strikes
            cleared = sm.clear_strikes(user_id)
            self.assertEqual(cleared, 10)
            self.assertEqual(len(sm.get_strikes(user_id)), 0)
        finally:
            if os.path.exists(test_db):
                os.remove(test_db)

if __name__ == "__main__":
    unittest.main()
