# eatwatah — Claude Project Context

## What is eatwatah
A Telegram bot for F&B discovery and recommendations built 
for young Singaporeans. Users can build a shared wishlist 
of food spots, log visits with ratings and reviews, and get 
AI-powered personalised recommendations via /ask.

Rebuilt from a working prototype called Date Darling which 
had these limitations:
- Google Sheets as the only database (single sheet, not scalable)
- Only 2 hardcoded users
- No group chat support
- Silent crashes with zero error handling

eatwatah is the proper rebuild — scalable, multi-user, 
multi-group, with a real database and AI layer.

---

## Full PRD
Two PRD files exist. Read the correct one for the feature you are implementing:

/docs/eatwatah_v2_prd.md — V2 source of truth (current)
Use this for: /start welcome copy, /viewwishlist WebApp,
area grouping fix, /deactivate.

/docs/eatwatah_prd.md — V1 source of truth (historical reference)
Use this for: schema (Section 4), error philosophy (Section 9),
bot personality (Section 1.5), privacy rules (Section 7).
V1 spec is authoritative for anything not covered in V2 PRD.

Where V2 PRD explicitly contradicts V1, V2 wins. See the
"V1 Reversals" section below for the full list of deliberate changes.

Never make architectural decisions that contradict the active PRD.

---

## Stack
- Language: Python 3.11+
- Telegram framework: python-telegram-bot v20+ (async)
- Database ORM: SQLAlchemy (async)
- Database: Railway PostgreSQL via DATABASE_URL
- Migrations: Alembic
- HTTP client: httpx
- AI: OpenAI API
- Places: Google Places API
- Environment: python-dotenv
- WebApp: single-file HTML/CSS/JS + Telegram WebApp SDK (V2, /viewwishlist)
- REST API: FastAPI (V2, serves WebApp — Telegram initData auth)

---

## Environments

Two environments exist. Never skip dev and deploy straight to prod.

| | Dev | Prod |
|---|---|---|
| Telegram bot | @eatwatah_dev_bot | @eatwatah_bot (live users) |
| Railway project | eatwatah-dev | eatwatah (main project) |
| Database | Dev Railway PostgreSQL | Prod Railway PostgreSQL |
| Env file (local) | `.env.dev` | `.env` |

**Running locally against the dev bot:**
```
ENV_FILE=.env.dev python bot/main.py
```

**Running locally against prod:**
```
python bot/main.py
```
Don't do this unless you have a specific reason — prod has real users.

**Deploying to dev Railway project:**
```
railway link   # select eatwatah-dev project
railway up
```

**Deploying to prod Railway project:**
```
railway link   # select eatwatah (main) project
railway up
```

**Rules:**
- All V2 feature work is tested on dev first
- Only deploy to prod when dev is confirmed stable
- Dev Railway project has its own DATABASE_URL — separate DB,
  no shared data with prod
- Both Railway projects have their own full set of env vars
  (bot token, DB URL, API keys). Set them in each project's
  Railway dashboard. Do not assume prod vars carry over.

---

## Environment
Always work inside the virtual environment.

Activate:
  Windows:   venv\Scripts\activate

Never install packages globally.
All pip installs must be done with venv activated.
requirements.txt is the source of truth for package versions.

---

## Project Structure
eatwatah/
├── CLAUDE.md
├── docs/
│   ├── eatwatah_prd.md        ← V1 PRD (historical reference)
│   └── eatwatah_v2_prd.md     ← V2 PRD (current source of truth)
├── bot/
│   ├── main.py              ← bot entry point
│   └── handlers/
│       ├── start.py
│       ├── add.py
│       ├── view_wishlist.py
│       ├── visit.py
│       ├── view_visited.py
│       ├── delete.py
│       ├── ask.py
│       ├── deactivate.py    ← V2: reversible account pause
│       └── delete_account.py
├── services/
│   └── recommendation_service.py  ← AI engine, never import from /bot
├── api/                     ← V2: FastAPI REST endpoints for WebApp
│   └── routes/
│       └── wishlist.py      ← serves /viewwishlist WebApp data
├── jobs/                    ← reserved for V3: background scheduled jobs
├── webapp/                  ← V2: single-file HTML/CSS/JS WebApp
│   └── wishlist.html
├── db/
│   ├── connection.py        ← SQLAlchemy engine and session
│   ├── models.py            ← all 6 table models
│   ├── context.py           ← chat context detection utility
│   └── migrations/          ← Alembic migration files
├── pipelines/               ← reserved for v3 external signal pipeline
├── .env                     ← never commit this
├── .gitignore
└── requirements.txt

