# Copyright (C) 2026 Dasik (Rifaditya) | GNU GPLv3
"""
Unit tests for Dasik Warden evaluation heuristics and strike progression.
"""

import os
import unittest
from warden_core import evaluate_message_content, ViolationType, DemeritManager

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

    def test_demerit_system_and_decay(self):
        test_db = "test_demerits.json"
        if os.path.exists(test_db):
            os.remove(test_db)

        try:
            dm = DemeritManager(storage_path=test_db)
            user_id = 9876543210
            base_time = 1700000000

            # 1. First infraction: Gatekeeping (+1 pt) -> Caution (0m timeout)
            p1, t1, desc1, ban1 = dm.add_demerit(user_id, "Gatekeeping", 111, ViolationType.GATEKEEPING, custom_time=base_time)
            self.assertEqual(p1, 1)
            self.assertEqual(t1, 0)
            self.assertFalse(ban1)

            # 2. Second infraction: Piracy (+3 pts) -> Total 4 pts -> 15-minute timeout
            p2, t2, desc2, ban2 = dm.add_demerit(user_id, "Piracy link", 111, ViolationType.PIRACY, custom_time=base_time + 100)
            self.assertEqual(p2, 4)
            self.assertEqual(t2, 15)
            self.assertFalse(ban2)

            # 3. Third infraction: Manual warning (+2 pts) -> Total 6 pts -> 1-hour timeout
            p3, t3, desc3, ban3 = dm.add_demerit(user_id, "Rude comment", 111, ViolationType.MANUAL_WARN, custom_time=base_time + 200)
            self.assertEqual(p3, 6)
            self.assertEqual(t3, 60)
            self.assertFalse(ban3)

            # 4. Test 30-day point decay / rehabilitation
            # Query 31 days in the future (31 * 86400 seconds)
            future_time = base_time + (31 * 86400)
            active_pts, active_records = dm.get_active_points(user_id, current_time=future_time)
            self.assertEqual(active_pts, 0)
            self.assertEqual(len(active_records), 0)

            # 5. Add infraction after clean period -> Starts fresh from newly added points!
            p4, t4, desc4, ban4 = dm.add_demerit(user_id, "New infraction after clean slate", 111, ViolationType.PIRACY, custom_time=future_time)
            self.assertEqual(p4, 3)
            self.assertEqual(t4, 15)
            self.assertFalse(ban4)

            # 6. Test 12-point threshold and 3-strike suspension permanent ban
            dm.clear_demerits(user_id)
            # 1st time hitting 12 pts
            p_hit1, _, _, ban_hit1 = dm.add_demerit(user_id, "Major violation 1", 111, ViolationType.ZERO_TOLERANCE, points=12, custom_time=future_time)
            self.assertEqual(p_hit1, 12)
            self.assertFalse(ban_hit1)  # 1st suspension, no ban

            # 2nd time hitting 12 pts
            p_hit2, _, _, ban_hit2 = dm.add_demerit(user_id, "Major violation 2", 111, ViolationType.ZERO_TOLERANCE, points=12, custom_time=future_time + 10)
            self.assertFalse(ban_hit2)  # 2nd suspension, no ban

            # 3rd time hitting 12 pts -> BAN!
            p_hit3, _, _, ban_hit3 = dm.add_demerit(user_id, "Major violation 3", 111, ViolationType.ZERO_TOLERANCE, points=12, custom_time=future_time + 20)
            self.assertTrue(ban_hit3)  # 3rd suspension triggers Permanent Ban!

        finally:
            if os.path.exists(test_db):
                os.remove(test_db)

if __name__ == "__main__":
    unittest.main()

