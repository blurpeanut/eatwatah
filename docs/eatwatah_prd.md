**Product Requirements Document**

**eatwatah**

*Your AI-Powered Companion on Telegram*

|                  |                                |
|------------------|--------------------------------|
| **Version**      | 1.0 — Initial Release          |
| **Status**       | Draft                          |
| **Date**         | February 2026                  |
| **Platform**     | Telegram Bot                   |
| **Target Users** | Young Singaporeans on Telegram |

# V1 Scope Summary

This section is the single source of truth for what gets built in v1. Anything not listed here is either a future feature or background architecture that does not need a user-facing implementation yet.

## In Scope — Build for V1

| **Feature**                 | **Notes**                                           |
|-----------------------------|-----------------------------------------------------|
| /start onboarding           | New user flow with curated starter suggestions      |
| /add                        | Google Places search, top 3 matches, confirm & save |
| /viewwishlist               | Grouped by city \> region, newest first             |
| /visit                      | Rating, review, occasion, photos                    |
| /viewvisited                | With per-user ratings and review snippets           |
| /delete                     | Soft delete with confirmation                       |
| /ask                        | AI recommendations with personal + external context |
| Group vs. solo context      | Auto-detected via chat_id — no user action needed   |
| Photo support on /visit     | Telegram file_id storage                            |
| Manual place entry fallback | Triggered when Google Places returns no results     |
| Error states                | All four failure types with friendly bot responses  |
| Railway PostgreSQL          | Full schema as per Section 4                        |
| /deleteaccount              | PDPA compliance — anonymises user data on request   |

## Deferred to V2

| **Feature**             | **Reason for Deferral**                                    |
|-------------------------|------------------------------------------------------------|
| Monthly recap message   | Requires background job scheduler — not core to v1 utility |
| Shareable wishlist link | Requires a web view layer outside the Telegram bot         |
| Sponsored listings      | No advertisers yet — schema is ready, logic is not needed  |
| /deals command          | Depends on sponsored listings being live                   |

# 1. Product Overview

eatwatah is a Telegram bot for anyone who loves eating out in Singapore but is tired of forgetting good spots, losing TikTok saves, or drawing a blank when someone asks "where should we go?". It lets users build a personal F&B database through casual chat — tracking wishlists, logging visits with reviews, and surfacing smart AI-powered recommendations that go well beyond a simple search.

The name is a nod to the quintessentially Singaporean question: "eat what ah?" — eatwatah lives where Singaporeans already spend their time, in Telegram.

## 1.1 Problem Statement

Food spots are discovered through TikTok, word of mouth, and casual chats — then immediately lost. People resort to static lists, saved posts, or just asking friends the same question every weekend. This creates friction:

- Hard to query quickly ("What's good near Bugis tonight?")

- No memory of what you've tried, rated, or liked

- Generic tools like Google Maps don't know your personal taste

- No easy way to share and sync a living list with friends or a partner

## 1.2 Vision

A conversational F&B companion that gets smarter the more you use it. It knows what you've eaten, what you loved, and what you'd probably enjoy next — and it can recommend places you've never heard of, not just ones already on your list.

## 1.3 Goals

- Give users a living, queryable personal F&B database inside Telegram

- Make logging and retrieving food spots effortless via chat

- Build an AI recommendation engine that learns individual taste profiles and surfaces genuinely useful, personalised suggestions

- Surface great options beyond the user's wishlist using external data

- Create a portfolio-worthy, extensible project

## 1.4 Non-Goals (v1)

- Native iOS/Android app

- Integration with booking platforms (OpenTable, Chope)

- Public social feed or follower system

- Restaurant-side business tools

## 1.5 Bot Personality & Tone of Voice

eatwatah's personality is a core part of the product — not an afterthought. It should feel like texting a friend who happens to know every good food spot in Singapore, not like using a utility tool.

**Guiding Principles**

- Casual and warm — speaks like a real person, never robotic or corporate

