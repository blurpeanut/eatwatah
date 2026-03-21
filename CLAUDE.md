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
Three PRD files exist. Read the correct one for the feature you are implementing:

/docs/eatwatah_v3_prd.md — V3 source of truth (current)
Use this for: domain setup, Telegram Mini App registration,
group /viewwishlist deep link, admin dashboard, CommandLogs.

/docs/eatwatah_v2_prd.md — V2 source of truth (previous)
Use this for: /start welcome copy, /viewwishlist WebApp,
area grouping fix, /deactivate.

/docs/eatwatah_prd.md — V1 source of truth (historical reference)
Use this for: schema (Section 4), error philosophy (Section 9),
bot personality (Section 1.5), privacy rules (Section 7).
V1 spec is authoritative for anything not covered in V2 or V3 PRD.

Where a later PRD explicitly contradicts an earlier one, the later one wins.
See the "V1 Reversals" section below for the full list of deliberate changes.

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
- All V3 feature work is tested on dev first
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
│   ├── eatwatah_v2_prd.md     ← V2 PRD (previous)
│   └── eatwatah_v3_prd.md     ← V3 PRD (current source of truth)
├── bot/
│   ├── main.py              ← bot entry point
│   └── handlers/
│       ├── start.py
│       ├── add.py
│       ├── view_wishlist.py  ← V3: branches private vs group
│       ├── visit.py
│       ├── view_visited.py
│       ├── delete.py
│       ├── ask.py
│       ├── deactivate.py    ← V2: reversible account pause
│       └── delete_account.py
├── services/
│   └── recommendation_service.py  ← AI engine, never import from /bot
├── api/                     ← FastAPI REST endpoints
│   ├── auth.py              ← Telegram initData validation
│   ├── main.py              ← FastAPI app, includes all routers
│   └── routes/
│       ├── wishlist.py      ← serves /viewwishlist WebApp data
│       └── admin.py         ← V3: /api/admin/stats + /api/admin/command-usage
├── jobs/                    ← reserved for V3: background scheduled jobs
├── webapp/                  ← single-file HTML/CSS/JS WebApps
│   ├── index.html           ← /viewwishlist WebApp (V3: reads start_param)
│   └── admin.html           ← V3: ER diagram + stats + command bar chart
├── db/
│   ├── connection.py        ← SQLAlchemy engine and session
│   ├── models.py            ← all 7 table models (incl. CommandLog)
│   ├── helpers.py           ← DB helpers incl. log_command()
│   ├── context.py           ← chat context detection utility
│   └── migrations/          ← Alembic migration files
├── scripts/                 ← one-off ops scripts (audit, backfill)
├── tests/                   ← pytest test suite
├── start.py                 ← unified entry: PTB bot + uvicorn FastAPI
├── Procfile                 ← web: python start.py
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
   This separation exists so future signal enrichment can plug
   into the service layer without touching bot handlers.

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

7. REST API: VALIDATE initData ON EVERY WISHLIST REQUEST
   The FastAPI wishlist endpoint must validate the Telegram WebApp
   initData HMAC-SHA256 hash against TELEGRAM_BOT_TOKEN before
   returning any data. Return HTTP 403 on failure — never trust a
   client-supplied chat_id without this check.
   The endpoint must return both status='wishlist' AND status='visited'
   entries. The existing get_wishlist_entries helper only returns
   status='wishlist' and cannot be used as-is for the WebApp endpoint.

