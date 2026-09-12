# Phase B — the real video editor: research + roadmap

Direct response to: "Video editor UI (Phase B) — no visible editing feature exists. This
is not a video editor." That's a fair correction. What shipped under OPEN_ISSUES.md #3 —
`Editor.jsx` — lets a human read a timeline's clip list, edit one caption's *text*, and
trigger a full re-render. There is no trim, no reorder, no split, no clip swap, no
transition control, no scrubbable preview. It's a caption editor with a re-render button,
not a video editor. This document is the honest roadmap for closing that gap, grounded in
how real editors (desktop, mobile, and browser-based) are actually built, not a guess at
what "an editor" should have.

## 1. Research: what real editors actually do

Looked at three different categories, because Antiquary is a **responsive web app**, not
a native desktop or mobile app — none of these are a 1:1 template, but each teaches a
real lesson.

### Desktop NLEs (Premiere Pro, DaVinci Resolve, Final Cut Pro, Avid, Filmora)

Every one of them, despite wildly different target users, converges on the same core
anatomy:
- A **preview monitor** (Premiere splits this into Source + Program; Resolve/Filmora use
  one) that's always showing the current playhead position — not a static list of clips.
- A **track-based timeline** (video/audio/text/overlay as separate horizontal lanes),
  with a **playhead** you scrub, and clips you select to reveal **trim handles** at each
  edge.
- A small, consistent **tool vocabulary**: select, razor/split, ripple trim, rolling trim,
  slip, slide. Almost everything else (effects, color, transitions) hangs off this
  vocabulary rather than replacing it.
- **Snapping/magnetic timeline** behavior so clips don't leave gaps or overlaps by
  accident when moved.
- Effects/transitions are applied *to an existing cut*, not chosen from a global setting —
  i.e., "this cut gets a crossfade" is a property of the cut, not the project.

None of this is achievable (or desirable) to fully clone — Theo Bramwell's own persona
brief is explicit about this: *"Do not turn this into a miniature professional NLE... The
goal is not to reproduce every editing application feature."* The useful takeaway isn't
the feature list, it's the **anatomy**: preview + timeline + trim handles + a small tool
vocabulary, with transitions as a per-cut property.

### Mobile editors (CapCut, VN, LumaFusion, DaVinci Resolve for iPad)

- Layout inverts for a portrait screen: **preview on top** (large, fixed), **timeline
  below** (horizontally scrollable, pinch-to-zoom to change timeline scale).
- Selecting a clip shows a **bold highlight + large drag handles** at its edges — the
  direct touch equivalent of a desktop trim handle, sized for a fingertip not a mouse
  pointer.
- A **compact icon toolbar** above or below the timeline (split, delete, speed, volume,
  text, filter) replaces the desktop's many docked panels.
- Track affordances (hide/lock/mute) shrink to small per-track icons, not a full panel.
- Crucially: **even professional touch NLEs scope down deliberately.** DaVinci Resolve for
  iPad ships only the Cut and Color pages — Fusion (motion graphics) and Fairlight (audio
  mixing) are left out entirely, not simplified. A touch professional tool's answer to
  "too many features for this screen" is *remove features*, not cram them in smaller.
  That's direct license to keep Antiquary's mobile editor scoped to what Theo's brief
  already prioritizes (trim, reorder, cut timing, transition swap) and not chase parity
  with desktop on a phone screen.

### Browser-based editors (Kapwing, Clipchamp) — the closest real analogue

These are the only category actually built the same way Antiquary is: a web app, no
install, running against media the browser doesn't natively own.
- The timeline **only appears once media is on it** — an empty/loading state matters.
- Both do **client-side preview compositing** (playing/scrubbing existing media files
  directly in the browser) and reserve server-side processing for the final export — they
  don't round-trip to a server on every scrub or trim.
- Both are explicitly scoped to **short-form/social content**, not professional long-form
  work — the same scope Antiquary's 30-45s vertical videos sit in. Reported weak points
  for both are performance on longer projects and timeline reliability — a caution to keep
  our own timeline model simple (small clip counts, short durations) rather than assuming
  it'll scale to timelines it was never designed for.

### Touch-friendly timeline mechanics (cross-cutting)

Independent of which app: a selected clip gets a visibly distinct highlight with large
(comfortable tap-target, not a 6px desktop-style handle) trim handles; horizontal
scrolling uses native scroll-snap rather than custom drag math where possible; pinch
gestures re-scale the timeline's zoom level; drag-to-reorder and trim-drag must not fight
each other (a real, named problem in every one of these apps' own UX writing).

## 2. What this means for Antiquary specifically

Three real constraints shape the plan, all already true of this codebase:

1. **This is a responsive web app, not native.** The right reference class is
   Kapwing/Clipchamp's architecture (client-composited preview, server-side final render),
   informed by CapCut/VN/LumaFusion's *touch interaction patterns* (trim handles, pinch
   zoom, compact toolbar) for the mobile breakpoint, and by desktop NLEs' *vocabulary*
   (trim/split/reorder/transition-per-cut) for what operations actually need to exist —
   not any one app's literal layout.