- Singaporean at heart — very light Singlish flavour is encouraged where natural (lah, eh, confirm, shiok, etc.), but never overdone to the point of parody

- Encouraging, never judgmental — whether a user rates something 1★ or 5★, the bot celebrates the act of logging

- Concise — gets to the point quickly; no long walls of text

- Playful but useful — humour and personality are welcome, but never at the cost of actually answering the question

**Tone Examples**

| **Situation**             | **Example Bot Response**                                                                       |
|---------------------------|------------------------------------------------------------------------------------------------|
| First wishlist add        | "Nice choice! Added to your wishlist 🔖 Keep adding and I'll get better at knowing your vibe." |
| Recommendation result     | "Based on what your group likes, try this 👇"                                                  |
| Place already in wishlist | "⚠️ \<place\> already exists in your wishlist."                                                |
| No results found          | "Hmm, nothing matching that leh. Try a different area or vibe and I'll look again?"            |
| After logging a visit     | "Shiok! Logged. The more you review, the better I get at finding your next favourite spot 🍜"  |

# 2. Users & Context

## 2.1 Target Users

Primary: Young Singaporeans (18–35) who are active on Telegram and love eating out. They discover food through TikTok, Instagram, and friends — but have no reliable system to track and recall those spots.

Secondary: Anyone on Telegram who wants a smarter personal food log — couples, friend groups, solo food explorers.

## 2.2 User Needs

| **User Need**     | **Description**                                                                        |
|-------------------|----------------------------------------------------------------------------------------|
| Quick add         | Add a food spot in seconds without leaving Telegram                                    |
| Fast lookup       | Instantly find options filtered by area, vibe, or cuisine                              |
| Personal memory   | Log visits with ratings and notes to build a taste profile                             |
| Smart suggestions | AI-driven recommendations based on past preferences AND external discovery             |
| Photo logging     | Attach photos to visited places for memories                                           |
| Shared use        | Multiple users (e.g. friends, couples) can contribute to a shared list in a group chat |

# 3. Feature Specifications

## 3.1 /start — Onboarding

**Description**

The entry point for every user. Behaviour differs depending on whether the user is new or returning.

**Returning User Experience**

Sends a warm welcome back message with a live snapshot: wishlist count, visited count, and a nudge to use /ask if they're deciding where to eat.

**First-Time User Experience**

New users land with zero data, so the bot cannot yet personalise anything. The onboarding flow does three things: introduces eatwatah's personality, encourages the user to start building their wishlist, and provides immediate value by surfacing curated starter suggestions so the bot is useful from minute one.

**First-Time Onboarding Flow**

1.  Bot sends a friendly intro: what eatwatah is, what it can do, and how to get started — written in a casual, warm tone that reflects the bot's personality

2.  Bot surfaces 3-5 curated starter suggestions ("Places other Singaporeans are saving right now") with inline buttons to add any of them directly to their wishlist

3.  Bot prompts: "Or just tell me a place you've been meaning to try — I'll find it for you 👀"

4.  Once the user adds their first wishlist item, the bot celebrates it and explains that the more they log, the smarter /ask gets

**Acceptance Criteria**

- New vs. returning state detected based on whether user has any DB records

- Curated starter list is maintained and refreshed periodically (not hardcoded forever)

- Inline buttons on starter suggestions allow one-tap wishlist add without typing /add

- First wishlist add triggers a celebratory confirmation message

- Returning users see their stats snapshot, not the onboarding flow

## 3.2 /add — Add to Wishlist

**Description**

User sends /add \<Location Name\> and the bot queries the Google Places API to return the top 3 matches. User confirms the correct entry, which is saved with a Google Place ID.

**User Journey**

5.  User sends: /add PS Cafe Raffles City

6.  Bot replies: "Searching for your place… please wait."

7.  Bot returns top 3 Google Places matches (name, address, rating, Google Maps link)

8.  User selects correct match (or "Any branch")

