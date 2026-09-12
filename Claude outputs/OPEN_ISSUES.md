# Open issues — the living tracker

This is now the primary tracking document for this project's mega-feature work (frontend
bugs, pipeline quality, player, editor, AI features). `CHECKLIST.md` remains as the
historical record of what happened session-by-session; this file is the current-state
source of truth: every open issue, its status, evidence, and what's next. Update this
file whenever an issue's status changes — don't let it go stale. See `UNDERSTANDING.md`
for the full reasoning behind each item's priority.

Status values: `OPEN` (not started/not fixed) · `IN PROGRESS` · `FIXED — NEEDS
RE-VERIFY` (code changed, not yet confirmed live) · `VERIFIED` (confirmed against the
real local stack, in the user's own browser/screenshot where applicable) · `STATIC
AUDIT FINDING — NOT LIVE-VERIFIED` (a real, specific issue traced in the actual code by
a real review, but not yet reproduced against the running local stack — a genuine lead,
not a confirmed bug, until someone does that) · `WON'T FIX` (with reason).

---

## 1. Review page decision bar has no visible padding

**Status: FIXED — NEEDS RE-VERIFY (from the user's own screen)**

`.decision` now has explicit horizontal padding, a real background/border/radius (a
genuine card, not blending flush into the page), applied via a breakout margin
(`margin: 0 calc(-1 * var(--s-6))`) so it doesn't depend on any ancestor gutter being
visually obvious at a given window width. `.decision-static` (preview modal / story
detail page, where the surrounding container already provides real outer padding) is
explicitly reset to stay flush there — no double-inset. Verified live in the browser at
1440px and 1035px wide (the latter matching the composition of the user's own
screenshot): the warning text, Reject/Approve buttons, and hint text now sit inside a
clearly bordered, padded card. Not marking VERIFIED (only a person, not me, can confirm
their own screen now shows it correctly) — next actual open of the review page by the
user should confirm this.

The user showed this exact bug twice (two different screenshots, same session) — the
"1/3 claims need a source" warning, Reject/Approve buttons, and the shortcuts hint text
all read as flush against the edges of their container, with no breathing room.

Previous investigation (recorded in `CHECKLIST.md`) concluded this was NOT a bug, based
on DOM measurement showing `.decision`'s left/right edges matched its sibling content
(title, narration) within the same column, and reasoning that the *page-level* gutter
(`.shell-main`'s `padding: ... var(--gutter) ...`) provided the real margin. That
measurement was real but insufficient — it didn't reproduce the user's actual window/
viewport, and the user's second screenshot shows the video frame and dossier text
running edge-to-edge in their real browser, which the page-level gutter should prevent
if it were applying. The corrected read: whether or not sibling elements are internally
consistent with each other doesn't matter if the whole column reads as edge-to-edge to
the person looking at it — "matches its siblings" is not the same bar as "has visible
padding around it."

**Fix being applied**: give `.decision` (and by extension `.decision-static`) real,
explicit horizontal padding of its own — not relying on inherited alignment from a
parent gutter that may or may not be visually obvious at the user's actual window size —
so the decision bar unambiguously reads as having breathing room around its content
regardless of viewport width or how a screenshot crops it. Same treatment applied
consistently to the fact-check panel it sits below, since the same "reads edge-to-edge"
complaint plausibly applies there too — re-check both live.

**Next**: apply the CSS fix, rebuild frontend, screenshot the review page at a few
realistic widths (not just one), and only mark VERIFIED once a fresh screenshot clearly
shows padding — don't re-mark this done from reasoning/DOM-measurement alone again.

---

## 2. No explainer motion graphics in generated videos ("animations")

**Status: VERIFIED**

Built `pipeline/motion_graphics.py`: detects a specific year/date mentioned in a beat's
own narration text (`extract_year_label` — handles both era-marked dates like "44 BCE"
and bare 4-digit years like "1872", while not false-positiving on unrelated small
numbers), and for beats where one is found, generates an animated timeline-marker
graphic (a line draws in, a marker lands at its tip, the year fades in, then it
disappears well before the beat's own cut) — built entirely from ffmpeg's own drawbox/
drawtext filters, no new dependency. Wired into `pipeline/render.py`'s per-beat filter
chain (both the original auto-generation path and `render_timeline.py`'s re-render
path now thread the beat's own text through so both get this).

Verified in two stages: first the filter mechanics standalone against a synthetic
ffmpeg clip (frames extracted at 7 timestamps — line correctly grows 0→full over 0.6s,
marker lands at the right moment, year fades in and holds, everything disappears after
the capped show window); then a real end-to-end generation ("the assassination of
Julius Caesar", story `99b758667b79`): beat 0's narration ("In ancient Rome... To stop
Julius Caesar's growing power...") contained "44 BCE"; frames extracted from the actual
rendered/downloaded MinIO video (not the synthetic test) at t=0.1/0.6/0.95/1.8/2.3/3.5s
confirmed the line is mid-growth with no text yet at t=0.1, "44 BCE" is fully drawn in
over real matched Roman-ruins stock footage at t=0.95, and by t=2.3 the overlay has
cleanly disappeared while the normal karaoke captions ("CAESAR'S GROWING") continue
underneath — exactly the intended "brief, purposeful accent" behavior, composited
correctly with the existing Ken Burns/caption/grade pipeline, not fighting it. 10 new
unit tests cover the year-extraction regex and the overlay filter's duration-capping/
label-sanitizing logic.

**Scope note**: this is v1 — one graphic type (a year/timeline marker), triggered by a
simple regex over the beat's own text. Explicitly not yet covered: an animated map for
"place" beats, a sequence/multi-event timeline spanning several beats, or a stat/number
callout — worth adding as v2/v3 following the same pattern once v1 is confirmed working
end-to-end, per the project's own "versioned, not one-shot" precedent for the editor.

**v2 redesign + a real bug, found, root-caused, and fixed (2026-09-12)**: the user
called the original design out directly — "looked really bad, like a basic element from
Filmora" — a fair hit (linear motion, wide flat bar, hard cutoff). Rebuilt as a tight
lower-third (drawtext's own box/boxcolor, no separate bar), eased entrance/exit, and a
short accent underline instead of a wide bar. The eased underline's WIDTH then hit a
real, obscure ffmpeg bug during verification: drawbox has its own option literally named
`t` (an alias for `thickness`, e.g. `t=fill`), and *inside drawbox's own* `w=`/`h=`/
`x=`/`y=` expressions, the bare identifier `t` silently resolves to that option's own
value, not to elapsed time — no parse error, since `t` is a recognized identifier there,
just not the one intended. Confirmed by isolated testing: with `t=fill` set, `w='(500*t)'`
evaluated to a huge constant (the "fill" sentinel) regardless of real time or `-ss`; with
a plain numeric thickness, the same expression evaluated to `500 * <that thickness
number>`, completely ignoring elapsed time. (`enable=` is unaffected — confirmed via a
separate isolated test — it's evaluated by ffmpeg's own timeline-expression framework,
not the filter's own option parser.) The earlier "`w=0` means fill-to-edge" theory from
initial debugging was a real, separately-confirmed ffmpeg behavior, but it was not the
actual root cause — the near-frame-width readings it seemed to explain made it a
plausible-looking red herring.

**Fix**: `motion_graphics.py`'s `_underline_width_segments()` computes the eased
grow/hold/shrink curve in plain Python (no ffmpeg expression involved), then emits one
`drawbox` per short time window with a literal, static width, gated by a real
`enable='between(t,...)'` clause. Verified two ways: (1) an isolated synthetic clip,
numeric pixel-width measurement at 8 checkpoints spanning entry/hold/exit — matches the
expected eased curve at every point (27→183→210, holds at ~210, 209→175→29→0), plus
visual frame inspection; (2) the actual `render.py` pipeline end-to-end (Ken Burns,
grade, vignette, transitions all composited) — three real rendered frames confirm the
text/underline animate together correctly and the graphic is fully, cleanly gone
afterward. Added `tests/test_motion_graphics.py::test_timeline_overlay_filter_underline_
width_is_never_a_t_expression` (regression-guards the exact bug class — asserts every
drawbox width is a static number, never a `t`-expression) and `test_underline_width_
segments_grows_holds_and_shrinks` (pure-function check on the eased curve). Also fixed
one unrelated stale test (`shrinks_show_time_on_short_beat` was written against an old
`MIN_SHOW=1.0` before this same redesign deliberately raised it to `1.5`, and was never
updated). Full suite: 64/64 pass.

The original prompt's animation ask ("if there's timeline or stuff like that requires
animations for making the user understand... use modern UI examples to create animation
elements") describes animated explainer graphics (timelines, maps, diagrams) that help a
viewer understand content the narration is describing — not general editing polish.

What exists today — Ken Burns pan/zoom, kinetic caption pop-in, varied ffmpeg
transitions, color grade/grain/vignette — is real, verified, and worth keeping, but it
is a different thing: it's *how footage is cut and treated*, not *a graphic generated to
explain the content*. Marking "animations" done based on this was a scope error. The
user is right that they can't see any animations, because the specific kind they asked
for was never built.

**What "done" would look like** (my own product judgement on scope, since the prompt
explicitly delegates this): when a beat's `entity_type` is `place` or `event` and the
underlying fact plausibly involves a sequence/location (dates, a journey, a series of
events), overlay a simple, tasteful animated graphic instead of (or on top of) the stock
visual — e.g. an animated map pin/route for a place, an animated timeline bar/ticks for
a date range or sequence of events, a simple animated stat/number callout for a
surprising figure. Built with ffmpeg drawtext/geq/overlay filters or a lightweight
open-source motion library rendered to a transparent-alpha clip and composited in —
free/OSS only, per the standing constraint. Scope this as its own phase; don't let it
block the editor work below, but don't leave it starved either — it's the single most
visible remaining gap.

**Next**: design a small, concrete first version (one graphic type — e.g. an animated
timeline bar — end to end) rather than trying to cover every case at once. Verify with a
real generation and extracted frames, the way every other pipeline change in this
project has been verified.

---

## 3. Video editor UI (Phase B) — no visible editing feature exists

**Status: OPEN — reopened; see `Claude outputs/VIDEO_EDITOR_ROADMAP.md` for the real plan**

Built: `app/editor/` (routes.py/service.py) — `GET /api/stories/<id>/editor` reads a
story's timeline, `PATCH /api/stories/<id>/editor/captions/<cap_id>` edits one caption's
text, `POST /api/stories/<id>/editor/render` triggers `render_timeline.render_story()`
in a background thread and `GET .../render/status` polls it. Frontend: `Editor.jsx` at
`/stories/:id/edit` (linked from the story detail page's top bar) shows the visual
track and every caption, lets you click any caption to edit its text inline, and has a
"Re-render" button. Verified live in the browser end to end: opened the editor for a
real story ("The Assassins Wore Women's Clothes"), edited a caption from "Caesar's
growing" to "Caesar's rapidly growing", saved it, clicked Re-render, and confirmed the
request started a background render (toast + spinner, ffmpeg log confirmed it completed).

**A real bug was caught in the process, fixed, and regression-tested**: the API response
showed the edit succeeding, but a fresh, independent DB query afterward showed the OLD
caption text — the edit had never actually reached Postgres. Root cause: `update_caption()`
mutated the already-loaded `story.timeline` dict in place, then did `story.timeline =
timeline` (the *same* object, by reference) and committed. SQLAlchemy's flush decides
whether a column needs to be in the UPDATE by comparing that column's own before/after
history — since before and after were literally the same object, they compared equal and
the column was silently dropped from the UPDATE, even though `story in session.dirty`
was `True`. Confirmed by direct reproduction in the container (shown above); the fix is
`sqlalchemy.orm.attributes.flag_modified(story, "timeline")`, which forces the column
into the UPDATE regardless of the equality check. Applied here and defensively in
`pipeline/enqueue_story.py`'s equivalent reassignment (which happened to work only
because it runs within the same flush as the Story's initial INSERT — not a
guaranteed-safe pattern to rely on). Added `tests/test_editor.py` with a regression test
that deliberately re-fetches the row via `session.expire_all()` instead of trusting the
function's return value — a return-value-only test would not have caught this. Re-ran
the full suite (56/56 pass) and re-verified live: the caption now reads correctly on a
completely fresh page load after the fix. This is exactly the kind of "looked done,
wasn't" gap this file exists to catch — logged in full rather than glossed over.

This directly answers the "no new feature added" complaint: it's now possible to open a
story, change something, and get a new video out — the thing that was categorically
missing before. Still explicitly NOT the full editor: no trim/reorder/swap-clip, no
"build from scratch," render status is in-memory only (documented limitation, fine for
the current single-worker deployment). Those remain open — see #4 below (renumbered
from the original "AI-assisted operations" slot; trim/reorder/swap-clip should probably
come before AI-assisted editing, re-prioritize once this is confirmed working).

Done (invisible to the user, backend-only):
- `Story.timeline` JSONB schema (visual/narration/caption/music tracks).
- `pipeline/timeline.py` populates it from a real generation.
- Durable per-clip asset storage: each beat's visual + audio clip is uploaded to MinIO
  under `stories/<user>/<story>/clips/...`, with the object key recorded on the
  timeline (this session's work).
- `pipeline/render_timeline.py`: can re-render a full timeline from those durable
  assets + the caption track's own stored word timestamps. Verified against a real
  generation this session (see `CHECKLIST.md` Phase A part 2 entry).

Not done at all:
- Any UI to view or edit a timeline.
- Any API route that lets the frontend read/write a `Story.timeline` or trigger
  `render_timeline.render_story()`.
- Trim/reorder clips, edit caption text/timing, swap a clip's image, adjust music.
- "Build from scratch" mode.

**Why this matters most after #1 and #2**: the user's "no new feature added" complaint
is most true here. Everything above is real work, but none of it is something a user
can click on. This needs a real, even if minimal, visible slice next: e.g. a page that
shows a story's timeline as a simple track list, lets a human edit one caption's text,
and has a "re-render" button that actually produces a new video. That's a thin vertical
slice through the whole stack (route → service → frontend), not the full editor — but it
makes progress visible and de-risks the render-from-timeline path against a real UI
before building the rest of the editor on top of it.

**Correction (2026-09-12)**: the user directly pushed back on this being called an
editor at all — "no visible editing feature exists. This is not a video editor" — and
that's correct: this slice edits caption text and re-renders; it has no trim, reorder,
split, clip swap, or transition control, which is what "video editor" actually means to
anyone who's used one. Re-opening this as **OPEN** rather than treating it as done. A
full research-backed roadmap for the real Phase B (trim/reorder/split/swap/transitions,
desktop + mobile) now lives in `Claude outputs/VIDEO_EDITOR_ROADMAP.md` — that file is
the plan; this entry tracks status as its phases land.

**Next**: build `VIDEO_EDITOR_ROADMAP.md` Phase B.1 (scrubbable client-side preview —
the real prerequisite for everything else in that roadmap).

---

## 4. AI-assisted single operations (Phase C) — not started

**Status: OPEN — blocked on #3**

Re-search a clip's visual, rewrite a caption via Ollama, a "polish" pass. Zero code
exists. Correctly sequenced after #3 (needs a UI to trigger from and a data model to
act on, both of which #3 provides).

---

## 5. AI chat-based iterative editing (Phase D) — not started

**Status: OPEN — blocked on #3, #4**

The single most-anticipated feature per the original prompt's own framing ("after this
is done" — explicitly sequenced last). Needs: a chat UI, an Ollama prompt that turns a
natural-language request into a targeted timeline patch, and ideally a way to re-render
only the affected clip(s) rather than the whole video (render_timeline.py currently only
does a full-timeline re-render — per-clip-only re-render is a real optimization to
design once this phase starts, not before).

---

## 6. Custom video player — shipped features not confirmed seen by the user

**Status: FIXED — NEEDS RE-VERIFY (user acknowledgement)**

Chapter tick marks, playback-speed cycling, picture-in-picture, and the fullscreen
distortion fix are all real, shipped, and were verified live in a browser earlier this
session. The user hasn't been shown these directly and may not know they exist — worth
a short, explicit callout/demo rather than assuming "shipped and verified" reads to them
as "done." Not re-opening this as broken; flagging it as a communication gap, since part
of the current frustration is "you didn't do half of the things asked" and this is a
case of real, done work that just hasn't been made visible.

---

## 7. Multi-voice + prosody

**Status: VERIFIED.** 14-voice pool, random per video; rate/pitch vary by beat position
and punctuation. Real, documented ceiling: edge-tts has no "styles"/express-as feature
at any settings (confirmed via source inspection) — revisit only if a different free/
OSS TTS engine with real expressive styles is found later.

## 8. Fonts / caption typography

**Status: VERIFIED.** 3 real installed OFL fonts + DejaVu, picked per video, confirmed
via `fc-list` that "Noto Sans Black" was never actually installed before this.

## 9. Music bed

**Status: VERIFIED.** 5 CC0 tracks (HoliznaCC0/FMA), ducked under narration, random pick.

## 10. Video title removed from burned-in render

**Status: VERIFIED.**

## 11. Subtitles overflowing frame

**Status: VERIFIED.** Character-budget-based line chunking replacing fixed word count.

## 12. Placeholder gradient background frequency

**Status: MITIGATED, not eliminated.** Root-caused (descriptor-strip-list gaps) and
substantially reduced; a placeholder fallback is structurally inherent to "sometimes no
real image matches a query" — the goal was rare + visually intentional (radial vignette
+ grain) when it fires, not literally zero occurrences.

## 14. Adopt persona-driven work, organization-style

**Status: ADOPTED — process change, ongoing**

Per the user's explicit clarification (see `UNDERSTANDING.md`): work should read as
distinct role personas taking ownership of their domain (a sound designer for audio, a
creative director for visual quality bar, a systems architect for infra calls), not one
undifferentiated voice. Adopted starting this session — reflected in how updates are
framed from here on, not a code change.

## 15. Motion graphics catalog — extend beyond the year/timeline marker

**Status: OPEN**

The v1 graphic (see #2) is confirmed working but intentionally narrow (one trigger: a
detected year). Needs a real catalog, each keyed off a different signal already present
in beat data:
- **Numbers/statistics** (e.g. "over 3,000 soldiers", "for 40 years") — an animated
  counter or stat callout, reusing the same drawbox/drawtext mechanics as the timeline
  marker.
- **Place names** (`entity_type == "place"`) — some lightweight animated map/location
  treatment; needs a real (free/OSS) source of map line-art or a programmatic approach
  (ffmpeg geq/lavfi drawing), since there's no map-tile service in scope here.
- **Comparisons/contrasts** — a simple split or before/after graphic.

Each new graphic type should follow #2's proof pattern exactly: build the ffmpeg filter
fragment, test it standalone against a synthetic clip with extracted frames before
wiring into `render.py`, then verify against a real generation.

## 16. Animated placeholder background (not a static image)

**Status: VERIFIED**

`fetch_visuals._placeholder_clip()` replaces the old static-image `_placeholder()`:
generates a short (4s), seamlessly-loopable animated backdrop — the same radial
vignette palette as before, but its center now drifts in a slow ellipse and a soft
diagonal light sweep oscillates across the frame (driven by `sin()`, not a modulo wrap,
specifically so it's continuous at the loop point — render.py plays this with
`-stream_loop -1` for any beat longer than 4s, so a non-periodic sweep would have
visibly jumped every repeat). Saved as `.mp4` instead of `.jpg` so it flows through
render.py's existing video-clip branch with no special-casing needed there. Verified
with a real ffmpeg encode + extracted frames at t=0.05/2.0/3.9s showing the glow
genuinely relocate across the frame (not a static image), plus 4 new automated tests
(`tests/test_fetch_visuals.py`): valid video of the right duration, measurable
frame-to-frame difference (confirms real motion, not a still saved as video), a
near-seamless loop point (small but nonzero difference between first/last frame), and
palette variety by seed. 60/60 tests pass.

This is the first shipped instance of the "full-frame animation, not just a small text/
icon overlay" ask (#17) — Marcus (Creative Director persona): deliberately restrained
(a drift + a soft light sweep, not anything busy), matching the "documentary, not
content" bar rather than reaching for maximal motion just because full-frame motion is
now possible.

`fetch_visuals._placeholder()` currently renders one static image (radial vignette +
grain) when no real stock visual matches a beat — real Ken Burns pan/zoom is applied to
it afterward like any other still, but the *backdrop itself* doesn't move on its own.
Per the user's direct ask, this should become a genuinely animated backdrop (e.g. slow
drifting light/particle motion, an animated gradient sweep) generated once via ffmpeg
lavfi filters (`geq`, `noise`, gradients with time-varying expressions) and rendered to
a short seamlessly-loopable clip, so a placeholder beat gets real, deliberate motion
instead of a still image being panned. This is a good first target for the "full-frame
animation" ask (#17) since it's the smallest, most contained surface to prove full-frame
motion graphics on before attempting anything larger.

## 17. Full-frame animated graphics ("Pixar/Disney quality")

**Status: OPEN — honest ceiling documented, real version scoped**

See `UNDERSTANDING.md`'s follow-up-clarification section for the full reasoning. Short
version: literal 3D character animation at Pixar/Disney quality is not achievable by any
automated, free, self-hosted system — that's a real, permanent ceiling, not a shortcut.
What's real and worth building: full-frame **2D motion graphics** (animated title
sequences, kinetic-typography scenes, particle/light effects, illustrated scene
transitions) at the highest quality the free ffmpeg-based toolchain allows, applied
first to the placeholder-background case (#16) and then to any beat where it would
genuinely read as a deliberate documentary/motion-graphics choice — not indiscriminately
covering every beat, which would look busy rather than professional.

## 18. Sound effects

**Status: VERIFIED**

Shipped as a **generated**, not sourced, asset — `pipeline/generate_sfx.py` synthesizes
`pipeline/assets/sfx/whoosh.mp3` from ffmpeg's own noise/filter primitives (two
independent pink-noise bands, crossfaded via linear envelopes into a rising spectral
sweep), the same "generate, don't source" approach already used for `motion_graphics.py`
and the animated placeholder backdrop (#16). This wasn't the first plan — CC0 licensing
discipline was applied first, same as the music bed: Kenney.nl's freely-scriptable CC0
audio packs (`interface-sounds`, `impact-sounds`, `digital-audio`, all confirmed CC0 via
their own license pages, downloaded and inspected) turned out to be uniformly
game/sci-fi flavored (click/confirm/error/zap/laser/impact) with nothing resembling a
soft cinematic whoosh, which would clash with this project's own "documentary, not
content" bar even where something whoosh-adjacent existed; Freesound.org's per-file
licenses can't be reliably verified/downloaded without a human in a browser; Pixabay's
sound-effects section blocks non-browser fetches (403). Generating it sidesteps all of
that with zero licensing risk — see `pipeline/assets/sfx/GENERATION.md` for the full
reasoning and the exact synthesis method.

Wired into `render.py` sparingly, on exactly two cue types, never on every cut: an
**accent transition** (`"circleopen"`/`"radial"` — a named person entering/leaving frame
relative to a place/event), timed to the middle of the crossfade; and a **motion-graphic
reveal** (the year/timeline-marker overlay), timed just after that beat's clip begins.
The final audio mix was refactored from a special-cased two-input `amix` (narration +
optional music) into a generic N-branch `amix` (narration always, music/sfx branches
added only when present) so "music only" / "sfx only" / "both" / "neither" are the same
code path, not different ones.

**Verified, not assumed**, at three levels: (1) the synthesized whoosh itself — decoded
the real mp3 and computed an FFT-based spectral centroid across early/mid/late thirds,
confirming a real, substantial, monotonic rise (2141→3445→4124Hz) and a genuine
fade-in (not a click); (2) the cmd/filter-graph construction — 3 new unit tests
(`tests/test_render.py`) confirm zero sfx wiring when no cue fires (hard-cut, no year
label), and that both cue types independently add the `whoosh.mp3` input with the
correct `adelay` offset; (3) a real end-to-end render with a beat that triggers both cue
types in one video — decoded the actual output audio and confirmed real high-frequency
transient energy at both expected cue timestamps (28-38x the energy of a quiet region
elsewhere in the same clip) and nowhere else. Full suite: 90/90 pass.

## 19. Subtitle typography v2

**Status: OPEN**

Font variety + kinetic pop-in + semantic emphasis coloring already shipped and verified
(see #8). "Better, professional typography" likely means the visual *treatment* now: a
documentary-style background plate/safe-area behind the caption block for legibility
against busy footage, refined contrast/shadow, tighter integration with the frame's
overall grade — a v2 pass on a real, already-shipped feature, not a from-scratch build.

## 20. Overall bar: documentary/movie quality, not "a video generator"

**Status: ONGOING — standing design constraint, not a closeable item**

Every future pipeline decision (motion graphics, audio, typography, transitions, grade)
should be judged against "would a documentary editor have made this choice on purpose,"
not "is this technically present." Tracked here so it isn't forgotten between sessions,
same as the cohesive-product-ownership constraint in `UNDERSTANDING.md`.

## 22. Creative quality review — a real gate, not just feature-level testing

**Status: OPEN — being set up now**

Sharp gap the user caught: every verification this session has checked "does this
specific new feature work" (does the timeline overlay appear, does the caption edit
persist) — there has been no standing step where someone actually watches a generated
video as a whole and judges it against "does this read as a professional documentary,
or does it read as a generic AI-generated video," independent of whether any single
feature under test is working. That's a different, higher-level question than feature
QA, and nothing has been answering it as a matter of process.

What's being set up: `Claude outputs/QUALITY_BAR.md` — a concrete rubric (Marcus Webb's
Creative Director bar + Theo Bramwell's Video Editor bar, not vague "make it look good"
language) — and a standing habit: every real verification generation from now on gets an
explicit creative-quality verdict against that rubric logged alongside the technical
verification, not just "the feature under test worked." This is what feeds back to
"the rest of the team" (i.e., shapes what gets prioritized next in this file) rather
than quality feedback living only in this session's own judgment with nothing written
down.

First real application: the just-completed health-check generation ("the discovery of
the Rosetta Stone", story `e3523606619c`) — reviewing it now against the new rubric as
the first real instance of this process, not retroactively calling past generations
"reviewed" when they weren't.

## 23. Beat-grouping fallback silently degrades sourcing quality (real footage mismatch found)

**Status: PARTIALLY FIXED — the visibility gap and the worst symptom are addressed;
the deeper cause is still open**

Found during the first real application of the new creative-quality-review process
(#22) on the Rosetta-Stone health-check generation (story `e3523606619c`, "The Stone
That Decoded the Ancient World"). Every beat in that video had `entity_type: "scene"`
and a `visual_query` that was just the first ~60 characters of its own narration text,
cut off mid-word ("Pierre-Francois Xavier Bouchard stum..."). Root cause: `write_beats()`
in `pipeline/generate_script.py` failed structural validation on all 3 retry attempts
for this topic, silently falling through to the deterministic even-split fallback
(line 229 area) — which drops per-beat entity_type detection entirely and uses a raw
truncated sentence fragment as the "search query," with **no log line anywhere**
saying this happened. This is the exact "generic AI video" failure mode the whole
beats/entity_type system was built to prevent, quietly reintroduced by its own safety-
net fallback path.

**Concrete evidence, not a theoretical concern**: extracted frames across the video's
full length (not just the feature under test) showed beat 1 ("In 1799, French
soldier...") correctly matched a real Napoleonic-reenactor clip, and beat 2 ("...decree
issued by Egyptian pharaoh Ptolemy V in 196 BC") matched real hieroglyphic-wall footage
with the new timeline overlay correctly showing "196 BC" — genuinely good. But beat 3
("stone featured the same text in three languages...") matched an unrelated stone
inscription with a cat sitting in front of it, and beat 4 (13.4s — "revealing secrets of
a lost civilization... game-changer in Egyptology") matched a video of **someone's hand
feeding a chipmunk on a cobblestone street**, with the karaoke captions "REVEALING
SECRETS OF" burned in over it. That is precisely the kind of mismatch that reads as
generic/automated rather than documentary, and it happened because the query was a
vague sentence fragment instead of a real, specific search phrase.

**Fixed now**:
1. `write_beats()` prints a clear stderr warning whenever this fallback fires, so it
   shows up in the generation log instead of being invisible — the first step to
   knowing how often this actually happens.
2. `_fallback_query()` (new helper, used at both fallback sites) trims to the last whole
   word within the length budget instead of a hard character slice — the exact
   mid-word cut ("...stum", "...pharao") is fixed. Regression tests added
   (`tests/test_beats.py`), 62/62 pass.

**Still open, and the more important half**: word-boundary trimming does not fix the
*semantic* vagueness — a truncated sentence fragment is still a worse query than a real
short search phrase, which is exactly why beat 4 still matched something as wrong as
chipmunk-feeding footage even with a whole-word cut. Real next steps (Amara Chen's
domain): find out how often this fallback actually fires now that it's logged; consider
more retry attempts, a repaired/simplified prompt, or a small dedicated repair call that
just asks the model for a short keyword phrase per sentence-group when the main
structured call fails, rather than falling all the way back to raw text truncation.

## 21. User media library + bring-your-own-script

**Status: OPEN — scoped, not started**

New, explicit ask: a personal media library where a user uploads their own images/
videos, which the generation pipeline can then use for a beat's visual instead of (or
alongside) auto-sourced stock, the same library is available inside the editor when
swapping a clip, and separately, a user can supply their own full script instead of
Ollama writing one.

Breaking this into real, buildable phases rather than one big undifferentiated feature:

- **Phase 1 — the library itself**: a new `MediaAsset` model (id, `user_id`, kind
  image/video, `object_key`, filename, content_type, size, created_at) + migration;
  storage namespaced as `media_library/<user_id>/<asset_id>.<ext>` (mirrors the existing
  per-user story namespacing); `POST /api/media` (multipart upload, size/type
  validated), `GET /api/media` (list your own), `DELETE /api/media/<id>`; a simple
  frontend page to upload/browse/delete. No pipeline integration yet — just "can a user
  store and see their own files," the same bottom-up order this project always builds
  in (schema → service → route → frontend → integration).
- **Phase 2 — use it in auto-generation**: the create flow lets a user optionally attach
  specific uploaded assets to the request; needs a real product decision on *how* they
  map to beats (pre-assign per beat once the script exists, vs. treating uploads as an
  extra candidate source `fetch_visuals.py` can match against a beat's query/entity_type
  alongside Wikidata/Commons/Pexels). Recommend the former (explicit per-beat
  assignment) — matching a user's own photo to the "right" beat automatically is a
  worse experience than just letting them place it.
- **Phase 3 — use it in the editor**: once Phase B's clip-swap operation exists (not
  built yet — see #3's remaining scope), "pick from your library" is one clip source
  alongside re-searching stock.
- **Phase 4 — bring-your-own-script**: a way to submit a full script (an ordered list of
  beats, or a single narration block generate_script.py's own sentence-splitter chops
  up the same way it does today) that skips the Ollama writer entirely. Real open
  question needing a product decision before building: does the fact-check pass still
  run on a user-authored script? Recommend yes, unconditionally — the review desk's
  claim-flagging is still useful signal on a human's own claims, and skipping it would
  make this the one path in the app that bypasses the fact-check discipline everything
  else has. `needs_human_review`'s copy may need a small tweak ("model confidence"
  framing doesn't quite fit a human-written script) but the mechanism stays.

None of this is started. Flagging Phase 1 as the right place to begin whenever this is
picked up — it's independently useful (users may want a personal media shelf regardless
of the pipeline integration) and de-risks the storage/model pattern before Phases 2-4
build on it.

## 13. Admin/self password-change minimum length inconsistency

**Status: OPEN — minor, found today.** `password_error()` requires 10+ characters for
any self-service or admin-reset password change, but `.env`'s `ADMIN_PASSWORD` (used
only once, by `seed-admin`, to bootstrap the very first admin account) is not validated
against that same rule. `ADMIN_PASSWORD=Qwerty1@` in this repo's local `.env` is 8
characters — it bootstraps fine, but the moment anyone tries to *change* it to something
of similar length via the real change-password flow, it's silently rejected (returns an
error string the caller must check — which is exactly what caused today's local-login
confusion: a test earlier in this session changed the local admin password via the
change-password feature, and a later attempt to reset it back to the original 8-char
`.env` value via a raw `set_password()` call silently no-opped because it's under 10
characters, and the ignored return value masked that). Small, real inconsistency
between bootstrap and runtime validation. Low priority — not a security bug (10 chars is
the stronger rule, not the weaker one), just a papercut worth fixing: either update
`.env.example`'s guidance to require 10+ characters, or have `seed-admin` warn if
`ADMIN_PASSWORD` doesn't meet the same bar.

---

## 54. Professional Video Quality Roadmap — Tier 1/2 implementation (2026-09-12)

**Status: VERIFIED — 5 items shipped and verified against the real stack**

Per `Claude outputs/PROFESSIONAL_QUALITY_ROADMAP.md`'s prioritized roadmap (research done
first, explicitly not implemented until the user confirmed "continue"):

- **Tier 1 #1 — per-clip color correction before the shared grade.** `render.py` now runs
  ffmpeg's `normalize` filter (`independence=0`, linked-channel — corrective, not a hue
  shift; `strength=0.6`, partial not full stretch; `smoothing=20` for real video clips) on
  each clip before the single shared creative grade, addressing the biggest identified
  cause of clips from three unrelated origins (Wikidata/Commons/Pexels) not reading as one
  production. **A real, serious bug found and fixed during verification**: wiring
  `normalize` in *after* the existing `scale=8000:-1` pre-scale (used ahead of `zoompan`)
  made a single ~2s clip balloon to 6.5GB+ RSS and get SIGKILLed by the OOM killer — found
  by watching `docker stats`/`/proc/<pid>/status` during a render that mysteriously died,
  not by reading the filter's docs. Isolated, reproduced, and fixed by moving
  `normalize` to run *before* `scale=8000:-1` (on the small source image, not the
  ~8000x14222px upscaled intermediate) — confirmed memory-flat (~350MB, stable) at both
  `smoothing=0` and the intended `smoothing=20` once reordered.
- **Tier 2 #8 — final loudness normalization.** Added `loudnorm=I=-14:LRA=11:TP=-1.5`
  (matches YouTube's own normalization target) as the last step of the audio chain, after
  narration+music are mixed. Verified: a real rendered output measured at **-13.7 LUFS
  integrated** via a fresh `ffmpeg ... loudnorm ... print_format=summary` pass — on target.
- **Tier 2 #7 — motion-graphics font now matches the video's own captions.** `render.py`
  accepts an optional `font` parameter (a `captions.py`-style dict) and threads its
  resolved file path into `motion_graphics.timeline_overlay_filter()` (new
  `motion_graphics.font_path_for()` helper), fixing audit #33 (previously always hardcoded
  Anton regardless of the caption font picked for that video). Wired through both real
  call sites: `run_pipeline.py` (auto-generation) and `render_timeline.py` (editor
  re-render). Verified visually — a real render with `font="Bebas Neue"` shows the year
  callout in Bebas Neue's distinctive condensed glyphs, not Anton.
- **Tier 2 #5 — transitions require actual subject overlap, not just matching
  `entity_type`.** New `_same_subject()` compares a bag-of-significant-words from each
  beat's own `visual_query`; the continuity crossfade now requires *both* matching
  `entity_type` *and* real word overlap, fixing audit #34 (a "person" beat about Caesar
  followed by a "person" beat about Brutus previously got treated as a continuation).
  5 new unit tests (`tests/test_render.py`) plus a real render confirming a genuine
  Caesar→Brutus subject change now produces a hard cut (`XFADE_CUT`/`"fade"`), not a
  crossfade.
- **Tier 1 #4 — beat-duration floor.** New `run_pipeline._merge_short_beats()` (called
  right after TTS synthesis, before narration concatenation) merges any beat whose real
  synthesized audio comes out under 0.9s into an adjacent beat (forward into the next
  beat where one exists, otherwise backward into the last kept one), concatenating audio
  (`tts.concat_audio` — lossless, same-voice/codec) and text, keeping the *surviving*
  beat's own visual asset. Fixes audit #38 (a punchy one-word beat could previously
  produce a sub-second "glitch" cut). Safe by construction: `captions.py` transcribes the
  final concatenated narration directly (word-level, not beat-boundary-based), so it's
  indifferent to how many beats the audio was assembled from. 5 new unit tests
  (`tests/test_run_pipeline.py`) cover forward merge, backward merge, cascading
  double-merge, no-merge, and single-beat-alone cases.

