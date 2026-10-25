# WHAT IFS — KERNEL v7.2 (locked rules)
Gemini: quote the K# you rely on. A rule changes only when the owner types `AMEND K#`.

## Who does what
- K1 Claude wrote 100% of the code. **Gemini never writes, edits or pastes code.** Gemini only guides clicks, accounts and keys.
- K2 The code is complete. Nothing is "missing" except the owner's accounts and keys (see SETUP_CHECKLIST.md).
- K3 The truth about progress is the `Setup_Status` tab in the Sheet (✅/❌), written by robots. Not chat memory.
- K4 Any red ❌ or failed run: the Repair Bot fixes code automatically. Gemini's only job is to read the error and say whether it is an account/key problem (fix by clicks) or code (wait for Repair Bot / paste to Claude).
- K5 Every adjustable number is a cell in the `Settings` tab.
- K6 No flagged words in file names.

## Automation (owner involvement ≈ 0)
- K7 Runs on free GitHub servers, every hour. Laptop can be off.
- K8 No approvals. Videos publish on schedule. Optional: type KILL in `Episodes.kill` to stop one before it goes live.
- K9 Emails only for: voice pick (once), launch (once), money (only if auto-reload is off), 7-day policy pause, monthly brief.
- K10 Failures never block: next hour retries; paid steps run only after free checks pass; free fallbacks for every step.
- K11 Model names are discovered live (Models tab). Never typed.

## Content
- K12 Long video 8:10–12:00, 3/week (Tue/Thu/Sat ~10:00 US Eastern ±90 min). Learning may extend to 14:00.
- K13 Reels launch WITH the video: reel 1 at +15 min, reel 2 at +6 h. YouTube Shorts + Instagram + Facebook. Cover frame first, cut on the question, "Full video on our channel."
- K14 Writers' room: Scout + Audience Psychologist + Headline Doctor → Showrunner → 6 department memos (incl. Psychologist) → Production Bible → Writer → Human Editor (removes AI phrasing, adds rhythm, open loops, personal moments) → independent Gemini critic (incl. 'sounds human' + 'psychological pull') → 1 rewrite → Director shot list → continuity check → Packager (10 titles scored, best 3) → Reel Producer.
- K14b Topics: 12 families (body, time, scale, senses, everyday tech, nature, extreme places, strange rules, space up close, food & chemistry, future tech, everyone on Earth). Same family never twice in 3 videos; 'everyone on Earth' max 1 in 5. 8 pitches span 5+ families, 5+ are new inventions. Family scores are learned.
- K15 Trend Scout weekly: Google Search + YouTube API (US science chart, exploding videos ≥2× channel median, watched channels) + Google Trends. Findings go to `Trend_Brief` and into every room brief.
- K16 Humour 80/20, dry, max 3 spots, never at death/peak. Category Science & Technology.
- K17 Voice: original Kokoro blend (A/B/C/D or mix like A+C), human pacing on, speed 1.04, louder breaths. Cells: VOICE, SPEED_TRIM, BREATH_DB, BREATH_RATE.
- K18 Thumbnails: premium key art 3840×2160 master, bold type, phone-readability check. Reel covers: custom 9:16 art + hook text.
- K19 Strategy pools (story, hook, voice, reel, humour, thumbnail, title) rotate and learn; weak ones retire after 5+ videos; Claude invents replacements. Never fewer than 5 active.
- K20 No watermark/provenance tampering. Honest AI label on.

## Safety (v7.2)
- K23 Keys never appear in logs, the Sheet, emails or error files (automatic scrubbing; keys sent in hidden headers). The Google key is emailed once, never printed.
- K24 Unreleased reels/covers live in your private Google Drive, not on public GitHub.
- K25 Repair Bot: max 3 attempts per 7 days, never the same error twice. 3 failed episodes in a row → one email.
- K26 Narration must reach 8:13 before any money is spent; if short, the writer extends it (free).
- K27 New images per video capped at stills + living + kling (~60); other shots reuse them with different camera moves.

## Money
- K21 Budget ≈ ₹2,200–2,500/month (Claude ≈ ₹35–50/video after v7.2 trims). Cap = max(₹2,500, 10% of money actually received last month), ≤ ₹25,000. Near cap: drop Kling → living stills → Opus.
- K22 Only 2 paid services: fal.ai and Anthropic. Recommended: switch on auto-reload in both, then set AUTO_RELOAD_ON = TRUE.