9.  Bot confirms: "Added PS Cafe to your wishlist!" with follow-up inline buttons: Add Note / Mark Visited / Delete

**Acceptance Criteria**

- Duplicate entries are blocked (matched by Google Place ID)

- Fuzzy/typo tolerance via Google Places search

- "Any branch" option stores place without specific location lock

- Added_by field records which user added the entry

- User can optionally add a note (e.g. reason they want to go)

## 3.3 /viewwishlist — View Wishlist

**Description**

Displays all wishlist items, grouped by city then by region (for Singapore: Central, North, East, West, North-East). Ordered newest to oldest within each group.

**Acceptance Criteria**

- Grouped display by city \> region

- Shows place name, address, who added it, and date added

- Handles empty wishlist gracefully

## 3.4 /visit — Log a Visit

**Description**

User logs a completed date. The bot prompts for a rating, review, occasion, and optional photos. Each user can log a separate rating for the same place.

**User Journey**

- User sends /visit \<Location Name\> or taps inline button after /add

- Bot asks for rating out of 5 (inline buttons: 1–5 ⭐)

- Bot asks for a short review (text input)

- Bot asks for photos (optional — user can skip)

- Entry is saved; wishlist status updated to "visited"

- Bot informs user that entry is saved

**Acceptance Criteria**

- Each user has independent rating per place

- Multiple visits to the same place create separate log entries

- Timestamps stored automatically

- Photos stored with reference to the place entry

- Visit can be logged even if place wasn't on wishlist first

## 3.5 /viewvisited — View Visited Places

**Description**

Shows all visited places with ratings and reviews. For groups larger than 2, displays average rating only.

**Acceptance Criteria**

- Shows both users' ratings side by side for ≤ 2 users

- Grouped and sortable by area or by date

- Displays occasion tag and review snippet

## 3.6 /delete — Delete an Entry

**Description**

Removes an item from the wishlist immediately. Soft-delete preferred to preserve visited history integrity.

**Acceptance Criteria**

- Confirmation prompt before deletion

- Visited log entries are preserved even if wishlist entry is deleted

## 3.7 /ask — AI-Powered Smart Recommendations (Core Feature)

**Overview**

This is eatwatah's most important and differentiating feature. /ask is not a wrapper around a generic AI chat — it is a context-rich recommendation engine that combines the user's personal taste profile, their full visit history, their wishlist, and live external F&B data to surface genuinely useful, personalised suggestions.

The goal is for every /ask response to feel like it came from a friend who knows exactly what you like, what you've already tried, and what's worth checking out right now.

**What Makes It Smart**

- It knows your history: the AI has full access to every place you've logged, your ratings, your review sentiments, and how often you visit certain cuisines or areas

- It learns your taste profile: over time it infers preferences — e.g. you tend to rate Japanese spots highly, you prefer casual over fine dining, you gravitate toward the East side

- It goes beyond your wishlist: unlike a simple filter on your saved list, the AI can suggest places you've never heard of by querying Google Places, drawing from curated F&B data, or using web search to find trending spots

- It understands natural language context: queries can include mood, occasion, group size, budget, location, and dietary needs

**Example Queries**

- "We're heading to Bugis — where should we eat?"

- "Something new we haven't tried, under \$20 per pax"

- "Good place for a birthday dinner, a bit atas but not too formal"

- "Chill cafe to work from this Saturday, somewhere in the West"

- "What's a spot similar to the Japanese place I loved last month?"

- "We want supper, what's open near Tanjong Pagar now?"

**Recommendation Engine Logic**

**Layer 1 — Personal Context (from database)**

- Retrieve user's top-rated cuisines, areas, price tiers, and occasions

- Identify patterns in review sentiment (e.g. frequently mentions "cosy", "good vibes", "portions big")

- Pull wishlist items that match the query context as priority candidates

- Flag places visited by one group member but not others ("you've been, but they haven't")

**Layer 2 — External Discovery (beyond the wishlist)**

- Query Google Places API with enriched parameters (location, type, price level, open now)