Full test suite: 75/75 pass.

**Tier 2 #9 — face-unaware Ken Burns on non-photographic portraits (closes audit #35),
added right after the above**: `fetch_visuals.py`'s Haar-cascade face detection is
trained on real frontal photographs, but named historical figures sourced via Wikidata
P18/Commons are overwhelmingly pre-photography imagery — paintings, engravings, coins,
marble busts — where detection failing is the common case, not the rare one. New
`_face_or_portrait_fallback()`: when detection fails on a `"person"` beat specifically,
falls back to a documented upper-third framing guess (`PORTRAIT_FALLBACK_CENTER = (0.5,
0.35)`) instead of leaving `render.py` to default to blind dead-center — the vast
majority of single-subject portrait/bust compositions place the head in the upper third,
not centered. Every other `entity_type` keeps the plain `None` fallback (no equivalent
composition assumption to lean on for a place/event/scene image). A real face detection
always wins when one is found — this only fires on genuine detection failure. 4 new
tests, deliberately *not* mocking the detection-failure path — a real solid-color image
naturally produces no detected face via actual cv2, the same as the real paintings/busts
this fixes. Full suite: 79/79 pass.

**All of Tier 1 and Tier 2 are now complete.** Remaining roadmap items (Tier 3) either
need the user's explicit product decision (§7 item 12 — photorealistic vs. illustrated
visual direction) or explicit permission to source new CC0 audio assets (mood-matched
music variety, sound design/SFX/ambience) per this project's own download-permission
rule — not something to proceed on unilaterally.