2. **Per-clip assets already exist and are durable.** `pipeline/enqueue_story.py` already
   uploads each beat's visual + audio clip to MinIO as its own object
   (`stories/<user>/<story>/clips/...`), which `render_timeline.py` reads to do a real
   server-side re-render. This is the single biggest asset this roadmap gets to build on:
   **a scrubbable preview doesn't need ffmpeg at all.** The browser can play/seek the
   individual clip files directly (a sequence of `<video>` elements, or one that swaps
   `src` at cut boundaries) to fake a real timeline preview client-side — exactly what
   Kapwing/Clipchamp do — while the actual burned-in-caption, graded, transitioned final
   output stays a real ffmpeg job, triggered explicitly, not on every edit.
3. **The current model (edit → immediately persist → explicit re-render) is close, but
   the audit already flagged the risk of scaling it up naively**: OPEN_ISSUES.md #28 notes
   that "Re-render" has no confirmation despite overwriting the currently-eligible video
   for everyone. Once there are five or six kinds of structural edit instead of one
   (caption text), that risk compounds — a user could rack up several trims/reorders and
   only realize the re-render overwrites the approved video with no way back. This
   roadmap's phases below build in a deliberate **staged-edit model** to address that: edits
   accumulate in `Story.timeline` (cheap, already durable, no ffmpeg) with a clear
   "unsaved re-render" indicator, and only an explicit, confirmed action produces a new
   video — closing #28 as a side effect of doing this properly, not as an afterthought.

## 3. The roadmap

Each phase is a real vertical slice (schema → service → route → frontend), verified
against the real local stack before moving to the next, matching how every previous phase
of this project has been built. Theo Bramwell reviews each phase's *editorial* correctness
(are these the controls an editor actually reaches for); Ines Torres + Naomi Park review
the desktop/mobile UI; Tomasz Kowalski reviews the render/concurrency implications.

### Phase B.1 — Scrubbable preview player (the real prerequisite)

Nothing below is reviewable without this. Replace the static clip-list view with an actual
preview: a canvas or stacked `<video>` elements that play/seek through the story's clips in
order, driven by a real playhead/scrubber synced to elapsed time across all clips (not per-
clip). This is client-side only — no new backend route. This is what turns "a list of rows"
into "something you can watch and scrub," which every single reference app treats as
non-negotiable table stakes.

**Verification**: open the editor for a real story, scrub the timeline, confirm the preview
frame matches the expected clip at that timestamp, at both a desktop and a mobile viewport
width.

### Phase B.2 — Trim (in/out points)

Selecting a visual clip reveals drag handles at its start/end (desktop: thin handles with
a mouse cursor affordance; mobile: larger tap targets, per the touch research above).
Dragging an edge sets a new in/out point, previewed instantly against the client-side
player from B.1 — no server round-trip to see the effect. Persisting a trim writes new
`start`/`end`/`duration` values onto that clip's timeline entry (staged, not yet
re-rendered). Minimum-duration guard (don't let a trim collapse a clip to near-zero).

**Verification**: trim a real clip shorter, confirm the preview reflects it immediately,
save, re-render, confirm the actual output video is shorter at that cut.

### Phase B.3 — Reorder

Drag-and-drop to change clip order in the visual track (desktop: mouse drag with a drop
indicator; mobile: long-press then drag, matching the platform-native pattern). Captions
and narration audio are tied to their *content*, not raw position — reordering the visual
track alone (leaving narration/caption order fixed) is likely wrong for this pipeline's
model, since visuals are sourced per-beat-of-narration; this needs a real product decision
(see open question in §4) before this phase starts, not an assumption.

### Phase B.4 — Split and delete

A razor/split operation at the current playhead position, and delete-with-ripple (removing
a clip closes the gap rather than leaving dead air) — the two most basic operations in
every NLE's tool vocabulary, absent today entirely.

### Phase B.5 — Transition control per cut

Expose `render.py`'s existing transition selection (`_transition_style()` — currently fully
automatic) as a per-cut, human-overridable choice: hard cut / crossfade / accent. Directly
implements Theo's brief ("swapping the transition at a cut, removing a transition") and
gives a human the override that audit #34 (same-`entity_type`-treated-as-same-subject) says
is currently missing entirely.

### Phase B.6 — Clip swap (manual re-source)