- Cross-reference with user's taste profile to rank and filter results

- Optionally: use web search to surface trending or recently reviewed spots on platforms like HungryGoWhere, Burpple, or TimeOut Singapore

- Clearly label suggestions as "from your wishlist", "you might like", or "trending nearby" so users always understand the source. Sponsored label reserved for Horizon 2

**Layer 3 — AI Reasoning & Response**

- The AI synthesises Layers 1 and 2 into a ranked shortlist of 3–5 suggestions

- Each suggestion includes: name, address, why it was recommended (personalised reasoning), price range, and a Google Maps link

- The AI explains the recommendation in natural language — not just a list

- Inline buttons let users add a suggestion directly to wishlist, or ask for more options

**Taste Profile (auto-built from usage)**

| **Signal**              | **How it's used**                                            |
|-------------------------|--------------------------------------------------------------|
| Cuisine ratings         | Weight recommendations toward cuisines you rate 4–5★         |
| Visit frequency by area | Suggest spots in areas you frequent                          |
| Review keywords         | Extract vibe preferences (cosy, loud, aesthetic, value)      |
| Occasion tags           | Distinguish casual vs. special occasion preferences          |
| Price of past visits    | Infer budget comfort zone                                    |
| Recency                 | Avoid recently visited; weight wishlist items added long ago |

**Acceptance Criteria**

- AI always uses personal history as context — never gives a generic "top 10 restaurants in Singapore" response

- Recommendations include at least one option from outside the wishlist in every response

- Each suggestion includes a clear, personalised reason why it was recommended

- Response time under 8 seconds (async loading message shown if needed)

- Gracefully handles edge cases: new users with no history, no matching results, ambiguous queries

- Inline action buttons on each result: Add to Wishlist / Already Been / Tell Me More

# 4. Data Model

The schema is designed to support both solo (DM) and group chat contexts natively. Every record is tagged with both a user_id (who did it) and a chat_id (which context it happened in), allowing one user to maintain a personal list and contribute to multiple group lists simultaneously.

## 4.1 Context Detection Logic

Telegram provides a chat_id with every message. If chat_id equals the user's telegram_id, the interaction is a private DM (solo context). If they differ, it is a group chat. This is detected automatically — no user action required.

| **Scenario**         | **chat_id**          | **Behaviour**               |
|----------------------|----------------------|-----------------------------|
| User DMs the bot     | = user's telegram_id | Personal wishlist & history |
| User in Group A      | = Group A's chat_id  | Group A shared wishlist     |
| Same user in Group B | = Group B's chat_id  | Separate Group B wishlist   |

## 4.2 Users Table

| **Field**    | **Type** | **Description**                                            |
|--------------|----------|------------------------------------------------------------|
| id           | INT      | Auto-increment primary key                                 |
| telegram_id  | STRING   | Telegram user ID — unique identifier                       |
| display_name | STRING   | Telegram display name at time of registration              |
| joined_at    | DATETIME | First /start timestamp                                     |
| is_deleted   | BOOL     | Soft delete flag — set when user requests account deletion |

## 4.3 Chats Table

Tracks every context (DM or group) the bot is active in. One user can belong to many chats; one chat can have many users.

| **Field**  | **Type** | **Description**                           |
|------------|----------|-------------------------------------------|
| id         | INT      | Auto-increment primary key                |
| chat_id    | STRING   | Telegram chat ID — unique per DM or group |
| chat_type  | ENUM     | "private" \| "group" \| "supergroup"      |
| chat_name  | STRING   | Group name (null for private DMs)         |
| created_at | DATETIME | When bot was first added to this chat     |

## 4.4 Wishlist Entries Table

Each row is a unique (place, chat) pair. The same Google Place can exist in multiple chats independently.