# Full panel audit — 2026-09-12

Per explicit request: a full audit of the whole application by the entire team, in
parallel, each persona reviewing their own domain end to end (not just recent changes).
Four agents ran concurrently, each embodying 2-5 personas over one slice of the
codebase, briefed to read every real file in their domain and cross-check against this
file first so they wouldn't re-report what's already tracked.

**Honest methodology note, asked about directly and worth stating plainly**: three of
the four agents worked in isolated git worktrees with no access to the running local
Docker stack (no Postgres/MinIO/Ollama/Flask) — so everything below except where
explicitly marked otherwise is a **static code-level finding**: real, specific, traced
to actual file:line references and actual mechanisms, not generic advice — but **not
yet reproduced against the running app**. That's a real, meaningful gap against this
project's own "verify against the real stack, never assume" rule, and these are marked
`STATIC AUDIT FINDING — NOT LIVE-VERIFIED` rather than `VERIFIED` because of it. The one
exception is Grace's migration findings (#49 below), which she confirmed by actually
running the migrations against a disposable Postgres container — that one is a
genuinely reproduced, confirmed bug, not just a code-read.

The audit agents were also killed mid-task once by the same session-wide usage-limit
reset that hit the main session, and resumed afterward — their final reports were
produced across that interruption, not in one uninterrupted pass. Worth knowing, not
a reason to distrust the findings: the reports that came back cite specific file:line
evidence and traced mechanisms (and in Grace's case, an actual reproduction), which is
a real, substantive review — but "read carefully" is not the same claim as "confirmed
live," and every item below should be reproduced against the real stack before being
promoted to `VERIFIED` or acted on as certain.

## Backend / Security (Tomasz Kowalski + Raj Mehta)

### 24. `job_manager.get_status()`'s job-promotion runs with no lock — can double-spawn the same pipeline subprocess

**Status: VERIFIED FIXED.** Promotion (and the crashed-job self-heal ahead of it) now
runs under the same `_lock` `start()`/`cancel()` already hold — see
`app/generation/job_manager.py`'s `get_status()`. Verified: full test suite re-run
against the real local stack after the change (61/62 pass; the one failure is the
pre-existing, unrelated `motion_graphics.py` v2 test — see #2's still-open frame-accuracy
work), app container restarted cleanly on the fixed code.

`app/generation/job_manager.py`'s `get_status()` promotes the oldest queued job to
running (~lines 139-164) with no `with _lock:` around it, unlike `start()` and
`cancel()`, which both take the lock. Traced mechanism: the DB-level partial unique
index only guarantees one *row* has `status='running'` — it does not prevent two
threads from both completing an `UPDATE` on the *same* row and both then calling
`_spawn(job)`, since that's not a second row, so the unique index sees no conflict.
With gunicorn's `--workers 1 --worker-class gthread --threads 4` and the frontend
polling `/api/generate/status` every 2.5s, two racing polls landing at the moment a job
finishes is a plausible, not contrived, scenario — and if it happens, it launches two
real `run_pipeline.py` subprocesses against the same Ollama instance, which is exactly
the "concurrent requests truncate each other's output" failure this project's whole
one-subprocess-at-a-time design exists to prevent. Fix: wrap the promotion block in the
same `_lock` `start()`/`cancel()` already use.

### 25. No `ProxyFix` behind Caddy — every per-IP rate limit is actually one shared, site-wide bucket

**Status: VERIFIED FIXED.** `app/__init__.py`'s `create_app()` now wraps
`app.wsgi_app` in `ProxyFix(app.wsgi_app, x_for=1, x_proto=1)`, trusting exactly the one
hop Caddy's `reverse_proxy app:8787` represents (Caddy sets `X-Forwarded-For`/`-Proto` by
default, confirmed by reading the `Caddyfile` — no extra Caddy config needed). Verified
in isolation with a real `werkzeug.test.EnvironBuilder` request carrying a
`X-Forwarded-For` header: `REMOTE_ADDR` as seen by the app correctly becomes the real
client IP instead of Caddy's container IP. App container restarted cleanly on the fixed
code; full test suite still 61/62 (same pre-existing unrelated failure as #24).

`app/extensions.py`'s `Limiter(key_func=get_remote_address, ...)` reads
`request.remote_addr`, but every request reaches Flask via `Caddy → reverse_proxy
app:8787` inside the Docker Compose network — meaning `remote_addr` is always Caddy's
container IP, never the real client's, since nothing calls `ProxyFix`/trusts
`X-Forwarded-For` anywhere in the app. Two real consequences: the login/signup rate
limits (`5 per minute` / `5 per hour`) aren't per-attacker — they're one global budget
everyone shares — and it's also a self-inflicted availability bug (5 real, different
people logging in within the same minute 429s everyone else until the window rolls
over). Cheap, correct-regardless-of-scale fix: `app.wsgi_app = ProxyFix(app.wsgi_app,
x_for=1)` in `create_app()`, trusting exactly the one hop Caddy represents.

