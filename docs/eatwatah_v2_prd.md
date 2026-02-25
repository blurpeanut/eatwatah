**eatwatah**

**Product Requirements Document --- v2.0**

Updated February 2026 --- eatwatah.com

  ----------------- ----------------- ----------------- -----------------
  **Status**        **Date**          **Platform**      **Domain**

  Draft             February 2026     Telegram Bot +    eatwatah.com
                                      WebApp            
  ----------------- ----------------- ----------------- -----------------

**1. What v2 Is About**

v1 shipped. People are using it. v2 focuses on two concrete problems:
making /viewwishlist navigable as the list grows, and giving users proper
account controls.

Two problems to solve:

-   **/viewwishlist navigation --- The list gets long fast. Users need a
    better way to explore and find places. Fix: WebApp with map +
    search.**

-   **/viewwishlist area grouping --- Some restaurants fall into Others
    when they belong to a named area. Fix: lat/lng reverse geocode to
    URA planning areas.**

**/ask AI quality upgrades are deferred to v3. See Section 4.**

**2. Branding & Domain**

-   Domain: eatwatah.com purchased February 2026 (Namecheap, auto-renew
    on)

-   Logomark: Bold rounded E in chilli red (#B82C1C) on white --- used
    as Telegram DP

-   Full logo: SG girl illustration + speech bubble saying eatwatah
    (website + marketing)

-   Landing page: simple one-pager with bot link and waitlist --- P2,
    ship after core product

**2.1 /start Welcome Message**

The first message a new user sees when they open the bot. Shown once
only --- never again after /start is tapped. Warm, funny, self-aware. No
hard sell.

Final approved copy:

> 👋 Hey!! I'm eatwatah 🍜
>
> Somewhere on your phone is a graveyard of restaurants you saved and
> fully meant to visit. Still there, still waiting, no judgment 😄
>
> Save places, tell me what you've tried, and ask me whenever
> "eatwatah??" stumps the group chat. I'll look at what you enjoy,
> what's buzzing in SG right now, and that place you bookmarked and
> completely forgot about.
>
> I'll always do my best to find you something you'll genuinely love 🙂
>
> **Your next great meal is already waiting. Let's find it. 🍜**
>
> /start --- let's get you somewhere good!

Implementation notes:

-   Triggered automatically when user opens the bot for the first time

-   Check DB for existing user record --- if none exists, show this
    message before any other response

-   After the welcome message, continue with the V1 onboarding flow:
    surface 3--5 curated starter suggestions ("Places other Singaporeans
    are saving right now") with inline buttons to add any directly to
    their wishlist. Prompt: "Or just tell me a place you've been meaning
    to try --- I'll find it for you 👀"

-   When the user adds their first wishlist item, trigger the
    celebratory confirmation message and explain that the more they log,
    the smarter /ask gets

-   After /start is tapped and user record exists, never show the
    welcome message again

-   If user somehow sends /start again later, respond with a short
    friendly message: "Hey, you're already all set! Try /help to see
    what I can do 😊"

**3. /viewwishlist --- WebApp Redesign**

**3.1 The Problem**

Current /viewwishlist returns a grouped text list in Telegram. This
breaks down as the wishlist grows:

-   50+ places becomes unscrollable

-   No way to search or filter

-   No spatial sense of where places are

-   Area grouping has gaps --- places fall into Others

**3.2 The Fix: Telegram WebApp with Map + Search**

Build a Telegram WebApp --- a mini web page launched from a button in
the /viewwishlist message. Full UI surface without leaving Telegram.
WebApp fetches user wishlist from the Railway backend via REST API and
renders it.

**3.3 WebApp Spec**

**Default view: Map**

-   Full-screen Google Maps JS with pins for all wishlist entries

-   Unvisited (wishlist) pins: orange

-   Visited pins: green

-   Both visible simultaneously, distinct colours at a glance

**Search & filter bar (persistent top)**

-   Free text --- searches restaurant name in real time

-   Cuisine filter --- pill chips: All / Japanese / Chinese / Western /
    Café / etc.

-   Area filter --- dropdown of URA planning areas present in the
    wishlist

-   Filters apply to both map pins and list view simultaneously

**Schema change required for cuisine filter**

V1's WishlistEntries table has no cuisine field. Add one:

  ------------------- ------- -------------------------------------------------
  **Field**           **Type** **Description**

  cuisine_type        STRING  Normalised cuisine label derived from Google
                              Places `types` at /add time. e.g. "Japanese",
                              "Chinese", "Western", "Café", "Hawker", "Other".
                              Nullable --- fallback to "Other" if no
                              cuisine-relevant type is returned.
  ------------------- ------- -------------------------------------------------

Mapping logic at /add time: Google Places returns a `types` array (e.g.
`["japanese_restaurant", "restaurant", "food", ...]`). Iterate the
`CUISINE_MAP` below in order --- first match wins. If no type matches,
store "Other". Implement as a `classify_cuisine(types: list[str]) -> str`
helper in `services/places_service.py`.

  ----------------------------------------- -----------
  **Google Places type (check in order)**   **Label**

  japanese_restaurant                       Japanese

  chinese_restaurant                        Chinese

  korean_restaurant                         Korean

  thai_restaurant, vietnamese_restaurant,   Southeast
  indonesian_restaurant                     Asian

  indian_restaurant                         Indian

  american_restaurant, western_restaurant,  Western
  steak_house, pizza_restaurant,
  italian_restaurant, french_restaurant,
  mediterranean_restaurant

  seafood_restaurant                        Seafood

  cafe, coffee_shop, bakery,                Café
  breakfast_restaurant

  bar, night_club                           Bar

  (none of the above match)                 Other
  ----------------------------------------- -----------

Add via Alembic migration alongside the area grouping fix (build order
step 2).

**Slide-up card on tap**

-   Restaurant name, area tag, cuisine tag

-   Notes saved at /add time

-   If visited: star rating + review text

-   Open in Google Maps button --- deep links to navigation

-   Dismiss: swipe down or tap outside

**List view toggle**

-   Toggle (top right) switches between Map and List

-   List groups by area, same data, no extra fetch

-   Tapping a list item opens slide-up card and flies to pin on map

**Technical notes**

-   Frontend: single-file HTML/CSS/JS + Telegram WebApp SDK

-   Maps: Google Maps JavaScript API (free tier: \~28,500 loads/month)

-   Auth: Telegram WebApp initData for user verification

-   Monitor: log Maps API usage weekly, billing alert at \$10/month

-   Future: same codebase becomes eatwatah.com web product foundation

**3.4 Area Grouping Fix**

**Root cause**

-   Area field inferred from raw address strings at /add time

-   Grouping does naive string match against short hardcoded list

-   Anything not matched falls to Others

**Fix**

-   At /add time: reverse geocode lat/lng → URA planning area (55
    zones). Store normalised tag, not raw address.

-   **Geocoding method:** call the Google Maps Geocoding API
    (`maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}`)
    using the existing `GOOGLE_PLACES_API_KEY`. Enable the Geocoding
    API in the same Google Cloud Console project (it is separate from
    the Places API). Extract the `sublocality_level_1` or
    `neighborhood` component from the response and normalise to the
    closest URA planning area name using a static lookup dict in
    `services/places_service.py`. Add a helper
    `async def reverse_geocode_area(lat, lng) -> str` alongside
    the existing `search_places` function.

-   At display time: expand area list to all 55 URA planning areas

-   Backfill: one-time migration on all existing entries using stored
    lat/lng

-   Fallback: if the Geocoding API returns no usable component, fall
    back to a postal district → neighbourhood lookup table (\~30
    mappings) keyed on the first two digits of the postal code in the
    stored address string

-   Target: Others bucket \< 5% of entries after migration

**4. /ask --- AI Quality Upgrade (DEFERRED TO V3)**

> ⚠️ This entire section is deferred to v3. v2 focuses on
> /viewwishlist, area grouping, /deactivate, and account middleware.
> Revisit when user base and data volume justify the additional
> complexity and cost.
>
> **Exceptions in v2 scope:**
> - Section 4.3.2 (Remove Follow-up Prompt) --- 3-line code change,
>   ships in v2 regardless of the wider /ask deferral.
> - Section 4.5 (REST API / FastAPI) --- required for the WebApp.

**4.1 What's Limiting /ask Today**

-   The AI's training data has a cutoff --- new openings and closures
    invisible

-   No real-time signal about what's trending or recently reviewed

-   Result: can personalise (what the user likes) but not discover
    (what's good right now)

**4.2 Data Strategy --- Why We're Not Scraping**

*Note: V1 PRD Section 11 planned a Phase 2 background pipeline using
Reddit (PRAW), TikTok Research API, and Instagram Meta Graph API. That
plan is retired. The legal review below explains why. Google Places
signals replace the entire Phase 2 external data strategy.*

Original plan was to crawl Burpple, Reddit, and HungryGoWhere. Ruled out
after legal review:

-   Burpple and HungryGoWhere ToS prohibit automated extraction

-   Reddit API ToS explicitly prohibits AI/ML use without written
    approval

-   Instagram and TikTok --- no official public API, scrapers break
    frequently, IP ban risk on Railway. Deferred to v3.

Revised approach --- three data sources, all legal and buildable now:

-   **Source 1: Google Places review velocity + sentiment analysis**

-   **Source 2: Google Places Popular Times data**

-   **Source 3: User-generated signals (/visit reviews + ratings) ---
    data only eatwatah has, moat grows with user base**

**4.2.1 Source 1 --- Google Places Review Velocity + Sentiment**

Pull the 5 most recent reviews for each saved place nightly via Google
Places API. Derive two signals:

**Review velocity score**

-   Count new reviews this week vs the place's monthly average

-   Velocity score = (reviews this week) / (avg weekly reviews over last
    3 months)

-   Score \> 3x = trending. Score \> 6x = significantly trending. Score
    \< 0.5x = going quiet.

-   Spike in reviews is a stronger trending signal than raw review count
    alone

**Sentiment analysis**

-   Run each new review through OpenAI nightly --- cheap batch
    job, not per /ask call

-   Extract: overall sentiment (positive / negative / mixed)

-   Extract: key descriptors --- e.g. 'worth the queue', 'good for
    dates', 'hidden gem', 'overpriced'

-   Extract: red flags --- e.g. 'closed', 'new management', 'gone
    downhill'

-   Store derived signals only --- not raw review text (keeps DB lean,
    avoids copyright issues)

**Schema: place_signals table**

  ------------------ ------------ ----------------------------------------
  **Field**          **Type**     **Description**

  google_place_id    string       Primary key, links to wishlist entries

  velocity_score     float        Review rate this week vs 3-month
                                  baseline

  velocity_label     string       trending / steady / quiet

  sentiment          string       positive / negative / mixed

  descriptors        string\[\]   e.g. \[worth the queue, good for dates\]

  red_flags          string\[\]   e.g. \[gone downhill\] --- empty array
                                  if none

  review_count_30d   int          New reviews in last 30 days

  last_updated       timestamp    When this row was last refreshed
  ------------------ ------------ ----------------------------------------

**How it enriches /ask**

Injected as natural language per relevant place:

> *"Burnt Ends is trending right now --- 8x its usual review rate this
> month. Recent reviewers call it worth the queue and great for a
> special occasion. No red flags."*

This is what makes /ask feel like a friend who's been paying attention
--- not just what you like, but what's happening right now.

**4.2.2 Source 2 --- Google Places Popular Times**

The Places API returns Popular Times data --- how busy a place typically
is by day and hour. Unlocks time-aware recommendations.

**What it enables**

-   If user asks at 7pm Friday, /ask knows which wishlist places are
    currently packed vs manageable

-   Filter out slammed places unless user explicitly wants a buzzy
    atmosphere

-   Surface undervisited time slots --- 'this place is popular evenings
    but quiet for Saturday lunch'

**Schema addition to place_signals**

-   peak_days: string\[\] --- e.g. \[Friday, Saturday\]

-   peak_hours: string --- e.g. 12pm-2pm, 7pm-9pm

-   currently_busy: bool --- derived at /ask call time from Popular
    Times + current timestamp

**How it enriches /ask**

Injected as a time-aware note when relevant:

> *"Note: it's Friday 7pm --- Sinpopo Brand is likely busy right now.
> Weekend lunch is usually much calmer if you prefer a quieter
> experience."*

**4.3 Improved /ask Prompt**

Context injected per call:

-   User wishlist (v1) + visit history with ratings (v1) + group context
    (v1)

-   Velocity + sentiment summary per relevant place (NEW --- Source 1)

-   Time-aware busyness signal (NEW --- Source 2)

-   Recency instruction --- 'Prioritise trending places. Flag if a place
    has red flag signals.'

Prompt rules:

-   Exactly 3 recommendations, one sentence each explaining the fit

-   Recommend freely from both visited and unvisited places --- no
    distinction. Visited places are just as valid, user may want to
    return.

-   Every response must include at least one option from outside the
    wishlist --- surface trending or relevant places via Google Places
    even if not saved by the user. Label these clearly as "you might
    like" or "trending nearby".

**How to get the external result (Layer 2)**

At /ask call time, after extracting area and occasion intent from the
query:

1.  Call Google Places Text Search or Nearby Search with the extracted
    area + cuisine/occasion signals as query parameters (e.g.
    "Japanese restaurant Bugis Singapore")

2.  Filter out any results whose google_place_id already exists in the
    user's wishlist for this chat --- those are Layer 1 candidates, not
    external discoveries

3.  Take the top 1--2 remaining results by Google rating. Inject them
    into the prompt alongside the wishlist context, labelled as external
    suggestions.

4.  The AI picks the best one as the "you might like" recommendation in
    the final response.

Degrade gracefully: if the Google Places call fails or returns no
usable results, return 3 wishlist-only recommendations and do not
surface an error to the user.

-   Signal confidence --- say so if data is thin on a place

-   Area-aware --- extract area intent from query, filter before
    injection

-   Occasion-aware --- extract occasion signals (date night, supper,
    solo, group) and weight descriptors accordingly

**4.3.1 Wishlist Data Model Clarification**

Places never leave the wishlist. Visited just adds more information ---
it does not remove or archive the entry.

-   Unvisited --- saved, haven't been yet

-   Visited --- been before, have a review and rating, may absolutely
    return

-   Deleted --- only way a place leaves the list. Explicit user action
    only.

This means /ask treats the full wishlist as a living food journal, not a
checklist. Visited places carry taste signal (rating, review) and are
fair game for future recommendations.

**4.3.2 /ask UX --- Remove Follow-up Prompt**

Current behaviour: after every /ask response, the bot appends a
follow-up message prompting the user with examples like 'ask me anything
--- near Orchard, good for dates etc'.

Decision: remove this entirely. /ask just responds and stops. No
follow-up message.

-   The prompt is unnecessary friction --- users already know how to ask
    follow-up questions

-   It makes the bot feel scripted and repetitive after the first use

-   Trust the user. If they want more, they'll ask.

**4.3.3 Change 1 --- Cuisine Preference from Ratings**

The most direct taste signal in the DB (which cuisines earn the highest
ratings) is computed in `_build_taste_profile`. A `CUISINE_SIGNALS` dict
in `recommendation_service.py` maps cuisine bucket names to keyword lists
(e.g. `"Japanese": ["japanese", "sushi", "ramen", "yakitori",
"tonkatsu"]`). For each visit, match `place_name` against the lists to
assign a cuisine bucket. Compute average rating per bucket across all
visits for the chat.

Returned as `cuisine_ratings: list[tuple[str, float]]` sorted descending.
Injected into the AI prompt as:

> Taste fingerprint --- cuisines by avg rating:
>   Japanese 4.7★ (8 visits), Western 4.1★ (5 visits), Hawker 3.8★ (6 visits)

Upgrade path: when `cuisine_type` column lands on `WishlistEntry` (from
the area grouping migration, Section 3.3), replace the keyword heuristic
with an exact lookup via `visit.google_place_id → entry.cuisine_type`.
Prompt structure stays identical --- no further changes needed at that
point.

No migration dependency.

**4.3.4 Change 2 --- Overdue Wishlist as Priority Signal**

A place saved 6+ months ago and never visited is the strongest "I keep
meaning to go here" signal in the database. Currently the wishlist is
sorted newest-first and capped at 10, so these forgotten entries never
reach the AI. After fetching the wishlist in `_build_taste_profile`,
filter for `status == "wishlist"` AND `(now - date_added).days > 90`.
Return as `overdue_wishlist: list[dict]` with `name` and `area`.

Injected into the AI prompt as a labelled section:

> Places they've been meaning to try (saved 3+ months ago, never visited):
>   - Nakhon Kitchen (Holland Village) --- saved 9 months ago
>   - Rizu (Tanjong Pagar) --- saved 6 months ago

Prompt instruction: "If any of these match the query context, prioritise
them --- the user has been meaning to go."

No migration dependency. `date_added` and `status` already exist on
`WishlistEntries`.

**4.3.5 Change 3 --- Correct Source Labelling for Candidates**

Visited places are not filtered out of recommendations. Users often want
to return to places they loved --- someone who rates Yakun Woodlands 5★
for breakfast probably wants it recommended again. The real issue is
incorrect labelling: a visited place appearing as "you might like" feels
wrong.

After `_search_candidates` returns, cross-reference candidates against
the profile's `visited_place_ids` and wishlist entry list. Annotate each
candidate:

-   `already_visited: True` + user's rating → label in prompt:
    "You've been here before (rated X★)"

-   `already_on_wishlist: True` (not yet visited) → label:
    "from your wishlist"

-   Neither → label: "you might like" / "trending nearby"

AI prompt instruction: "Only exclude a previously visited place if the
user's query explicitly asks for somewhere new or somewhere they haven't
tried."

No migration dependency.

**4.3.6 Change 3b --- 800m Distance Constraint for Area-Specific Queries**

If someone asks for food near Tanjong Pagar, recommending somewhere in
Bugis (2km away) is unhelpful and breaks trust. Area intent in a query
implies the user is physically near that location or heading there.

When `parsed_query` contains an `area`, the AI prompt must explicitly
instruct: "Only recommend places within 800m of {area} MRT / the named
location. Do not surface places in adjacent areas even if they match
other criteria."

For the Google Places candidate search, when an area is specified,
replace the island-wide `SG_RADIUS_M` (40km) with an 800m radius centred
on the parsed area's coordinates. This requires a lookup table of major
Singapore MRT/area centroids (lat/lng per area name) --- a dict in
`places_service.py` alongside the existing `SINGAPORE_AREAS` list.

No migration dependency.

**4.3.7 Change 4 --- Group Context and Time of Day in the AI Prompt**

The AI currently has no idea if it's talking to a solo user or a group,
and no idea what time it is. Both substantially change what a good
recommendation looks like.

**4a --- Group vs solo context**

`get_recommendations` takes an `is_group: bool` parameter (V2 addition).
In `ask.py`, derive it: `is_group = not is_private_chat(chat_id,
user_id)`. Forward into `_call_ai_reasoning`. One line added to the
prompt:

> Context: Group chat (shared wishlist)   OR   Solo / private DM

**4b --- Time of day**

In `_call_ai_reasoning`, call `datetime.now(timezone.utc)` converted to
SGT (UTC+8). One line added to the prompt:

> Current local time: Friday 10:45pm (Singapore)

Zero additional API cost. Enables the AI to reason about supper queries,
open-now relevance, and appropriate dining contexts for the current time.

No migration dependency.

**4.3.8 Change 5 --- Personalised No-Arg /ask Suggestions**

`/ask` with no arguments currently returns a generic example query. It is
a wasted moment with a user who is ready to be surprised. V2 adds a new
public function: `get_personalised_prompts(chat_id, user_id) ->
list[str]`.

This calls `_build_taste_profile` (DB reads only, no AI call) and
generates 2--3 query suggestions deterministically:

1.  If `overdue_wishlist` non-empty → "something like {name} in {area}
    I've been meaning to try"

2.  If `cuisine_ratings` non-empty + `top_areas` non-empty →
    "good {top_cuisine} near {top_area}"

3.  If `occasions` non-empty → "somewhere good for {top_occasion}"

4.  Fallback (new users with no history) → three generic
    Singapore-appropriate examples

In `ask.py`, the no-arg branch calls `get_personalised_prompts()` instead
of hardcoded example text. Response format:

> What are you in the mood for? 🍜
>
> Based on your history, maybe:
> • /ask good Japanese food near Tanjong Pagar
> • /ask Nakhon Kitchen --- I've been meaning to try this one
> • /ask somewhere cosy for a casual dinner
>
> Or just ask me anything --- near Orchard, open now, birthday dinner,
> whatever!

No AI API call fires on the no-arg path. Fast and free. Gets richer after
the `cuisine_type` migration (Section 3.3) but fully functional now.

No migration dependency.

**4.3.9 Implementation Order for Five Changes**

Implement in this sequence to avoid touching the same functions twice:

1.  Change 3 --- candidate source labelling (pure data plumbing,
    no prompt surgery)

2.  Change 1 --- cuisine rating aggregation (adds `cuisine_ratings`
    to taste profile + prompt section)

3.  Change 2 --- overdue wishlist (adds `overdue_wishlist` to taste
    profile + new prompt section)

4.  Change 4 --- group context + time injection (touches function
    signatures in both `recommendation_service.py` and `ask.py`)

5.  Change 5 --- personalised no-arg (builds on enriched profile
    from steps 1--3)

**4.4 Cost Management**

**Current cost baseline (\< 100 places, \~9 users)**

  --------------------------- ------------------- ---------------------------
  **Cost item**               **Est. monthly**    **Notes**

  Google Places nightly fetch S\$0                100 calls/night =
                                                  3,000/month. Free tier:
                                                  28,500/month

  Popular Times data          S\$0                Bundled in same Place
                                                  Details call as reviews

  OpenAI --- sentiment batch  S\$0.05             \~20 new reviews/night ×
                                                  200 tokens each

  OpenAI --- /ask calls       S\$1.50             \~100 calls/day × S\$0.0005
                                                  per call

  Google Maps JS (WebApp)     S\$0                \~300 loads/month. Free
                                                  tier: 28,500/month

  Railway hosting             S\$7--14            Flat fee, existing cost

  Total                       \~S\$10--15/month   Well within S\$50 budget
  --------------------------- ------------------- ---------------------------

**Cost inflection points to watch**

  ------------------------ ------------------- ---------------------------
  **Trigger**              **Threshold**       **Action**

  Google Places API        \~950 places in DB  Review nightly fetch
  charges                                      frequency, consider
                                               skipping low-activity
                                               places

  OpenAI /ask charges      \~1,000 active      Introduce per-user daily
  spike                    users               soft cap

  Google Maps JS charges   \~950 DAU opening   Set billing alert, consider
                           WebApp              Maps lite fallback
  ------------------------ ------------------- ---------------------------

**Controls implemented in v2**

-   **Cache place_signals block nightly --- every /ask reads from DB,
    never hits Google Places API directly at query time. Single biggest
    cost lever.**

-   **OpenAI for all AI calls by default --- /ask responses and
    sentiment batch.**

-   **Hard cap /ask responses at 500 tokens --- recommendations don't
    need to be essays.**

-   **Pre-filter place_signals to top 10-15 relevant entries per query
    before injection --- don't dump the whole table.**

-   **Deduplication --- same user + similar query within 5 minutes
    returns cached response, no new API call.**

-   **Soft cap on /ask per user per day --- after 10 calls, add a gentle
    note that results may be cached. No hard block.**

-   **Degrade gracefully --- if sentiment batch job fails, /ask falls
    back to velocity score only. Core feature never blocked by
    enrichment failure.**

**Monitoring**

-   Set Google Cloud billing alert at S\$10/month --- do this now before
    you forget

-   Log token usage per /ask call in Railway --- track weekly average

-   Log Google Places API call count daily --- alert if nightly job
    exceeds 500 calls unexpectedly

-   5-minute Monday check: Railway logs, Google Cloud console, token
    averages

Target: \< S\$0.01 per /ask call at current scale. Revisit thresholds
when user base grows beyond 50 active users.

**4.5 New Infrastructure Required in V2**

v1 was a pure Telegram bot with no background jobs and no web server.
v2 adds two meaningful infrastructure pieces:

**Background job scheduler**

Required for the place_signals nightly job (review velocity fetch +
sentiment batch). V1 deferred the monthly recap because it required a
scheduler. That deferral no longer applies --- the scheduler is now
needed for core /ask quality. Implement as a scheduled task in Railway
(cron job or APScheduler within the bot process).

**REST API (FastAPI)**

Required to serve the /viewwishlist WebApp. V1 was bot-only. V2 adds a
lightweight FastAPI service on Railway alongside the bot that exposes:

-   `GET /api/wishlist?chat_id=...` --- returns all active entries for
    the chat. **Must query both `status='wishlist'` AND
    `status='visited'` entries** --- the WebApp shows both as map pins
    (orange = unvisited, green = visited). `status='deleted'` entries
    are excluded. The existing `get_wishlist_entries` helper only
    returns `status='wishlist'`; the endpoint needs a separate query
    or a new helper that fetches both statuses.

**Response schema** (JSON array):

  ---------------- -------- -----------------------------------------------
  **Field**        **Type** **Notes**

  id               int      WishlistEntry primary key

  name             string   Place name

  address          string   Full address

  area             string   URA planning area, or null

  cuisine_type     string   Cuisine label, or null

  lat              float    Latitude, or null

  lng              float    Longitude, or null

  status           string   "wishlist" or "visited"

  notes            string   User notes from /add, or null

  rating           int      Most recent visit rating (1--5), or null

  review           string   Most recent visit review text, or null

  maps_url         string   https://maps.google.com/?place_id={place_id}
  ---------------- -------- -----------------------------------------------

`rating` and `review` are sourced from the most recent Visit row for
this `google_place_id` in this chat. Used by the slide-up card.

**Auth:** Telegram WebApp initData verification on every request. The
WebApp passes initData from the Telegram client; the server validates
the HMAC-SHA256 hash against TELEGRAM_BOT_TOKEN before returning any
data. Return HTTP 403 if validation fails --- the WebApp shows:
"Session expired. Please close and reopen from Telegram."

---

**5. Platform Strategy**

**5.1 Now: Telegram First**

eatwatah is a Telegram bot. The friend group testing it is the best
product validation available. Ship v2 for them before thinking about
growth.

**5.2 Later: Web Companion**

When Telegram outgrows itself, add a web layer via Telegram Login Widget
--- one-tap auth, no new passwords, existing users carry over instantly.

-   Bot: conversational adding and logging

-   Website: rich visual experience (map, full wishlist, shareable
    pages)

-   Shareable URLs: eatwatah.com/u/sarah --- deferred. No data model
    changes needed in v2. Revisit when the web product is prioritised.

**5.3 The WebApp as Bridge**

The /viewwishlist WebApp built in v2 is the first step toward the web
product. Same codebase, same data model. Build it cleanly and it becomes
the public website foundation when the time comes.

**6. Feature Summary**

  ------------------------ -------------- --------------------------
  **Feature**              **Priority**   **Unlocks**

  Area grouping fix +      P0             Clean /viewwishlist data
  backfill migration

  /viewwishlist WebApp     P1             Core navigation upgrade
  (map + search + card)

  /deactivate command      P1             Reversible account pause

  Account reactivation     P1             Seamless return for
  middleware                              inactive users

  Landing page             P2             Domain does something
  (eatwatah.com)                          useful
  ------------------------ -------------- --------------------------

**7. Recommended Build Order**

  -------- ----------------------------------------- ----------------------------
  **\#**   **Task**                                  **Done when...**

  1        Audit Others bucket --- SQL, check         Every entry has a reason
           uncategorised entries and confirm           for its current area
           lat/lng is populated on all rows

  2        Fix /add area inference --- reverse         New adds get correct URA
           geocode lat/lng → URA planning area.        area + cuisine_type
           Alembic migration to add cuisine_type        stored at save time
           to WishlistEntries at the same time.

  3        Backfill migration --- run on all           Others \< 5% of entries;
           existing DB entries (area +                  cuisine_type populated
           cuisine_type)

  4        Build /viewwishlist WebApp --- map +        Opens from Telegram, both
           search + filters + slide-up card.            pin colours show, search
           FastAPI endpoint returns both wishlist        and filters work
           + visited entries.

  5        Remove /ask follow-up prompt ---            No trailing message after
           delete footer message block in               /ask responses
           bot/handlers/ask.py (Section 4.3.2)

  6        Alembic migration --- add                   is_deactivated field
           is_deactivated to Users table                live in DB

  7        /deactivate command --- new command         Users can pause account
           handler, soft-pause flag, confirmation       reversibly
           message with /deleteaccount reminder

  8        Account reactivation middleware ---         Deactivated users return
           check flag at top of every handler,          seamlessly, original
           reactivate silently then continue            command executes

  9        Landing page --- eatwatah.com               Domain live and useful
           one-pager with bot link + waitlist
  -------- ----------------------------------------- ----------------------------

**8. Account Deactivation & Reactivation**

**8.1 Current State**

V1's Users table has a single boolean `is_deleted` used by /deleteaccount
to mark permanent deletion. There is no separate deactivation flag.

V2 adds a new field to the Users table:

  ------------------- ------- -------------------------------------------------
  **Field**           **Type** **Description**

  is_deactivated      BOOL    Default false. Set true by /deactivate. Reset to
                              false by auto-reactivation middleware. Separate
                              from is_deleted, which is only set by
                              /deleteaccount and is never reversed.
  ------------------- ------- -------------------------------------------------

The middleware checks `is_deactivated` only. `is_deleted` remains
exclusively for permanent account deletion. A user cannot be both
is_deleted and is_deactivated --- /deleteaccount takes precedence and
is final.

Add this field via an Alembic migration before implementing /deactivate
or the reactivation middleware.

**8.2 Decision: Auto-reactivate with Message**

If a deactivated user interacts with the bot in any way, auto-reactivate
their account and continue their original action. Do not force them
through a separate /reactivate command.

Welcome back message:

> *👋 Welcome back! Your account has been reactivated and your wishlist
> is still here. Carrying on\...*

The original command then executes immediately after, in the same flow.

**8.3 Implementation**

**Middleware approach**

-   Implement as a standalone `async def reactivate_if_needed(telegram_id,
    chat_id, bot) -> bool` function in `db/helpers.py`. Returns True if
    the user was reactivated (so the handler can send the welcome back
    message before proceeding), False if no action needed.

-   Call it at the top of every command handler, immediately after
    `ensure_user_and_chat` --- the same pattern already used for
    auto-registration (Rule 4). Do **not** use python-telegram-bot's
    TypeHandler-based middleware; the explicit per-handler call is
    simpler and consistent with the existing codebase pattern.

-   If `is_deactivated` is True: set to False, commit, caller sends the
    welcome back message, then continues executing the original command.

-   One function called everywhere --- no duplicated logic across
    commands.

**Edge cases**

-   User deactivates mid-conversation (e.g. partway through /add flow)
    --- on next interaction, reactivate first then restart the command
    cleanly. Do not try to resume broken state.

-   Group chats --- same middleware applies if a deactivated user sends
    a command in a group

-   /deactivate sent by already-deactivated user --- ignore gracefully,
    no error

**8.4 Deactivation vs Deletion --- PDPA Note**

These are two separate commands serving different user needs. Both exist.

-   /deactivate (NEW in v2) --- pauses the account. Data is retained.
    Fully reversible. Use this if you want a break.

-   /deleteaccount (shipped in v1) --- permanent anonymisation of all
    user data. No recovery. Satisfies PDPA right to erasure.

The /deactivate confirmation message should be explicit: "Your account
has been deactivated. Your wishlist is saved and you can return any
time. To permanently delete all your data, use /deleteaccount."

This distinction matters for PDPA compliance --- users have the right to
request erasure of personal data. /deleteaccount is already live from
v1. Do not remove or replace it with /deactivate.

**9. Deferred to v2.1+**

-   /ask AI quality upgrades (all of Section 4 except 4.5) ---
    place_signals table, nightly Google Places job, review velocity
    scoring, sentiment analysis, Popular Times data, and all five engine
    improvements (cuisine taste fingerprint, overdue wishlist signal,
    correct source labelling, 800m area constraint, group/time context
    injection, personalised no-arg /ask). Revisit when user base and
    data volume justify the additional complexity and cost.

-   Background job scheduler --- required for the place_signals nightly
    job. Deferred with it.

-   Instagram data --- ToS risk, inconsistent API. Defer indefinitely.

-   /deleteaccount permanent wipe enhancement --- V1 shipped anonymisation.
    A harder full-erasure pass (photos, logs, orphaned records) should
    be completed before scaling beyond friend group. V1's /deleteaccount
    is sufficient for now.

-   Recommendation explanations --- show why a place was recommended.
    Nice to have.

-   Push notifications --- requires more data volume first.

-   Full eatwatah.com web product --- build after WebApp proven and user
    base grows.

-   Visited/unvisited toggle as primary filter --- useful but map pin
    colours solve this for now.

*This document is the v2 single source of truth. Update it as decisions
change. Last updated February 2026.*