---

## Non-Negotiable Architecture Rules

1. DECOUPLED RECOMMENDATION ENGINE
   /services/recommendation_service.py must never import
   anything from /bot/
   The bot handler in /bot/handlers/ask.py only:
   - Sends the holding message
   - Calls recommendation_service.get_recommendations(query, chat_id, user_id)
   - Formats and sends the returned results
   This separation exists so future signal enrichment (V3)
   can plug into the service layer without touching bot handlers.

2. CONTEXT DETECTION ON EVERY COMMAND
   Import and call is_private_chat(chat_id, user_id) from 
   db/context.py in every single command handler.
   If chat_id == user telegram_id → private DM context
   Else → group chat context
   Never hardcode context assumptions.

3. ALL DB OPERATIONS IN TRY/EXCEPT/FINALLY
   Every database session must be wrapped in try/except/finally.
   Always close sessions in the finally block.
   Never let a DB failure cause a silent crash.

4. AUTO-REGISTRATION SAFETY NET
   Every command handler must check if the user exists in 
   the Users table before processing.
   If not found: register them silently, then continue.
   Prevents crashes from users who bypassed /start.

5. NEVER EXPOSE RAW ERRORS TO USERS
   No Python exceptions, stack traces, or technical messages 
   shown to users ever.
   Every failure has a friendly response in the bot's tone.
   All errors logged to the Errors table with full context.

6. SOFT DELETES ONLY
   Never hard delete any row from WishlistEntries or Visits.
   Set status = 'deleted' on WishlistEntries.
   Visit history is never deleted under any circumstance.

7. REST API: VALIDATE initData ON EVERY REQUEST
   The FastAPI wishlist endpoint must validate the Telegram WebApp
   initData HMAC-SHA256 hash against TELEGRAM_BOT_TOKEN before
   returning any data. Return HTTP 403 on failure — never trust a
   client-supplied chat_id without this check.
   The endpoint must return both status='wishlist' AND status='visited'
   entries. The existing get_wishlist_entries helper only returns
   status='wishlist' and cannot be used as-is for the WebApp endpoint.

---

## Bot Personality & Tone
Read Section 1.5 of the PRD for full guidance and examples.

Summary:
- Casual and warm — speaks like a real person, never robotic
- Singaporean at heart — light Singlish is encouraged where natural
  (confirm, shiok, wah, anot, etc.)
- NEVER use: lah, leh, or eh — these read as forced/cringey
- Encouraging, never judgmental
- Concise — no long walls of text
- Playful but useful — humour welcome, never at cost of clarity

Examples of correct tone:
  "Nice choice! Added to your wishlist 🔖"
  "⚠️ <place> already exists in your wishlist."
  "Shiok! Logged. The more you review, the better I get 🍜"
  "Hmm, nothing matching that. Try a different area?"
  "Something went wrong on our end — not your fault! 
   Try again in a bit 🙏"

---

## Error Philosophy
Read Section 9 of the PRD for full error state specifications.

Summary:
- Never go silent — every failure has a response
- Never expose raw errors — always friendly human language
- Never fake success — if something failed, say so honestly
- Always log server-side — Errors table + Telegram alert 
  to DEVELOPER_TELEGRAM_ID for critical failures
- Retry logic: DB operations retry once silently before 
  surfacing error to user

---

## V1 Reversals — Deliberate Decisions in V2
These are places where V2 explicitly overrides V1. Do not treat them
as conflicts — they are resolved decisions.

| Topic | V1 | V2 Decision |
|---|---|---|
| /start onboarding | Multi-step: intro, curated suggestions, first-add celebration | Use V2 welcome message text, but keep V1 curated suggestions + first-add celebration flow |
| /ask scope | Must include ≥1 result from outside wishlist | KEEP V1 rule — delete V2's "wishlist-only" line. External discovery stays. |
| Phase 2 pipeline | Reddit + TikTok + Instagram via official APIs | Retired. Reddit ToS prohibits AI/ML use. TikTok/Instagram have no stable official API. Google Places signals replace the whole plan. |
| AI provider | OpenAI API | Keep OpenAI — V2 PRD's Claude Haiku references are incorrect, use OpenAI models |
| /deleteaccount | Shipped in V1 (anonymise data) | Keep. V2 adds /deactivate as a separate reversible pause. Both coexist. |
| Shareable URLs | Deferred to V2 | Still no action — no data model changes needed now |