### 26. Background daemon threads never call `db.remove_session()` — a resource-lifecycle gap and a latent stale-session risk

**Status: VERIFIED FIXED.** Both `job_manager._watch()` and `editor/service.py`'s
`_run()` now wrap their bodies in `try/finally: db.remove_session()`. Verified: full test
suite re-run against the real local stack (61/62, same pre-existing unrelated failure),
app container restarted cleanly.

`remove_session()` is only ever called from Flask's `teardown_appcontext`
(`app/__init__.py`). Two ad-hoc daemon threads open a DB session via `get_session()`
and never call it: `job_manager._watch()` and `editor/service.py`'s `_run()` (the
re-render thread). Since `scoped_session`'s default registry key is
`threading.get_ident()`, and CPython can reuse thread ids once a thread exits, a later
short-lived thread that happens to get a reused id could inherit a previous thread's
abandoned session state from the registry — separately from that edge case, this is
also a plain unbounded memory leak in the scoped_session registry over the server's
lifetime. Fix: wrap both thread bodies in `try/finally: db.remove_session()`.

### Reviewed and confirmed solid (Tomasz + Raj)

Ownership scoping at every layer (route + service, consistently 404-not-403), CSRF
coverage (global `CSRFProtect`, zero exemptions found), session invalidation on
credential change (mechanism traced fully, matches what's already recorded verified),
and the blast radius of the already-fixed `flag_modified` JSONB bug (grepped all of
`app/` — no other occurrence). No new findings in any of these areas.

## Frontend / Mobile (Ines Torres + Naomi Park)

### 27. Editor.jsx's caption-save has no Undo, breaking the app's own established convention

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

Every other reversible mutation in this app (`StoryDetail.jsx`, `StoryCollection.jsx`,
`AdminUsers.jsx`, `Review.jsx`) wires an `undo` callback into its success toast.
`Editor.jsx`'s `saveCaption()` fires a bare success toast with no `action` — a caption
edit is exactly as reversible as those (you can just edit it back), yet it's the one
mutation in the app that doesn't offer the one-click way to do that. Fix: capture the
caption's previous text before saving and pass it as the toast's `undo` callback, same
shape as everywhere else.

### 28. Editor.jsx's "Re-render" has neither a confirm dialog nor an undo, despite overwriting the currently-eligible video for everyone

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

The app's own stated rule is: confirm dialogs are for actions that discard
in-progress work or affect someone else, matching the existing "Stop generation"
dialog's explicit reasoning. Re-rendering overwrites the current approved/eligible
video with no snapshot kept anywhere — at least as destructive as the case that already
gets a confirm dialog, and right now `rerender()` just fires immediately on click. Not
an automatic "add a dialog" — a real product decision to make deliberately, since a
confirm dialog on every caption-edit-then-rerender loop could get annoying; worth
Priya's/Ines's judgment on the right shape (maybe only confirm if there's no
in-progress unrendered edit vs. re-confirming every time).

### 29. Real, pre-existing one-off inline styles bypassing the design-token scale

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

Not new to this session, but real and untracked: `Account.jsx`, `AdminUsers.jsx`'s
`ResetPasswordDialog`, and `AppShell.jsx`'s mobile `AccountSheet` all hardcode raw pixel
values (`gap: 12`, `marginBottom: 20`, `fontSize: 14`, `padding: 20`, etc.) instead of
referencing the existing `--s-1` through `--s-12` spacing scale, which already covers
every one of these exact values by name. Separately, `style={{ fontSize:
"var(--text-sm)" }}` is repeated verbatim across six call sites in four files — at
least token-referencing, but repeated enough to be its own class rather than an inline
style each time.

### 30. `Editor.jsx` has zero mobile media queries — confirmed by grep, not assumed

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

`grep -n "@media" pages.css` shows 15 breakpoints, none touching any `.editor-`
selector — every other real page surface (Review's queue/decision-bar treatment,
StoryDetail's grid stacking) has an explicit mobile pass; the editor, shipped this
session, has none. Concrete consequence: the caption Save/Cancel buttons are `size="sm"`
(32px height) sitting next to a 44px-tall text input in the same row, with no mobile
breakpoint to correct it the way Review's decision buttons get bumped to 50px at 767px.

### 31. The custom video player's control buttons are a fixed 30×30px at every viewport — the one component actually being watched on a phone

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

`.vplayer-btn { width: 30px; height: 30px; ... }` with no breakpoint anywhere bumping
it up for touch — governs play/pause, speed-cycle, PiP, fullscreen. Under the ~44px
minimum touch target on every device, not just narrow ones.

### 32. Volume control is dead on touch in a real width range, then silently removed below 480px with no substitute

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

`.vplayer-vol` only expands on `:hover` or the slider's own `:focus-visible` — on
touch there's no hover, and a 0-width element can't be tapped to receive focus, so
between ~481-1023px (large phones landscape, small tablets) the control renders but is
permanently inert. Below 480px, `.vplayer-volume` (wrapping both slider and mute button)
is simply `display: none` — no on-screen mute/volume control at all on an actual phone
in portrait, with nothing substituted. May be an acceptable tradeoff, but reads as an
accidental casualty of the hover pattern rather than a deliberate decision right now.

### Reviewed and confirmed solid (Ines + Naomi)

`Editor.jsx`'s structural rhythm (back button, EmptyState/ErrorState/Skeleton reuse,
`label`-styled section heads, the shared `Button` primitive) correctly reads as the
same app, not bolted-on. `StoryPoster.jsx`'s hover-preview correctly gates behind
`matchMedia("(hover: hover) and (pointer: fine)")`. `.collection-restore`'s hover-fade
is correctly wrapped in the same media query. The mobile `AccountSheet`'s touch targets
are a real, comfortable 48px. Review's queue-to-horizontal-scroll and pinned-decision-
bar mobile treatments are genuinely well-built — the contrast with Editor.jsx having
none of this is what makes #30 worth flagging, not a knock on Review.

## Pipeline / Creative (Marcus Webb, Theo Bramwell, Dana Okafor, Sam Ruiz, Amara Chen)

### 33. The timeline-marker graphic's font never matches the video's own caption font

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

`motion_graphics.py` hardcodes Anton as `FONT_PATH`, but `captions.pick_font()` picks
one of four typefaces randomly per video, and `render.py` never threads that choice
into the overlay filter call. On 3 of 4 generated videos, the year callout is set in a
different display face than the captions in the same frame — a real type-system
mismatch. Fix: thread the video's picked font through to the overlay filter (both in
`render.py` and `render_timeline.py`, which hits the same hardcoded path).