| **Field**       | **Type** | **Description**                                   |
|-----------------|----------|---------------------------------------------------|
| id              | INT      | Auto-increment primary key                        |
| chat_id         | STRING   | FK to Chats — which context this entry belongs to |
| google_place_id | STRING   | Unique Google Place ID                            |
| name            | STRING   | Place name                                        |
| address         | STRING   | Full address                                      |
| area            | STRING   | Region/district (e.g. Bugis, Orchard)             |
| lat / lng       | FLOAT    | Coordinates from Google Places                    |
| added_by        | STRING   | FK to Users — telegram_id of who added it         |
| status          | ENUM     | "wishlist" \| "visited" \| "deleted"              |
| any_branch      | BOOL     | True if not locked to a specific branch           |
| notes           | TEXT     | Optional free-text notes or TikTok link           |
| date_added      | DATETIME | Auto-set on creation                              |

## 4.5 Visits Table

Each row is one user's review of one visit. Multiple users can log separate reviews for the same group outing.

| **Field**       | **Type** | **Description**                                           |
|-----------------|----------|-----------------------------------------------------------|
| id              | INT      | Auto-increment primary key                                |
| chat_id         | STRING   | FK to Chats — context where visit was logged              |
| google_place_id | STRING   | FK to Wishlist Entries (or standalone if not on wishlist) |
| logged_by       | STRING   | FK to Users — telegram_id of reviewer                     |
| rating          | INT      | 1–5 stars, per user per visit                             |
| review          | TEXT     | Free-text review                                          |
| occasion        | STRING   | Casual / Special / Work / Spontaneous                     |
| photos          | ARRAY    | Telegram file_id references                               |
| visited_at      | DATETIME | Auto-set on creation                                      |

## 4.6 Sponsored Restaurants Table

Separate from the organic user-generated data. Used for Horizon 2 monetisation. Never mixed into the core wishlist or visit history.

| **Field**        | **Type** | **Description**                                         |
|------------------|----------|---------------------------------------------------------|
| id               | INT      | Auto-increment primary key                              |
| google_place_id  | STRING   | Links to real Google Place for accurate info            |
| name             | STRING   | Restaurant name                                         |
| cuisine_tags     | ARRAY    | Used for taste-matching before surfacing as sponsored   |
| area             | STRING   | Location for proximity filtering                        |
| deal_description | TEXT     | Optional exclusive discount or offer for eatwatah users |
| active_from      | DATE     | Campaign start date                                     |
| active_until     | DATE     | Campaign end date                                       |
| is_active        | BOOL     | Whether this listing is currently surfaced              |

# 5. Technical Architecture

## 5.1 Stack

| **Layer**            | **Technology**                                                      |
|----------------------|---------------------------------------------------------------------|
| Bot Framework        | python-telegram-bot or Grammy (Node.js) (python is preferred)       |
| Backend              | Python (FastAPI) or Node.js                                         |
| Database             | PostgreSQL via Railway (managed, persistent SQL database)           |
| Places API           | Google Places API                                                   |
| AI / Recommendations | OPEN AI API — primary reasoning and recommendation layer |
| Hosting              | Railway (same platform as DB, simplifies infra)                     |
| Photo Storage        | Telegram server storage or Railway-linked S3-compatible bucket      |

## 5.2 Database — Railway PostgreSQL

Railway's managed PostgreSQL service is the recommended database. It provides a persistent, production-grade SQL database with zero infrastructure overhead. The connection string is provided as an environment variable and works natively with popular ORMs like Prisma, SQLAlchemy, and Drizzle.

- Provisioned directly from the Railway dashboard alongside the bot service

- Automatic backups and connection pooling included

- Scales easily if the user base grows beyond a private tool

- Environment variable: DATABASE_URL injected automatically into the Railway service

## 5.3 Key Technical Considerations

- Duplicate detection: Match by Google Place ID, not place name string

- Spelling tolerance: Google Places API handles fuzzy matching natively

- Multi-user ratings: Each (place_id, visited_by, visit_date) is a unique record

- Place updates: Periodically re-fetch from Google Places to keep hours/info fresh

