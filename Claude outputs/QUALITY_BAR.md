# The quality bar — Marcus Webb + Theo Bramwell

This is the rubric a generated video gets checked against — not "does it look good," a
concrete checklist a Creative Director and a Video Editor would actually use. Every real
verification generation gets an explicit pass through this list logged in
`OPEN_ISSUES.md` alongside whatever specific feature was being tested. A video can pass
every feature-level test (captions render, transitions fire, the timeline overlay
appears) and still fail this — that gap is exactly why this file exists.

## The one question underneath all of it

Would this read as a deliberate choice a documentary editor made on purpose, or does it
read as something a pipeline produced? Everything below is that question broken into
checkable parts.

## Marcus's checklist (does it *look* like a documentary)

- [ ] No beat sits on an obviously-wrong or generic stock visual that a real editor
      would have rejected (a placeholder firing is fine occasionally; a placeholder
      firing because a query was badly formed is not).
- [ ] The Ken Burns pan/zoom direction varies across the piece — not the same direction
      on every single beat.
- [ ] Transition choices actually track the entity-type logic (same-subject continuity
      vs. a genuine subject change vs. the sparing person/place accent) — spot-check at
      least two cuts against the actual beat sequence to confirm the mechanism is
      entity-type-driven, don't just trust that an xfade filter executed without error.
- [ ] Color grade/vignette/grain read as a deliberate treatment, not as a filter left on
      by default — does the piece have a consistent "look," or does it look untreated.
- [ ] Any motion graphic (timeline marker, future map/stat callout) appears at a moment
      that actually earns it, holds long enough to read, and disappears cleanly — not
      mistimed, not overstaying.
- [ ] The animated-placeholder fallback (when it fires) reads as a deliberate abstract
      backdrop, not as "the video broke here."

## Theo's checklist (does it *cut* like a documentary)

- [ ] Cut points land on natural pauses in the narration, not mid-word or mid-phrase.
- [ ] Pacing varies across the piece — the hook doesn't move at the same speed as the
      close; not everything is cut to the same rhythm throughout.
- [ ] No beat is so short the cut feels like a glitch, and none is so long it feels like
      the pipeline forgot to cut.
- [ ] Watching straight through, no single moment makes you think "that was clearly
      automated" — if one does, name the exact timestamp and why.

## Sam's checklist (do the captions read like a real documentary's captions)

- [ ] Legible against the busiest footage in the piece, not just the calmest frame.
- [ ] No line overflows or wraps awkwardly.
- [ ] Emphasis coloring is used on genuinely notable words, not so often it stops
      meaning anything.

## Dana's checklist (does the audio hold up)

- [ ] Narration is always the clearest thing in the mix — music/SFX never fight it.
- [ ] Voice delivery doesn't sound flat/robotic through the whole piece — real prosody
      variation across the hook/body/close.
- [ ] Music (when present) is ducked correctly and doesn't have an audible hard cut in
      or out.

## How to use this

After any real verification generation, actually watch it (or extract and review enough
frames across its full length, not just the beat under test), go through every box
above, and write the verdict into `OPEN_ISSUES.md` — including the boxes that fail, in
plain language, with the exact timestamp/beat where they fail. A rubric nobody actually
runs is decoration; the point is a written verdict every time, pass or fail.