### 34. Transition logic treats "same entity_type" as "same subject" — it isn't the same claim

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

`render.py`'s `_transition_style()` fires a smooth continuity crossfade whenever two
consecutive beats share an `entity_type`, with no check on whether they're actually the
same named person/place. A beat about Caesar followed by a beat about Brutus (both
`entity_type: "person"`) gets treated as an uninterrupted continuation when it's
editorially a real subject change deserving a harder cut. Fix direction: compare
`visual_query`/a normalized name in addition to `entity_type` before granting the
smooth-continuation transition.

### 35. Face detection (Haar cascade, photo-trained) is structurally mismatched for the imagery "person" beats actually source

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

Pre-photography historical figures are sourced almost exclusively as Wikidata P18
images that are paintings, engravings, coins, or busts — profile-view/stylized imagery
is the norm for this content type, not the exception, and `haarcascade_frontalface_
default` is trained on real frontal photos. When detection silently fails (documented,
by design), Ken Burns defaults to blind dead-center framing — common for this asset
type, not rare. Worth a documented fallback heuristic (bias upper-third for portrait-
style busts/paintings) rather than pure center.

### 36. (Lower confidence, needs a real frame check) The year-marker's own clock may start before an incoming crossfade has visually resolved

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED, LOW CONFIDENCE**