- Photo handling: Store Telegram file_id references; retrieve via Telegram API

- Stateful conversations: Use conversation handlers for multi-step flows (/visit, /add)

- AI context window: Pass user taste profile + recent history as system context on every /ask call

# 6. Bot Commands Summary

| **Command**      | **Action**               | **Notes**                                         |
|------------------|--------------------------|---------------------------------------------------|
| /start           | Welcome & stats overview | Shows wishlist + visited counts                   |
| /add \<place\>   | Add to wishlist          | Google Places search, confirm match               |
| /viewwishlist    | Browse wishlist          | Grouped by city \> region, newest first           |
| /visit \<place\> | Log a completed visit    | Rating, review, occasion, photos                  |
| /viewvisited     | Browse visited log       | With ratings and review snippets                  |
| /delete          | Remove wishlist entry    | Soft delete, preserves visit history              |
| /ask \<query\>   | AI smart recommendations | Personalised, context-aware, goes beyond wishlist |

# 7. Privacy & Data

## 7.1 Data Ownership

As the platform operator, you own the infrastructure and the aggregated dataset. However, users retain rights over their own personal data — the reviews, ratings, and activity they contribute. These are not in conflict: aggregated and anonymised data (e.g. "users who like Japanese food tend to rate X highly") can be used freely for AI training and analytics. Individual user records cannot be sold or shared without consent.

Singapore's Personal Data Protection Act (PDPA) applies since the product targets Singapore users. Key obligations for v1:

- Inform users what data is collected and why (via a plain-language Privacy Policy)

- Allow users to request deletion of their personal data

- Do not share individual-level data with third parties, including restaurant advertisers

- Sponsored listings use aggregated taste signals for matching — never individual user profiles

## 7.2 User Data Deletion

A /deleteaccount command must be implemented before public launch. When triggered:

- User's display name and telegram_id are anonymised in the Users table (is_deleted set to true)

- Their wishlist entries and visit logs are soft-deleted and excluded from all future AI context

- Photos they uploaded are removed from storage

- Group contributions are retained in anonymised form so group lists are not broken

## 7.3 What eatwatah Does Not Do

- Never sells individual user data to restaurants or any third party

- Never uses private reviews or ratings in public-facing features without consent

- Sponsored restaurant matching uses cuisine/area signals only — not personal identifiers

# 8. Edge Cases & Logic Rules

- Duplicate entries: Blocked by Google Place ID match; bot informs user

- Spelling errors: Google Places handles normalisation; offer top 3 options

- Any branch option: Store without specific branch; match by chain name

- Multiple visits to same place: Each visit is a new record, separate from wishlist entry

- Independent ratings: Each user rates separately; display both or average depending on context

- Place info changes: Scheduled re-sync with Google Places API for name/hours changes

- Photo support: Store Telegram file_id; retrieve on demand

- Empty state: Graceful empty-state messages for all list commands

- /ask with no history: New users receive popular curated Singapore F&B suggestions with a prompt to start logging visits for personalised results

# 9. Error States

eatwatah's error philosophy is simple: never go silent, never fake it, always tell the user what happened in plain language. A bot that handles failure gracefully feels polished and trustworthy; one that goes quiet or crashes feels broken.

## 9.1 User Input Errors

Triggered when a user sends an unrecognised message or an incomplete command (e.g. /add with no place name).

- Bot responds in a friendly, non-judgmental tone — never just silence or a raw error

- Gently corrects with a concrete example: "Eh, try sending it like this: /add Hai Di Lao Orchard 😄"

- If the user sends a completely unrecognised free-text message with no command, bot shows a short command menu with inline buttons so they can get back on track

## 9.2 Google Places API Errors

| **Scenario**          | **Bot Response**                                                                                                                                                                                         |
|-----------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Zero results returned | "Hmm, couldn't find that one leh. Try rephrasing — e.g. add the area after the name. If it's still not showing up, you can add it manually instead 👇" (manual entry fallback offered via inline button) |
| API timeout or down   | "Shiok spots are loading a bit slow right now — our map search is having a moment. Try again in a bit? 🙏"                                                                                               |