A "replace this clip" action — re-run the existing stock-visual search with an edited query,
or (once the media-library work in OPEN_ISSUES.md #21 phase 3 lands) pick from a user's own
uploaded assets. Manual swap (a human picking a specific alternative) belongs here, in the
structural editor; *automatic* AI-assisted re-search/rewrite is #4/Phase C's territory and
stays there — this phase only wires up the mechanism, not the automation.

### Phase B.7 — Staged edits, explicit save/re-render, and Undo

This is the architectural piece that makes B.2-B.6 safe to ship rather than a liability:
- Every structural edit above writes to `Story.timeline` as a **draft** (already
  persistable today — no schema change), with the frontend showing a clear "unsaved
  changes — re-render to apply" state rather than each edit silently being live.
- "Re-render" gets the confirm dialog audit #27/#28 asked for, following the app's own
  existing rule (confirm when an action discards in-progress work or affects the
  currently-eligible-for-everyone video) — and every edit gets a real Undo via the same
  toast pattern already used everywhere else in the app (audit #27).
- This phase is also where `render_timeline.py`'s "full-timeline-only" limitation gets
  revisited: even a partial improvement (skip ffmpeg work for clips whose timing/content
  didn't change since the last render) meaningfully cuts re-render cost as the number of
  small edits grows.

### Phase B.8 — Mobile/responsive pass

Close audit #30 (zero mobile media queries on `Editor.jsx`) and #31 (30×30px player
controls under the touch-target minimum) as part of this work, not separately — the
touch-specific trim-handle sizing, pinch-to-zoom timeline, and compact toolbar from the
mobile-editor research above are exactly what this pass implements. Should land once B.1-
B.4 exist on desktop, so there's a real editor to make responsive rather than a moving
target.

## 4. Open questions to settle before B.1 starts

Real product/technical decisions, not implementation details — flagging rather than
guessing:

1. **Client-side preview mechanism**: sequential `<video>` element swapping (simplest, but
   a visible stutter at cut boundaries is likely) vs. a canvas + `requestVideoFrameCallback`
   approach (smoother, more code) vs. accepting the stutter for v1 and revisiting only if
   it's actually distracting in practice. Recommend starting with the simplest sequential
   `<video>` approach and only investing in canvas compositing if real use shows the cut
   stutter matters — consistent with this project's "verify before adding complexity" habit.
2. **Reorder scope**: does reordering the visual track imply reordering narration/captions
   too (i.e., restructuring the story), or is visual-only reorder (re-pairing an existing
   visual to a different beat's audio) the actual use case? These are different features
   with different complexity — needs a real answer before B.3, not an assumption baked into
   the data model.
3. **No new npm dependency, per standing rule** — everything above is scoped to be buildable
   with native browser APIs (`<video>`, drag events, touch events) and the existing React/
   CSS setup. If B.1's preview approach genuinely needs a library (e.g. a waveform
   renderer for the audio track), that's a real, explicit exception to raise at the time,
   not something to reach for by default.

## Sources consulted

- [Premiere Pro interface guide — Adobe](https://helpx.adobe.com/premiere-pro/desktop/get-started/source-and-program-monitor-adjustments/about-source-monitor-and-program-monitor.html)
- [Timeline Panel in Premiere Pro, explained — Filmit.io](https://filmit.io/blog/timeline-panel-premiere-pro-explained-for-editors)
- [DaVinci Resolve Interface and Pages — 2 Pop](https://2pop.calarts.edu/technicalsupport/davinci-resolve-interface/)
- [DaVinci Resolve for iPad review — TechRadar](https://www.techradar.com/pro/software-services/davinci-resolve-for-ipad-review)
- [DaVinci Resolve for iPad — complete review — Film Editing Pro](https://www.filmeditingpro.com/davinci-resolve-for-ipad-complete-review-testing/)
- [CapCut UI guide — timeline, tools, panels — Websiteseostats](https://websiteseostats.com/capcut-ui-a-complete-guide-to-the-capcut-user-interface-editing-timeline-tools-panels-templates-and-creative-workflow/)
- [Master CapCut Timeline Settings — Filmora/Wondershare](https://filmora.wondershare.com/advanced-video-editing/capcut-timeline.html)
- [CapCut vs VN vs LumaFusion — Beverly Boy](https://beverlyboy.com/film-technology/capcut-vs-vn-vs-lumafusion-the-best-mobile-editor-for-beginners/)
- [5 video editor apps ranked (CapCut/InShot/VN/Splice/LumaFusion) — Unstar](https://unstar.app/blog/capcut-inshot-vn-splice-lumafusion-video-editing-apps-ranked-2026)
- [LumaFusion review 2026 — AI Chat Daily](https://www.aichatdaily.com/tools/lumafusion)
- [Clipchamp vs Kapwing — SelectHub](https://www.selecthub.com/video-editing-software/clipchamp-vs-kapwing/)
- [How to edit video with Kapwing — Envato Tuts+](https://photography.tutsplus.com/tutorials/how-to-edit-a-video-with-kapwing--cms-39115)
- [Designing a timeline for mobile video editing — img.ly](https://img.ly/blog/designing-a-timeline-for-mobile-video-editing/)
- [Timeline UI design patterns — Eleken](https://www.eleken.co/blog-posts/timeline-ui-design)

## Relationship to existing tracking

This roadmap replaces the vague "Phase B" reference in OPEN_ISSUES.md #3/#4/#5 with the
concrete phases above. See OPEN_ISSUES.md for status tracking as each phase lands — this
file is the plan, not the status log, matching the split this project already uses between
`PERSONAS.md` (who) and `OPEN_ISSUES.md` (current state).