The overlay's `t=0` is anchored to the padded clip start (extended by half the
adjoining transition's duration), not to when the crossfade has actually finished
blending — for a beat preceded by a 0.45s smooth crossfade, the line-draw could begin
~0.2s into a still-resolving dissolve. Possibly imperceptible. Needs an actual extracted
frame to confirm either way before treating as real.

### 37. Real correctness bug: the first beat's crossfade offset can go negative

**Status: VERIFIED FIXED — reproduced and fixed with a real ffmpeg encode**

`render.py`'s cut loop now clamps: whenever `offset` would go negative, the transition
duration for that cut shrinks to fit the accumulated duration available instead of
trusting the arithmetic (`offset` floors at 0). Verified by actually reproducing the
crash scenario — a synthetic 3-clip sequence with a deliberately short (0.2s) first beat,
run through `render()` for real (real ffmpeg encode, real music mix, not just reading the
code) — which previously would have handed `xfade` a negative offset; the fix produces a
valid 279KB/4.13s output instead.

`render.py`: `offset = acc_duration - t` for the first transition, where
`acc_duration = requested[0]` and `requested[0]` only gets the *right-side* transition
padding (not left, since there's no beat before it). If beat 0's real narration
duration is shorter than half the crossfade duration (0.225s for a smooth transition) —
plausible for a punchy one-word hook line, which the writer prompt explicitly wants —
`offset` goes negative, an invalid argument to ffmpeg's `xfade`. Every later cut is
protected by then having much larger accumulated duration; this is specifically a
first-beat exposure. Fix: clamp `offset >= 0` (and correspondingly shrink the
transition duration for that cut) rather than trusting the arithmetic.

### 38. No floor/ceiling on a beat's actual rendered duration

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

Nothing merges a too-short beat into a neighbor or splits an overlong one — durations
are whatever `tts.py` measures from whatever grouping `generate_script.py` produced,
with no safety net. A single short exclamatory sentence grouped as its own beat could
produce a sub-second clip with no guard against it reading as a glitch.

### 39. Escalation of #23: the even-split fallback is a *pacing* bug too, not only a sourcing bug

**Status: STATIC AUDIT FINDING — extends #23, not a duplicate**

`_even_groups()`'s `divmod`-based sentence-count split chooses beat *boundaries*
content-blind, the literal "divide runtime evenly and call it pacing" anti-pattern.
Whoever scopes the deeper fix for #23 (better prompt/retry/repair) should judge it
against cut-boundary quality too, not just query quality — a fix that only patches the
search phrase but leaves count-based grouping in place still ships a mechanically-paced
video when it fires.

### 40. Music has a fade-out but no fade-in — every video's music enters on a hard cut

**Status: VERIFIED FIXED — real ffmpeg encode with real music mixed in confirms it**

`render.py` now mirrors the existing `afade=t=out` with `afade=t=in:st=0`, both durations
clamped to at most half the video's total length so a very short video can't overlap the
two fades into something louder than either alone. Verified with the same real ffmpeg
encode used for #37, using one of the project's actual CC0 tracks
(`pipeline/assets/music/documentary/drifting-piano.mp3`) — encode succeeded with both
fades present in the filter graph.

`render.py`'s music mix has one `afade=t=out` call and nothing mirroring it on entry —
music hits its full ducked volume the instant the filter chain starts. Contradicts
Dana's own bar ("no audible hard cut in or out") and wasn't caught by #9's "VERIFIED"
claim, which checked presence/ducking, not the entrance. Fix: mirror the fade-out with
a short `afade=t=in:st=0:d=~0.6-1s` on the `[music]` label.

### 41. Escalation of #7 (marked VERIFIED): prosody variation is really two discrete presets, not a curve across the piece

**Status: STATIC AUDIT FINDING — escalates an existing VERIFIED item**

`tts.py`'s `_prosody_for()` only differentiates beat index 0 (hook) and the last index
(closer) — every beat in between gets byte-identical rate/pitch regardless of position,
varying only if that specific sentence happens to end in `?`/`!`. For a typical 4-6 beat
script, that's the majority of the video reading with identical delivery. #7's "varies
by beat position" claim is true at exactly two discrete stops, not a real curve. Fix
direction: interpolate rate/pitch smoothly across beat index, or add a genuine middle
arc.

### 42. Minor: music always starts at t=0, never a random offset

**Status: STATIC AUDIT FINDING — low priority**

With only 5 tracks in rotation, two videos landing on the same track sound identical
from the first second. No looping-seam risk (tracks are long enough), just a repetition
note.

### 43. Emphasis word list overlaps heavily with the writer prompt's own hook vocabulary

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED, needs a real spot-check**

`captions.py`'s `_EMPHASIS_RE` list ("first," "only," "secret," "never," "forgotten,"
"vanished," "discovered," "true," "everything," "last," "final"...) overlaps
suspiciously with the exact curiosity-gap/contrarian-hook vocabulary
`WRITER_SYSTEM_PROMPT` explicitly instructs for hook lines. Risk: the accent color
could fire hardest on exactly the hook line, where Sam's bar says it should be rarest.
Not confirmed against a real render — worth a spot-check on a handful of real hook
lines before treating as a real problem.