## 9.3 AI API Errors (/ask)

| **Scenario**           | **Bot Response**                                                                                                                               |
|------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| Response taking long   | Bot immediately sends "Hmm let me think... 🤔" as a holding message, then delivers the result when ready                                       |
| Timeout (\>10 seconds) | "Eh, taking too long lah. Try asking again in a moment? 😅"                                                                                    |
| AI API fully down      | "My brain is taking a break right now 🤯 Can't give recs at the moment — but you can browse your wishlist with /viewwishlist while I recover!" |

## 9.4 Database Errors

| **Scenario**        | **Bot Response**                                                                                                             |
|---------------------|------------------------------------------------------------------------------------------------------------------------------|
| DB read/write fails | "Something went wrong on our end — not your fault! Give it a moment and try again 🙏"                                        |
| DB fully down       | Same message as above — no retries on the user-facing side, but error is logged server-side for the developer to investigate |

## 9.5 General Error Principles

- Never expose raw technical errors, stack traces, or API error codes to users

- Always maintain the bot's casual, friendly tone even in failure messages

- All errors are logged server-side with timestamp, user_id, chat_id, and error type for debugging

- Critical failures (DB down, AI down) should trigger a developer alert (e.g. via email or a separate monitoring Telegram bot)

# 10. Future Direction

eatwatah is built as a personal group tool first. But the architecture — a growing database of personal taste profiles, visit histories, and F&B preference signals — has clear commercial potential at scale. The three horizons below document the long-term vision without constraining v1 decisions.

## Horizon 1 — Personal Group Tool (Now)

Nail the core experience for small groups of friends and couples. The goal is a product that genuinely replaces the "eh where to eat" group chat spiral and makes people want to log every meal. Trust, delight, and real daily utility come first.

## Horizon 2 — Restaurant Partnerships & Monetisation

As eatwatah grows its user base, restaurants gain a new incentive: appearing in front of users who are already in decision mode and actively looking for somewhere to eat. Unlike passive advertising, eatwatah recommendations happen at exactly the right moment.

**Sponsored Listings Model**

- Restaurants pay to be included in a separate Sponsored table in the database

- Sponsored spots are only surfaced if they genuinely match the user's taste profile — irrelevant ads are never shown

- All sponsored results are clearly labelled "Sponsored" to protect user trust

- Restaurants can attach exclusive discounts or deals for eatwatah users, turning ads into a value-add rather than an interruption

- A /deals command surfaces active promotions from partner restaurants near the user

**Why This Works**

The trust model is the product's moat. Users trust eatwatah's recommendations precisely because they feel personal. Sponsored content only holds value for restaurants if that trust is maintained — creating a natural alignment between user experience and advertiser quality. Taste-matching as a filter for ad eligibility is the mechanism that keeps this honest.

## Horizon 3 — B2B / SaaS

Platforms like Burpple, Oddle, and food delivery apps have large user bases and rich F&B data, but lack a personalisation layer that learns individual and group taste over time. eatwatah's recommendation engine — trained on personal visit histories, ratings, and review sentiment — is a natural fit as a licensed feature for these platforms.

- License the taste-profile and recommendation engine as an embeddable API

- Incentivise partner platform users to leave more reviews by surfacing better recs the more they log

- Hawker associations, food festivals, or tourism boards could use the same engine to personalise itineraries

This horizon is aspirational for a solo builder at v1 stage. The architectural decision that matters now is ensuring the data model and AI layer are cleanly separated from the Telegram-specific bot logic, so the engine can eventually be extracted and licensed independently.

# 11. Phase 2 — External Signal Pipeline

To be built after v1 is live and stable. This is a separate background service — a standalone repo that runs independently of the Telegram bot and feeds an enriched F&B signals database that the /ask recommendation layer queries. It does not change how the bot works; it makes the AI layer smarter.

