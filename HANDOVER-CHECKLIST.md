# Handover Checklist — Tomer → Hadar

For Tomer: things to do *outside* the repo to actually complete the handover.
Hadar's `ONBOARDING.md` lists everything he needs *from* you; this file lists
everything you need to *give*.

> Status legend: `[ ]` = not done, `[x]` = done, `[~]` = in progress / partial

---

## Credentials & access (out-of-band — Signal/encrypted message, not git)

### Supabase
- [ ] Decide on transfer model:
  - **Option A** — invite Hadar as a collaborator/owner on the existing project
    (simplest, Hadar uses same DB you've been writing to)
  - **Option B** — Hadar provisions his own Supabase project; we hand him the schema
    + a one-time export of the current 25,585 rows
- [ ] Execute the chosen option
- [ ] Share `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` via Signal (or
      let him pull them from his own project dashboard if Option B)

### Gemini API key
- [ ] Decide on transfer model:
  - **Option A** — share existing billed key (simplest, but Hadar uses your billing)
  - **Option B** — Hadar gets his own key from a billed GCP project; verify billing
    is on before he tries the first sync (free tier = instant `limit: 0`)
- [ ] If Option B: walk through enabling billing on his GCP project to avoid the
      Gemini quota gotcha — see `.planning/docs/TRIBAL-KNOWLEDGE.md` #2
- [ ] Share key via Signal

### Server SSH (`ceci`, 178.62.39.248)
- [ ] Hadar generates a new SSH key pair on his machine: `ssh-keygen -t ed25519`
- [ ] He sends you his **public** key (`~/.ssh/id_ed25519.pub` or similar)
- [ ] You add it to the server: `ssh ceci "echo '<his pubkey>' >> ~/.ssh/authorized_keys"`
- [ ] He sets up `~/.ssh/config` per the snippet in `ONBOARDING.md` §2
- [ ] He verifies: `ssh ceci "hostname && docker ps | grep gov2db"`
- [ ] (Optional but recommended) Once Hadar's key is confirmed working, rotate
      yours off the server if you're stepping away permanently

### GitHub repo
- [ ] Add Hadar as collaborator on `TomerGutman1/CECI_SCRAPER` (Settings → Collaborators)
- [ ] If you're transferring full ownership, use Settings → Transfer ownership
- [ ] He clones via his GitHub credentials

### Docker Hub (optional)
- [ ] Decide if Hadar needs push access to `tomerjoe/gov2db-scraper`. The default
      deploy path on ceci is `git pull + docker compose build` (rebuilds on server),
      so Docker Hub is only needed if you're doing prebuilt-image deploys.
- [ ] If yes: share Docker Hub creds (or have him use his own Docker Hub and update
      `docker-compose.yml` to point to his image)

---

## Knowledge transfer

These are already done as part of the handover-prep session (commit `<TBD>`):

- [x] `ONBOARDING.md` written and committed
- [x] `.planning/docs/TRIBAL-KNOWLEDGE.md` — 16 non-obvious gotchas migrated out of
      Claude Code personal memory
- [x] `CLAUDE.md` "Current Status" refreshed to May 2026 + added "Known Blockers" section
- [x] `README.md` rewritten — removed dead `OPENAI_API_KEY` references and removed
      `make migrate-*` commands that point to deleted scripts
- [x] `.planning/handoff.md` overwritten with May 2026 snapshot
- [x] Working tree cleaned (Feb 23 cleanup committed, 7 new ops scripts tracked,
      `taste.sh` vendored from server)
- [ ] `ShareOnboardingGuide` link generated and shared with Hadar (next step)

## Live walkthrough (recommended, ~1 hour)

Once Hadar has credentials, run through `ONBOARDING.md` §1-7 together:

- [ ] Verify local Docker comes up clean on his machine
- [ ] Verify SSH works to ceci
- [ ] Run `taste.sh` together so he sees production state
- [ ] Do one trivial commit + deploy together so he understands the loop
- [ ] Discuss top open work (see `ONBOARDING.md` "Day 3" section)

## Final transfer

- [ ] If transferring ownership of GitHub repo, do it now
- [ ] If keeping shared access, decide cadence ("I'm available for questions for
      30 days, then it's yours")
- [ ] (Optional) Schedule a 2-week check-in to debug whatever surprised Hadar in
      the first cron cycles

---

## Things you should explicitly tell Hadar verbally

(These are in the docs but worth saying out loud)

- The Gemini billing thing is real — free tier dies the instant your trial expires.
  Don't think the code is broken; check `limit: 0` first.
- Don't run `make sync` on his Mac. Use Docker.
- The 02:00 IDT cron means he won't see it run in real-time unless he stays up. Read
  logs the morning after.
- The gov.il `x-client-id` is public, not a secret — but the URL gateway will move
  again at some point. The self-healing layer should adapt; if it doesn't, manual
  update to the constants is the fix.
- The 6 PDF-only decisions are intentional gaps. Don't burn a day "fixing" them
  unless we decide that 0.1% gap matters.

---

## After handover is complete

- [ ] Move this file to `.planning/archive/HANDOVER-CHECKLIST-2026-05-19.md`
      (or delete) so future readers aren't confused about who's running things
