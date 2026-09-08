# Dasik Warden 🛡️

Dedicated moderation and community guardian bot for the **Dasik Igaijinn** Discord server (`1546093898907258933`).

Built with a solo-developer voice, Dasik Warden automates community safety, enforces zero-gatekeeping standards, protects against malware/cracked software distribution, and maintains an auditable 3-strike disciplinary ladder.

---

## 🌟 Core Moderation Invariants

### 1. Anti-Piracy & Warez Defense
- Automatically detects and purges links/mentions of cracked Minecraft launchers (TLauncher, Shiginima, Crystal Launcher cracked, etc.) and illicit mod re-upload / malware sites (`9minecraft`, `mc-mods.org`).
- Deletes infringing messages instantly, issues an informative DM explaining Mojang EULA & account safety, and registers a strike.

### 2. "Help or Stay Silent" (Zero-Gatekeeping Invariant)
- Detects toxic, dismissive responses to beginners (*"google is free"*, *"google it"*, *"read the wiki"*, *"dumb question"*, *"RTFM"*).
- **First infraction**: Replies with a friendly educational reminder (*"No question is a stupid question. If you don't feel like answering kindly, please stay silent and let others or the dev answer."*).
- **Repeated infractions**: Message purged and escalated on the disciplinary ladder.

### 3. 3-Strike Progressive Disciplinary Engine
- **Strike 1**: Warning notice + 10-minute timeout.
- **Strike 2**: Warning notice + 1-hour timeout.
- **Strike 3**: Automated permanent server ban.
- **Zero-Tolerance Bypass**: Immediate permanent ban for malware, token loggers, phishing gift links, or doxxing threats.

---

## 🛠️ Slash Commands

| Command | Permission | Description |
| :--- | :--- | :--- |
| `/strikes <member>` | Moderate Members | View full strike history, timestamps, and reasons for a member. |
| `/warn <member> <reason>` | Moderate Members | Issue a manual strike and trigger the disciplinary ladder. |
| `/clearstrikes <member>` | Administrator | Clear all active strikes on record for a member. |

---

## 🧪 Testing & Execution

Run the headless unit test suite:
```bash
python test_warden.py
```

Run the bot:
```bash
python warden.py
```