### 44. The editor's caption-edit fallback visibly downgrades the karaoke effect for edited captions specifically

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

Editing a caption deliberately clears its per-word timestamps (reasoned tradeoff — stale
timing would be worse). But `build_ass_from_track`'s fallback then treats the whole
edited phrase as one fake "word," so the pop-in/emphasis animation applies to the whole
phrase as a unit — every other caption in the same video still pops word-by-word. The
tradeoff was reasoned as an engineering necessity, but nobody's actually looked at what
it looks like next to its neighbors. Needs a real screenshot before calling it settled.

### 45. `_validate_beat_groups` has no type-checking on `sentences` — a plausible model quirk crashes the whole generation instead of triggering the (now-hardened) fallback

**Status: VERIFIED FIXED.** `_validate_beat_groups` now rejects any non-`int` (and
explicitly excludes `bool`, a Python `int` subclass) element before doing arithmetic on
it, returning `None` — the same "fall through to retry/fallback" path every other
validation failure already uses — instead of raising an uncaught `TypeError` that would
have killed the whole generation. Full test suite re-run after the change (61/62, same
pre-existing unrelated motion-graphics failure).

`idx = [n - 1 for n in nums]` assumes every element is an int. A model returning
JSON-string numbers (`["1","2"]`) raises an uncaught `TypeError` with no retry. A model
returning floats (`[1.0, 2.0]`) is worse — `0.0 == 0` lets the contiguity check pass
silently, then `sentences[i]` raises `TypeError` on float indexing later. Neither is
caught by the existing `except` around `_chat_json`, so this kills the whole generation
rather than falling through to the fallback that was just hardened for a *different*
failure mode. Fix: validate each element is `isinstance(n, int)` before doing
arithmetic, falling through to the same `None` return other validation failures use.

### 46. `generate()`'s own retry loop has the identical silent-fallback-no-log bug just fixed in `write_beats()`, one level up

**Status: VERIFIED FIXED.** Every failed attempt in `generate()` now prints which
attempt number, exception type, and message to stderr before continuing — lands in
`job_manager`'s captured generation log, same as `write_beats()`'s existing fix. Full
test suite re-run after the change (61/62, same pre-existing unrelated failure).

Every attempt-level failure in `generate()` (a missing writer key, a `fact_check()`
exception) is caught by one broad `except` and silently `continue`s, for all attempts,
with zero logging — only a bare, stage-agnostic `RuntimeError` after everything's
exhausted. The exact class of bug #23 already fixed one layer down. Fix: log which
stage and which exception on every failed attempt here too.

### Reviewed and confirmed solid (all five pipeline personas)