---

## V1 Scope — Shipped
/start          onboarding flow, new vs returning user
/add            Google Places search, confirm, save to wishlist
/viewwishlist   grouped by region, newest first
/visit          multi-step: rating, review, occasion, photos
/viewvisited    visit history with per-user ratings
/delete         soft delete with confirmation
/ask            AI recommendation engine
/deleteaccount  PDPA compliance, anonymise user data

Full error handling across all commands
Group vs solo context detection on all commands
Auto-registration safety net on all commands

---

## V2 Scope — Build These
See /docs/eatwatah_v2_prd.md for full specs.

/viewwishlist   WebApp redesign: map + search + filters + slide-up card
/deactivate     new command — reversible account pause (not /deleteaccount)
area grouping   reverse geocode lat/lng → URA planning area at /add time
                + one-time backfill migration on existing entries
middleware      auto-reactivation on every command for deactivated users
REST API        FastAPI endpoints for WebApp (Telegram initData auth)
/ask cleanup    remove follow-up prompt after every /ask response
                (Section 4.3.2) — 3-line change in bot/handlers/ask.py

## Deferred — Do Not Build
/ask upgrades   all V2 AI improvements deferred to V3: place_signals table,
                nightly Google Places job, review velocity scoring, sentiment
                analysis, Popular Times, and the five engine improvements
                (cuisine fingerprint, overdue wishlist, source labelling,
                800m area constraint, group/time context, personalised
                no-arg /ask). Full spec preserved in V2 PRD Section 4.
background job  scheduler for nightly place_signals job — deferred with it
/deleteaccount  permanent data wipe (v2.1+ — PDPA critical, must ship
                before scaling beyond friend group. V1 /deleteaccount
                handles anonymisation; permanent wipe is a separate,
                harder operation. See V2 PRD Section 8.4.)
Monthly recap   requires background scheduler — revisit when user base
                justifies it
Shareable URLs  eatwatah.com/u/sarah — data model TBD, page deferred
/deals          depends on sponsored listings being live
Full web product eatwatah.com — build after WebApp proven
Instagram pipeline ToS risk, deferred indefinitely

---

## Database — 6 Tables
Full schema in Section 4 of V1 PRD and in db/models.py.
PlaceSignals table is deferred to V3.

Quick reference:
Users             telegram_id, display_name, joined_at, is_deleted
Chats             chat_id, chat_type, chat_name, created_at
WishlistEntries   chat_id, google_place_id, name, address, area,
                  lat, lng, added_by, status, any_branch,
                  notes, date_added
Visits            chat_id, google_place_id, logged_by, rating,
                  review, occasion, photos, visited_at
SponsoredRestaurants  google_place_id, name, cuisine_tags, area,
                      deal_description, active_from,
                      active_until, is_active
Errors            timestamp, telegram_id, chat_id, command,
                  error_type, message

---

## Environment Variables
All in .env — never commit this file.

TELEGRAM_BOT_TOKEN       from BotFather
GOOGLE_PLACES_API_KEY    from Google Cloud Console
OPENAI_API_KEY           from OpenAI
DATABASE_URL             auto-provided by Railway PostgreSQL
DEVELOPER_TELEGRAM_ID    your personal Telegram ID for alerts

---

## Privacy Rules
Read Section 7 of the PRD for full details.

Summary:
- Users retain rights over their own personal data
- /deleteaccount anonymises user data, preserves group 
  contributions as "Deleted User"
- Never sell or share individual user data
- Sponsored matching uses aggregated signals only
- Singapore PDPA applies — inform users what is collected

---

## Phase 2 — Do Not Build Yet
After v1 is live, a separate background signal pipeline 
will be built as a standalone service in /pipelines/.
It will enrich /ask recommendations with external data from:
- Reddit Singapore (official PRAW API)
- TikTok (official Research API)  
- Instagram (Meta Graph API)
- Google Places (already in stack)

The reason /services/recommendation_service.py must stay 
decoupled from /bot/ is precisely so Phase 2 can plug into 
the service layer without touching the bot handlers.

Full Phase 2 spec in Section 12 of the PRD.
Do not build any of this in v1.