8. ADMIN ROUTES REQUIRE HTTP BASIC AUTH
   Every route under /admin and /api/admin/* must use FastAPI's
   HTTPBasic dependency. Credentials come from env vars ADMIN_USERNAME
   and ADMIN_PASSWORD — never hardcoded. Return 401 with
   WWW-Authenticate: Basic on failure. No exceptions.

9. COMMAND LOGGING IS FIRE-AND-FORGET
   log_command(command, chat_id, user_id) in db/helpers.py must be
   called in every handler after auto-registration and before main logic.
   Wrap it in try/except and silently swallow all failures.
   Never let command logging crash or slow a user-facing command.

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
Read Section 9 of the V1 PRD for full error state specifications.

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

## V2 Scope — Shipped
/viewwishlist   WebApp redesign: map + search + filters + slide-up card
/deactivate     reversible account pause (not /deleteaccount)
area grouping   reverse geocode lat/lng → URA planning area at /add time
                + one-time backfill migration on existing entries
middleware      auto-reactivation on every command for deactivated users
REST API        FastAPI endpoints for WebApp (Telegram initData auth)
/ask cleanup    removed follow-up prompt after every /ask response

---

## V3 Scope — Build These
See /docs/eatwatah_v3_prd.md for full specs.

### Domain + Mini App (ops, then code)
domain          eatwatah.com → Cloudflare DNS → Railway prod custom domain
mini app        Register @eatwatah_bot on BotFather as Telegram Mini App
                Short name: wishlist → t.me/eatwatah_bot/wishlist

### Bot handler change
view_wishlist   Branch on chat type:
                - Private chat: keep WebAppInfo inline button (V2 behaviour)
                - Group chat: send url= button with MINI_APP_LINK?startapp=<chat_id>
                Fallback: text list if MINI_APP_LINK not set (never crash)

### WebApp change
index.html      Update chat_id resolution order:
                start_param → urlChatId → initDataUnsafe.chat.id → user.id
                start_param = tg.initDataUnsafe.start_param (set by deep link)

### Admin dashboard (eatwatah.com/admin)
CommandLogs     New table: id, command, called_at, chat_id, user_id
                Alembic migration required
log_command()   New helper in db/helpers.py — fire-and-forget async insert
                Called in all 9 handlers after auto-registration
admin.py        GET /api/admin/stats — user/wishlist/visit/chat/error/sponsored counts
                GET /api/admin/command-usage?days= — per-command call counts
                Both routes: HTTP Basic Auth (ADMIN_USERNAME, ADMIN_PASSWORD)
admin.html      Panel 1: static CSS ER diagram — all 7 tables + FK arrows
                Panel 2: stat cards grid (fetches /api/admin/stats)
                Panel 3: horizontal bar chart (fetches /api/admin/command-usage)
                         time range selector: All time / 30 days / 7 days
api/main.py     Include admin router, serve admin.html at /admin

### New env vars (add to both Railway dashboards)
WEBAPP_BASE_URL  https://eatwatah.com (prod) / Railway dev URL (dev)
MINI_APP_LINK    t.me/eatwatah_bot/wishlist (prod) / t.me/eatwatah_dev_bot/wishlist (dev)
ADMIN_USERNAME   e.g. "admin"
ADMIN_PASSWORD   strong secret, set in Railway only

## Deferred — Do Not Build
/ask upgrades   all V3 AI improvements deferred: place_signals table,
                nightly Google Places job, review velocity scoring, sentiment
                analysis, Popular Times, and the five engine improvements
                (cuisine fingerprint, overdue wishlist, source labelling,
                800m area constraint, group/time context, personalised
                no-arg /ask). Full spec preserved in V2 PRD Section 4.
background job  scheduler for nightly place_signals job — deferred with it
/deleteaccount  permanent data wipe (v2.1+ — PDPA critical, must ship
                before scaling beyond friend group. V1 /deleteaccount
                handles anonymisation; permanent wipe is a separate,
                harder operation.)
Monthly recap   requires background scheduler — revisit when user base
                justifies it
Shareable URLs  eatwatah.com/u/sarah — data model TBD, page deferred
/deals          depends on sponsored listings being live
Landing page    eatwatah.com homepage — P2, spec in V3 PRD Section 8.
                Non-blocking; ship Mini App + admin first.
Instagram pipeline ToS risk, deferred indefinitely

---

## Database — 7 Tables
Full schema in Section 4 of V1 PRD and in db/models.py.
PlaceSignals table is deferred.

Quick reference:
Users             telegram_id, display_name, joined_at, is_deleted,
                  is_deactivated
Chats             chat_id, chat_type, chat_name, created_at
WishlistEntries   id, chat_id (FK→Chats), google_place_id, name,
                  address, area, cuisine_type, lat, lng,
                  added_by (FK→Users), status, any_branch,
                  notes, date_added
Visits            id, chat_id (FK→Chats), google_place_id,
                  logged_by (FK→Users), place_name, rating,
                  review, occasion, photos, visited_at
SponsoredRestaurants  google_place_id, name, cuisine_tags, area,
                      deal_description, active_from,
                      active_until, is_active
Errors            id, timestamp, telegram_id, chat_id, command,
                  error_type, message
CommandLogs       id, command, called_at, chat_id (FK→Chats),
                  user_id (FK→Users)   ← V3: new table

---

## Environment Variables
All in .env — never commit this file.

TELEGRAM_BOT_TOKEN       from BotFather
GOOGLE_PLACES_API_KEY    from Google Cloud Console
OPENAI_API_KEY           from OpenAI
DATABASE_URL             auto-provided by Railway PostgreSQL
DEVELOPER_TELEGRAM_ID    your personal Telegram ID for alerts
WEBAPP_BASE_URL          Railway URL or eatwatah.com — controls WebApp button
MINI_APP_LINK            t.me/<bot>/wishlist — controls group deep link button
ADMIN_USERNAME           HTTP Basic Auth username for /admin
ADMIN_PASSWORD           HTTP Basic Auth password for /admin

---

## Privacy Rules
Read Section 7 of the V1 PRD for full details.

Summary:
- Users retain rights over their own personal data
- /deleteaccount anonymises user data, preserves group
  contributions as "Deleted User"
- Never sell or share individual user data
- Sponsored matching uses aggregated signals only
- Singapore PDPA applies — inform users what is collected