The animated placeholder backdrop (#16) — genuinely good, no new issue. Multi-voice
pool and font/OFL installation discipline (#7 base claim / #8) — implemented as
described. Music licensing (`SOURCE.md`) — in order, checked, nothing new. The
beat-fallback sourcing mismatch itself (#23) — already fixed for word-boundary
truncation, its remaining semantic-vagueness half correctly left open, not duplicated.

## Infra / Legal / QA (Grace Liu, Elena Voss, Jordan Blake)

### 47. Two migrations crash on database states their own docstrings admit are possible — reproduced, not just read

**Status: VERIFIED FIXED — reproduced, fixed, and re-verified against a disposable
Postgres container (not the real stack's data)**

Both migrations are now defensive:
- `7d6d14915223`: only enforces `created_by_id SET NOT NULL` when the backfill actually
  left zero NULLs; otherwise logs a clear warning and leaves the column nullable rather
  than crashing the upgrade.
- `24759f5939e5`: before creating the partial unique index, demotes every `running` row
  except the oldest to `status='error'` with an explanatory message, so the exact
  pre-fix race this index exists to prevent can no longer crash the migration that fixes
  it.

Re-verified by reproducing both original crash scenarios from scratch against a fresh
`postgres:16-alpine` container (a story row with zero `users` rows; two `generation_jobs`
rows already `status='running'`) — both now complete with exit code 0, and the expected
warning/error-demotion actually happened (checked via direct `SELECT`). Also confirmed
the happy path is unchanged: with a real admin present and no duplicate running rows,
`created_by_id` still ends up `NOT NULL` exactly as before.

Original finding, for reference — Grace spun up an isolated `postgres:16-alpine`
container and ran the actual `alembic` binary from the built image against it:

Grace spun up an isolated `postgres:16-alpine` container (never touching the real
stack's data) and ran the actual `alembic` binary from the built image against it:
- `7d6d14915223_scope_stories_to_their_owner.py`: with a `stories` row present and
  zero `users` rows, the admin-backfill `UPDATE` finds no admin, leaves
  `created_by_id` NULL, and the following `ALTER COLUMN ... SET NOT NULL` raises
  `IntegrityError` — confirmed by actually triggering it.
- `24759f5939e5_one_running_job_at_a_time_db_enforced.py`: with two `generation_jobs`
  rows already `status='running'` (exactly the pre-fix race this migration exists to
  prevent), creating the partial unique index raises `UniqueViolation` — confirmed by
  actually triggering it.

Since `docker-compose.yml`'s `app` command is a single `&&`-chained shell command
ending in `gunicorn`, either failure means the container never starts, `restart:
unless-stopped` retries the same failing command forever, and the app is fully down
with no automatic recovery. Not a live risk *today* (these DB states don't currently
exist on the real system) — a real landmine for a future partial restore or reused
migration history. Fix: make the *upgrade* defensive (skip/guard the `NOT NULL` if no
admin exists yet; `UPDATE` extra "running" rows to `'error'` before creating the unique
index) rather than trusting the precondition silently.

### 48. CI never runs the test suite before deploying to production

**Status: STATIC AUDIT FINDING — confirmed by reading the actual workflow file**

`.github/workflows/deploy.yml` has no `pytest` step anywhere — checkout → build
frontend → docker build/up → restart caddy → health check. The health check confirms
the app *starts*, not that ownership scoping or the generation queue still work. Every
push to `main` deploys regardless of test suite status. Fix: add a `pytest` step (at
minimum the fast pure-function tests) gated on failure, before the build/deploy steps.

### 49. Unpinned `:latest` tags for minio, ollama, netdata; no healthchecks on minio/ollama

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED (not a current live issue, a
fragility risk)**

`caddy`/`postgres` are correctly pinned; `minio`/`ollama`/`netdata` aren't — a fresh
pull gets whatever "latest" resolves to that day, no reproducibility, no changelog
gate. Separately, neither `minio` nor `ollama` has a `healthcheck`, so `depends_on`
only confirms the container *process* started, not that the HTTP API inside is ready —
`storage.ensure_bucket()` and the `ollama pull` init step both have zero retry logic,
so a slow first boot on a small box could fail the whole `app` startup chain. Not
happening today (containers have been up for hours) — worth fixing before the next
cold start/reboot. Fix: pin the three tags; add real `healthcheck:` blocks and switch
dependents to `condition: service_healthy`.

### 50. Two of three bundled fonts carry the wrong font's copyright notice

**Status: STATIC AUDIT FINDING — a real licensing-hygiene gap, confirmed by reading
`OFL.txt`**

`pipeline/assets/fonts/OFL.txt` states only Anton's own copyright line, but Archivo
Black and Bebas Neue are separately, independently copyrighted OFL fonts — OFL 1.1
requires each copy carry *that font's own* copyright notice, not a different font's.
Fix: pull each font's own actual copyright line and either keep three separate license
files or append all three real notices to the shared one.

### 51. Wikimedia User-Agent string doesn't meet Wikimedia's own API policy, and misdescribes the project

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED**

`fetch_visuals.py`'s `HEADERS` UA string has no contact info (required by Wikimedia's
UA policy so operators can reach you) and still says the project's old name
("history-shorts") and "personal hobby project" — no longer accurate for a multi-user
signed-up product. An unidentifiable UA is exactly what gets throttled/blocked without
warning under that policy. Fix: update to name the real project and include a real
contact point.

### 52. No license/attribution captured for individual Wikimedia Commons/Wikidata images

**Status: STATIC AUDIT FINDING — NOT LIVE-VERIFIED, distinct from the music/fonts case**

Unlike the music bed (a small, fixed, one-time-vetted set with a durable `SOURCE.md`),
Commons/Wikidata images are fetched fresh per generation, per beat, unbounded — and
`_commons_imageinfo()` never requests `extmetadata` (where the actual per-file license
lives), so a CC-BY/CC-BY-SA file with a real attribution requirement could be burned
into a rendered video with no credit anywhere and no mechanism to provide one. "It's on
Commons" isn't itself a clearance — Commons hosts a real mix of licenses. Fix
direction: fetch `extmetadata` alongside the existing call, reject/flag files under a
license requiring attribution this pipeline can't currently render, or surface a credit
line somewhere (dossier metadata, end-credits caption).

### 53. The entire test suite never goes through a real Flask route — an entire layer of the app is invisible to it

**Status: STATIC AUDIT FINDING — the single biggest test-coverage gap found**

Every test calls a service-layer function directly; none use Flask's test client or
exercise `@approved_required`/`@admin_required` at all. Concretely uncovered:
`app/auth/` in full (no `test_auth.py` at all); the `session_version` invalidation
mechanism has no regression test confirming an old cookie actually stops working after
a password change; `app/admin/` in full, including the explicit self-lockout guard
(admin can't demote themselves with no one left to reverse it) — about as
security-sensitive as this codebase gets, with zero coverage; `story_video`'s
Range-header streaming; the editor's render-trigger/render-status endpoints. Fix
direction: one `test_routes_smoke.py` using the real Flask test client, covering at
minimum unauthenticated/non-admin rejection, the self-lockout guard, and session
invalidation after a password change — would close the largest gap without duplicating
every existing service-level test.

### Reviewed and confirmed solid (Grace + Elena + Jordan)

Full migration reversibility (`upgrade head → downgrade base → upgrade head` round
trip passes cleanly on all six migrations, actually run — not read). Dockerfile layer
order (dependency install before app code, correct rebuild-cost ordering). Every
`requirements.txt` package genuinely permissive OSS, no "free tier of a paid product"
risk. Pexels usage matches its actual license terms exactly. No architectural drift on
the Ollama-vs-consumer-Claude reasoning. Where tests exist, they're genuinely good —
`test_editor.py`'s persistence regression test, `test_ownership.py`/`test_queue.py`'s
real-failure-mode tests, `test_beats.py`'s fallback-query regression test, and
`test_fetch_visuals.py`'s actual-motion frame-diff tests were all called out by name as
real, non-superficial tests, not manufactured praise.

## What this means for priority

30 new items (#24-53), overwhelmingly `STATIC AUDIT FINDING — NOT LIVE-VERIFIED`. Per
Jordan's own bar, none of these get promoted to `VERIFIED` or treated as certain until
someone reproduces them against the real running stack. Suggested triage, not a
mandate: #47 (migrations) is the one already-confirmed item and probably the highest
real-world severity if it were ever hit; #24/#25 (job-manager race, missing ProxyFix)
are cheap, well-understood fixes worth doing regardless of live-verification since the
mechanism is unambiguous from the code; #53 (route-level test gap) is worth closing
before trusting any of the ownership/security claims elsewhere in this file as
permanently true, since nothing currently guards against a regression at that layer.

# Real production incidents — reported by the user, 2026-09-12

## 55. edge-tts DNS/network failure kills the whole generation, nothing saved, no retry

**Status: OPEN — real occurrence in prod, root cause understood, not yet mitigated**

User-reported, with the exact stack trace from the failed-generation card in prod:

```
File ".../aiohttp/connector.py", line 657, in connect
    proto = await self._create_connection(req, traces, timeout)
  File ".../aiohttp/connector.py", line 1242, in _create_connection
    _, proto = await self._create_direct_connection(req, traces, timeout)
  File ".../aiohttp/connector.py", line 1577, in _create_direct_connection
    raise ClientConnectorDNSError(req.connection_key, exc) from exc
aiohttp.client_exceptions.ClientConnectorDNSError: Cannot connect to host
speech.platform.bing.com:443 ssl:<SSLContext ...> [Temporary failure in name resolution]
```

`pipeline/tts.py`'s `synthesize()` (`edge_tts.Communicate(...).save(out_path)`) talks to
Microsoft's `speech.platform.bing.com` over the network for every single beat, with **no
retry/backoff anywhere** in the pipeline for this or any other external network call
(Wikidata/Commons/Pexels fetches in `fetch_visuals.py` have the same gap). A transient
DNS blip on the server — which self-resolves, as literally nothing else about this
request was wrong — is currently indistinguishable from a permanent failure: it takes
down the whole generation job immediately, the user sees a raw traceback in the "last
generation failed" card, and (confirmed in the same screenshot) nothing is saved, so a
multi-minute generation has to be redone from scratch for a few seconds of bad luck on
one DNS lookup.

**Fix direction**: wrap the per-beat `synthesize()` call (and ideally the Wikidata/
Commons/Pexels HTTP calls in `fetch_visuals.py`, same class of problem) in a small
retry-with-backoff (e.g. 3 attempts, short exponential delay) that only retries on the
transient network exception classes (DNS/connection/timeout — not on a real 4xx from the
service, which retrying won't fix). Separately, surfacing "network hiccup, retrying..."
instead of an immediate raw traceback would match this project's honest-UI precedent
(no fake progress, but also no scarier-than-necessary failure for something
self-healing). Not yet implemented — this is a real, reproducible gap, not a hypothesis.

## 56. Placeholder fallback still reads as "just a gradient, no real video" in production — escalates #16/#17

**Status: OPEN — user-confirmed live occurrence; direction confirmed by the user: replace with custom animations/illustrations, not just tune the existing animated gradient**

User-reported: the second video generated in the same prod session rendered with **no
real sourced visual for at least one beat** — what appeared on screen was the animated
placeholder backdrop (#16 — a drifting radial-vignette gradient with a light sweep, not
a static image, but still just a gradient) rather than any actual photo/illustration.
The user's own framing, verbatim: *"These blank backgrounds should be replaced with
custom animations and custom illustrations."*

This isn't a new bug — #16 already documents the animated-gradient placeholder as
"MITIGATED, not eliminated" (#12) and #17 already scopes the honest ceiling ("full-frame
2D motion graphics... applied first to the placeholder-background case") as the real,
larger fix. What this report adds: **direct confirmation from an actual production
occurrence** that the current animated gradient still reads as "blank"/"no video" to a
real viewer, not just as a theoretical gap, and **explicit user direction on where #17
should go next** — actual illustrated/animated content per placeholder occurrence
(e.g. a small library of pre-built or programmatically-generated 2D scene graphics
keyed by the beat's `entity_type`/topic, not only the current single drift+sweep
treatment), rather than further tuning the gradient itself. Promote #17 from "scoped, not
started" to the next real priority once the music/SFX work in flight is done.

Also worth checking (not yet done): why this specific beat fell through the entire
Wikidata → Commons → Pexels waterfall in `fetch_visuals.py` to begin with — #12's
"descriptor-strip-list gaps" root cause may need another look at whatever query this
beat generated, alongside building the better fallback itself.