Direct scraping of platforms like Burpple or Oddle is prohibited under their Terms of Service and potentially actionable under Singapore's Computer Misuse Act. The pipeline below is built entirely on legal public data sources via official APIs.

## 11.1 Data Sources & What They Contribute

| **Source**        | **Access Method**                                   | **Signal Contributed**                                                                                                                                                     |
|-------------------|-----------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Google Places API | Already in stack                                    | Ratings, price level, opening hours, popularity by time of day, user review snippets. Factual backbone — answers 'is this place good and open now'                         |
| Reddit Singapore  | Official Reddit API (PRAW) — free, no scraping      | Authentic unfiltered local sentiment from r/singapore and r/askSingapore. Years of 'where to eat' threads with real replies. Answers 'what do Singaporeans actually think' |
| TikTok            | TikTok Research API — official, free for developers | Trending discovery layer. A place blowing up on SG food TikTok this week is a signal Google Maps doesn't have yet. Answers 'what's hot right now'                          |
| Instagram         | Meta Graph API — official, requires app review      | Vibe and aesthetic signals from \#sgfood \#sgcafe public posts. Useful for queries like 'somewhere aesthetic for a birthday'. Answers 'what does this place feel like'     |

## 11.2 Pipeline Architecture

The pipeline runs as a separate scheduled service on Railway alongside the bot. It follows a simple three-stage flow:

| **Stage**   | **Description**                                                                                                                                                                                   |
|-------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1\. Crawl   | Each source runs on its own schedule — Reddit daily, Google Places weekly, TikTok and Instagram 3x per week. Raw data is stored in a staging table                                                |
| 2\. Process | Claude API processes raw text into structured signals: sentiment score (-1 to +1), vibe tags (cosy, loud, value, aesthetic, etc.), trending score, mention frequency by recency                   |
| 3\. Enrich  | Processed signals are written to an F&B Signals table keyed by google_place_id — the same identifier used throughout eatwatah's core schema. The /ask layer queries this table as Layer 2 context |

## 11.3 Additional Database Tables (Phase 2)

**F&B Signals Table**

| **Field**       | **Type** | **Description**                                 |
|-----------------|----------|-------------------------------------------------|
| google_place_id | STRING   | FK — links to core schema                       |
| source          | ENUM     | "google" \| "reddit" \| "tiktok" \| "instagram" |
| sentiment_score | FLOAT    | -1.0 (negative) to +1.0 (positive)              |
| vibe_tags       | ARRAY    | e.g. \["cosy", "value for money", "aesthetic"\] |
| trending_score  | FLOAT    | Weighted by recency and mention volume          |
| mention_count   | INT      | Total mentions in source within crawl window    |
| last_crawled    | DATETIME | Timestamp of most recent data pull              |
| raw_sample      | TEXT     | Representative quote or snippet for AI context  |

## 11.4 How It Makes /ask Smarter

With the pipeline live, the /ask Layer 2 changes from a simple Google Places query to a multi-signal lookup. For any candidate place, the AI now has:

- Google Places: factual quality signal — overall rating, price, hours

- Reddit: authentic local opinion — what real Singaporeans say unprompted

- TikTok: recency and trending signal — is this place having a moment right now

- Instagram: vibe match — does it fit the aesthetic or occasion the user is asking for

A query like "somewhere new and trending for a birthday dinner, not too formal" can now be answered with genuine external intelligence — not just what's in the user's wishlist or what Google Maps ranks highest.

## 11.5 Key Architectural Decision for V1

The single most important thing to protect this future is already specced: keep the AI recommendation engine fully decoupled from the Telegram bot logic. The /ask handler should call a recommendation service that accepts inputs and returns results — so in Phase 2, plugging in the external signal pipeline is a matter of enriching those inputs, not rewriting the bot. Build v1 with this separation in mind and Phase 2 becomes an extension, not a rebuild.

*eatwatah PRD v1.0*