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
/docs/eatwatah_prd.md is the single source of truth.
Read the relevant section before implementing any feature.
Never make architectural decisions that contradict the PRD.

Section reference guide:
- V1 Scope Summary → what to build now vs defer
- Section 1.5    → bot personality and tone of voice
- Section 3      → all feature specifications
- Section 4      → full database schema (5 tables)
- Section 5      → tech stack and architecture
- Section 7      → privacy and data rules
- Section 9      → error states and error philosophy
- Section 10     → future direction (do not build yet)
- Section 11     → Phase 2 pipeline (do not build yet)

---

## Stack
- Language: Python 3.11+
- Telegram framework: python-telegram-bot v20+ (async)
- Database ORM: SQLAlchemy (async)
- Database: Railway PostgreSQL via DATABASE_URL
- Migrations: Alembic
- HTTP client: httpx
- AI: Open AI API
- Places: Google Places API
- Environment: python-dotenv

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
│   └── eatwatah_prd.md
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
│       └── delete_account.py
├── services/
│   └── recommendation_service.py  ← AI engine, never import from /bot
├── db/
│   ├── connection.py        ← SQLAlchemy engine and session
│   ├── models.py            ← all 5 table models
│   ├── context.py           ← chat context detection utility
│   └── migrations/          ← Alembic migration files
├── pipelines/               ← empty, Phase 2 only
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
   - Calls recommendation_service.get_recommendations(
       query, chat_id, user_id)
   - Formats and sends the returned results
   This separation is mandatory for Phase 2 extensibility.

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

## V1 Scope — Build These
/start          onboarding flow, new vs returning user
/add            Google Places search, confirm, save to wishlist
/viewwishlist   grouped by region, newest first
/visit          multi-step: rating, review, occasion, photos
/viewvisited    visit history with per-user ratings
/delete         soft delete with confirmation
/ask            AI recommendation engine (3-layer)
/deleteaccount  PDPA compliance, anonymise user data

Full error handling across all commands
Group vs solo context detection on all commands
Auto-registration safety net on all commands

---

## V2 Scope — Do Not Build
Monthly recap scheduled message
Shareable wishlist web link
Sponsored listings logic (schema exists, logic deferred)
/deals command
Phase 2 external signal pipeline (Reddit, TikTok, Instagram)

---

## Database — 5 Tables
Full schema in Section 4 of PRD and in db/models.py.

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
OPENAI_API_KEY           from OPENAI
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