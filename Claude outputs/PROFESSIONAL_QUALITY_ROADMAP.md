# Professional Video Quality Roadmap

Research and planning only — **no implementation in this document**, per explicit
instruction. This is Phase 1-7 of the requested process: research real film/video
production principles, define a professional quality bar, honestly audit our current
pipeline against it, design the production pipeline and creative north star, and lay out
a prioritized (but not-yet-executed) roadmap plus a repeatable quality-control system.

---

## 0. A framing point that shapes everything below

Antiquary does not generate video frames with a diffusion/video model (no Sora/Veo/Runway
in this pipeline — see `CLAUDE.md`'s reasoning on why: cost, and this project's own choice
to stay deterministic/inspectable). It **composites real, sourced stock photos and video
clips** (Wikidata portraits, Wikimedia Commons, Pexels) with **real TTS narration**
(edge-tts), **real transcribed captions** (faster-whisper), and **real ffmpeg editing**
(Ken Burns pan/zoom, crossfades, color grade, motion graphics) — see
`docs/ARCHITECTURE.md` and `pipeline/`.

This matters for which research applies. Most of what's written about "why AI video looks
fake" (hand deformities, morphing, temporal-consistency flicker, impossible physics — see
§1.6 below) describes a **different failure mode**: a generative model hallucinating
pixels frame-by-frame. That's not our problem — we don't generate pixels, we select and
edit real ones. **Our actual failure mode is closer to "amateur stock-footage YouTube
slideshow" than "AI video artifact."** The professional-filmmaking research that transfers
directly is: shot/asset *selection* quality (standing in for cinematography, since we
don't control a camera), color grading *consistency across disparate sources* (standing
in for on-set lighting consistency), edit rhythm and motivation (fully applicable — this
is real editing, done in code), sound design depth (fully applicable), and typography/
motion-graphics restraint (fully applicable). Keeping this distinction explicit throughout
is what keeps this roadmap from prescribing fixes (camera lens choice, blocking actors)
that don't actually apply to a footage-compositing pipeline.

---

## 1. Research findings

### 1.1 Cinematography (composition, lighting, lensing, camera movement)

- **Three-point lighting (key/fill/rim)** is the foundational lighting vocabulary: key
  light shapes the subject, fill controls shadow density (a 2:1 key:fill ratio is a common
  baseline, tighter like 1.5:1 for a brighter commercial look), and a rim/back light
  separates subject from background for a sense of depth.
  ([StudioBinder](https://www.studiobinder.com/blog/three-point-lighting-setup/))
- **Motivated lighting**: professional DPs build the key light to match a *logical* source
  already implied by the scene (a window, a lamp) rather than lighting for exposure alone —
  light that doesn't come from somewhere reads as artificial.
  ([ASMR Education](https://asmr.education/faq/video-production/three-point-lighting-cinematography-guide))
- **Composition**: rule of thirds, leading lines, and depth-of-field control are the core
  tools for directing attention and establishing a subject's relationship to its
  environment; lens/focal-length choice directly determines how much of the frame is in
  focus and therefore what reads as "important."
  ([StudioBinder — shot composition](https://www.studiobinder.com/blog/rules-of-shot-composition-in-film/),
  [Motion Array](https://motionarray.com/learn/filmmaking/shot-composition-framing-rules/))
- **Motivated camera movement**: "A camera move that isn't motivated by the blocking is
  just the camera announcing itself" — movement should ride an actor's action or a
  narrative beat, not exist for its own sake.
  ([LensVid](https://lensvid.com/technique/tips-motivated-unmotivated-camera-movement/))
- **Depth staging**: staging subjects across depth (not just side-to-side) lets a single
  camera move reframe between subjects and reads as more cinematic than flat blocking.
  ([Clapboard](https://www.clapboard.com/blog/directing/film-theory/blocking-staging-filmmaking-guide),
  [StillsLab](https://stillslab.com/news/how-to-block-a-scene-for-the-camera))

### 1.2 Production design & visual world

Consistency of palette, texture, and environmental detail across a production is what
makes disparate shots read as "the same world." The literature here is mostly about
physical sets/props/wardrobe, which doesn't map onto our pipeline directly (we don't build
sets) — but the underlying principle, **visual consistency across every shot the viewer
sees in sequence**, maps directly onto our biggest actual gap: we source clips from three
unrelated origins (Wikidata portraits, Commons scans, Pexels stock) with wildly different
color science, grain, and quality, and currently apply only a single fixed grade on top,
not a true *unifying* correction per source.

### 1.3 Editing (Walter Murch, documentary structure, B-roll)

- **Walter Murch's "Rule of Six"** (*In the Blink of an Eye*) ranks what makes a cut work,
  in priority order: **Emotion (51%)**, Story (23%), Rhythm (10%), Eye-trace, two-
  dimensional plane of screen, three-dimensional space of action (the last three sum to
  16%). Technical continuity is deliberately *last* — "a cut can violate spatial
  continuity, temporal continuity, and rhythmic convention and still work if it is
  emotionally true, but a cut that is technically perfect but emotionally false will
  always feel wrong."
  ([StudioBinder — Rule of Six](https://www.studiobinder.com/blog/walter-murch-rule-of-six/),
  [PremiumBeat](https://www.premiumbeat.com/blog/cutting-on-the-blink-editing-tips-from-walter-murch/))
- **A cut should feel like a blink** — a natural pause in thought, not an arbitrary
  duration expiring. This is the exact principle Theo Bramwell's persona brief
  (`Claude outputs/personas/theo-bramwell.md`) already encodes as "Cut timing comes from
  content, not arithmetic."
- **Documentary B-roll structure**: professional editors work a "two-layer" pass — first
  the emotional target of each moment, then which B-roll image best expresses or
  *contrasts* that feeling; B-roll paces a story by giving information time to settle
  rather than cutting on every beat. A **horizontal axis** (overall pacing/flow) and
  **vertical axis** (precise sync between a specific word/phrase and a specific image) are
  both actively managed, not left to a flat formula.
  ([Inside the Edit](https://www.insidetheedit.com/blog/b-roll-editing-structure))
- **Short-form/vertical retention mechanics** (directly relevant — this is literally our
  format): 50-60% of viewer drop-off happens in the first 3 seconds, so the hook must be
  immediate; captions are close to mandatory since much viewing is sound-off; a "pattern
  interrupt" (sudden sound, quick zoom, unexpected movement) is a named, deliberate
  technique for holding attention, not just "more cuts."
  ([JoinBrands](https://joinbrands.com/blog/youtube-shorts-best-practices/),
  [Schedulala](https://schedulala.com/blog/youtube-shorts-editing-tips-pro-techniques))

### 1.4 Color

- **Correction before grading, always**: color correction (white balance, exposure,
  skin-tone accuracy) is a technical fix; grading is the creative pass on top. Applying a
  creative LUT to uncorrected footage *amplifies* the underlying problems instead of
  adding style — order matters.
  ([Dehancer](https://www.dehancer.com/learn/article/color-grading-color-correction-a-practical-guide-for-beginners))
- **Skin tones are the single highest-scrutiny element** of any grade, because human
  perception is finely tuned to faces — LUTs commonly shift skin toward orange/magenta,
  and correcting that via secondary HSL work is "what separates 'okay' grades from
  professional ones."
  ([Colorby AI](https://colorby.ai/post/cinematic-luts-and-skin-tone-preservation-in-grading-18c4b2ee))
- **Film emulation** (matching a Kodak/Fuji stock's contrast curve, halation, grain, gate
  weave) is a deliberate technique for a "shot on film" look — distinct from just adding
  grain, which is what our pipeline currently does.
  ([Envato Elements](https://elements.envato.com/learn/color-grading-vs-luts-what-is-the-difference))

### 1.5 Sound

- **Six co-equal layers**, not one music bed: dialogue/narration (the spine), Foley
  (tactile realism), production/ambient sound (scene glue — traffic, room tone, wind),
  designed sound effects (invisible glue that guides attention), and music (the emotional
  map). A professional mix is a *layered* construction, not narration-plus-one-track.
  ([Krotos Studio](https://krotos.studio/blog/film-sound-design))
- **Ambience specifically** is called out as foundational-but-invisible: a scene with zero
  room tone/environmental texture reads as sterile even if dialogue and music are both
  present and well-mixed.
- **Workflow**: spot (identify priority moments) → source/create → layer (primary sound
  front, supporting texture beneath) → temp mix → final pass. Nothing in our current
  pipeline does anything resembling "spotting" — sourcing is entirely automatic and
  undifferentiated (see §3).
- **Loudness targets are a real, checkable technical standard**, not a matter of taste:
  YouTube normalizes to ≈-14 LUFS integrated; broadcast (EBU R128) targets -23 LUFS; a mix
  with real dynamic range (a healthy LRA, not everything slammed to one level) reads as
  more "produced" than a heavily limited, flat one.
  ([Sweetwater](https://www.sweetwater.com/insync/loudness-standards-lufs-peaks-and-streaming-limits/),
  [Bobby Owsinski](https://bobbyowsinskiblog.com/lufs-standards/))

### 1.6 Why AI-generated video specifically looks fake (and why most of it doesn't apply here)

Documented causes for *generative*-video artifacts: weak temporal consistency (no true
physics simulation, so frame-to-frame flicker/drift), hand/limb deformities from
diffusion models struggling with complex overlapping geometry, "waxy" over-smoothed skin
from aggressive denoising, and object permanence failures (objects re-estimated each
frame instead of tracked).
([Atlabs AI](https://www.atlabs.ai/blog/why-your-ai-videos-look-fake-(and-how-to-fix-them-step-by-step)))
As stated in §0, **none of this is our pipeline's failure mode** — we don't generate
frames. The one transferable idea: the **uncanny valley** effect (a photorealistic result
that's 95% right trips harder than something 60% right, because the viewer's brain expects
"real" and catches the missing 5%) has an analogue in our world: a documentary-style
narration+caption+grade package that's *almost* professional but has one identifiably
"off" element (a robotic TTS cadence, a mismatched stock clip, a caption font swap
mid-video) reads as more obviously synthetic than a rougher, more consistently-executed
package would — consistency of execution matters more than any single element's peak
quality.

### 1.7 Explainer-video genre reference (Kurzgesagt) — the closest real comparable

Kurzgesagt is explicitly cited as this project's own aspirational reference
(`pipeline/motion_graphics.py`'s docstring already says so). Their actual method: 2D
motion graphics trading photorealism for *clarity* — simple, consistent visual metaphors
built in After Expressions/expressions-driven animation, not literal footage.
([Kurzgesagt on Skillshare](https://www.skillshare.com/en/classes/motion-graphics-with-kurzgesagt-part-1/631970755))
The honest implication for Antiquary: our current approach (real stock photos/footage +
Ken Burns) is chasing photorealistic documentary credibility, which is a *harder* bar to
hit consistently with automatically-sourced assets of variable quality, than a
motion-graphics-forward approach that owns its illustrated/stylized nature the way
Kurzgesagt does. This is a real strategic fork worth the user's explicit input later (see
§7's open question), not a decision to make silently here.

---

## 2. Reference materials (consolidated)

| Domain | Source |
|---|---|
| Three-point lighting | [StudioBinder](https://www.studiobinder.com/blog/three-point-lighting-setup/), [MasterClass](https://www.masterclass.com/articles/what-is-three-point-lighting-learn-about-the-lighting-technique-and-tips-for-the-best-three-point-lighting-setups) |
| Composition/lensing | [StudioBinder](https://www.studiobinder.com/blog/rules-of-shot-composition-in-film/), [Motion Array](https://motionarray.com/learn/filmmaking/shot-composition-framing-rules/) |
| Camera movement/blocking | [LensVid](https://lensvid.com/technique/tips-motivated-unmotivated-camera-movement/), [Clapboard](https://www.clapboard.com/blog/directing/film-theory/blocking-staging-filmmaking-guide) |
| Editing (Murch) | [StudioBinder — Rule of Six](https://www.studiobinder.com/blog/walter-murch-rule-of-six/), [PremiumBeat](https://www.premiumbeat.com/blog/cutting-on-the-blink-editing-tips-from-walter-murch/) |
| Documentary B-roll structure | [Inside the Edit](https://www.insidetheedit.com/blog/b-roll-editing-structure), [PremiumBeat](https://www.premiumbeat.com/blog/b-roll-video-edit-guide/) |
| Color correction vs. grading | [Dehancer](https://www.dehancer.com/learn/article/color-grading-color-correction-a-practical-guide-for-beginners), [Colorby AI (skin tones)](https://colorby.ai/post/cinematic-luts-and-skin-tone-preservation-in-grading-18c4b2ee) |
| Sound design layering | [Krotos Studio](https://krotos.studio/blog/film-sound-design), [C&I Studios](https://c-istudios.com/balancing-dialogue-music-and-sound-effects-audio-mixing-techniques-for-film-and-video/) |
| Loudness standards | [Sweetwater](https://www.sweetwater.com/insync/loudness-standards-lufs-peaks-and-streaming-limits/), [Owsinski](https://bobbyowsinskiblog.com/lufs-standards/) |
| Why AI video looks fake | [Atlabs AI](https://www.atlabs.ai/blog/why-your-ai-videos-look-fake-(and-how-to-fix-them-step-by-step)) |
| Short-form retention | [JoinBrands](https://joinbrands.com/blog/youtube-shorts-best-practices/), [Schedulala](https://schedulala.com/blog/youtube-shorts-editing-tips-pro-techniques) |
| Kurzgesagt / explainer motion graphics | [Skillshare](https://www.skillshare.com/en/classes/motion-graphics-with-kurzgesagt-part-1/631970755), [Kinetic typography — Wikipedia](https://en.wikipedia.org/wiki/Kinetic_typography) |
| TTS/prosody state of the art | [BentoML — open-source TTS 2026](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models) |

---

## 3. Professional-quality principles → a concrete bar for Antiquary

Translating the research into criteria specific to what our pipeline actually controls
(sourced-asset selection and treatment, not original cinematography):

| Dimension | What "excellent" means here |
|---|---|
| **Visual consistency** | Every sourced clip in one video reads as belonging to the same "world" after grading — not necessarily the same literal color, but a consistent contrast curve, grain amount, and color temperature bias applied *per-source* before the shared final grade. |
| **Composition (via sourcing + crop)** | The subject (a detected face, a named landmark) sits on a rule-of-thirds point after crop/Ken Burns framing, not blind center-crop. |
| **Realism** | No jarring mismatch between narration content and visual content (the chipmunk-footage failure in OPEN_ISSUES.md #23 is the canonical example of this bar being missed). |
| **Editing rhythm** | Shot durations vary with content (a punchy hook beat is shorter, a reveal holds longer), not `total_duration / n`. Transitions are chosen for a *reason* (same-subject continuity vs. hard subject change), not applied uniformly. |
| **Color** | Correction (skin/neutral-tone normalization per source) happens before the shared creative grade; skin tones specifically checked. |
| **Sound** | At minimum three real layers present and distinguishable on playback: narration, music (with in *and* out fades), and at least occasional sound design accents (a whoosh on a motion-graphic reveal) — not narration + one static music bed. |
| **Music/audio technical** | Final mix lands near -14 LUFS integrated (YouTube's own normalization target) with real, audible dynamic range, not everything slammed flat. |
| **Motion graphics** | On-screen only when it adds real information (a date, a stat); gone the instant its point is made; never a stock template look. |
| **Typography/captions** | Legible against any background (a real safe-area treatment, not just color), emphasis reserved for genuinely surprising words, not applied to the hook line as often as everywhere else. |
| **Storytelling/pacing** | A felt arc (hook → build → payoff → release), not uniform intensity start-to-finish. |
| **Technical** | No clipped audio, no visibly banded gradients, no truncated/garbled captions, no motion-graphic artifacts (the exact class of bug just fixed in `motion_graphics.py`). |
| **Overall emotional impact** | A viewer's honest answer to "did this feel made, or generated?" is "made." |

---

## 4. Honest analysis of current shortcomings

Grounded in the actual pipeline (`pipeline/generate_script.py`, `fetch_visuals.py`,
`tts.py`, `captions.py`, `render.py`, `motion_graphics.py`), not a generic list. Several of
these are already independently tracked in `Claude outputs/OPEN_ISSUES.md` from the
9/12 team audit — cited by number where they overlap, since this roadmap should extend
that tracking, not duplicate it silently.

1. **Visual sourcing has no cross-clip consistency pass.** Each beat's image/clip is
   fetched independently from Wikidata/Commons/Pexels with no shared color treatment
   before the single final grade — three different cameras/scanners/eras of source
   material, visually. This is the single biggest "doesn't feel like one production"
   cause, and nothing in the pipeline addresses it today.
2. **Cut timing is still substantially duration-driven, not content-driven** — beat
   duration comes from TTS length, and while beats now exist as a semantic unit (a real
   improvement over flat division), nothing merges an accidentally-short beat or holds an
   accidentally-important one longer (audit #38: "no floor/ceiling on a beat's actual
   rendered duration"). Murch's "rhythm from emotion" principle has no mechanism to act on
   here at all — durations are a byproduct of narration length, never a directorial choice.
3. **Sourcing mismatches are a real, demonstrated failure mode**, not theoretical — the
   Rosetta Stone generation's chipmunk-footage beat (OPEN_ISSUES.md #23) is a concrete,
   already-documented instance of exactly the "AI slideshow" feel this whole task is about.
4. **Sound is one music bed, not a layered mix.** No Foley, no ambient bed, no sound
   design accents — the single most-cited "what separates professional from amateur"
   element in the research (§1.5) is almost entirely absent. (Partially tracked as
   OPEN_ISSUES.md #18, scoped but not started.)
5. **Prosody variation is two discrete presets** (hook/closer), not a real curve across
   the piece (audit #41) — every mid-video beat delivers identically regardless of its
   actual emotional content.
6. **Transitions are chosen by a proxy (`entity_type` match) that isn't the actual claim**
   (audit #34) — a Caesar→Brutus subject change gets treated as continuous. This is
   exactly the "cut motivated by nothing real" failure Murch's research warns against.
7. **Color grade is a single fixed pass**, not correction-then-grade — no skin-tone-aware
   secondary work, no per-source correction, despite skin tones being flagged as the
   single highest-scrutiny grading element in the research (relevant here since a large
   fraction of "person" beats are named-figure portraits).
8. **Motion graphics font doesn't match caption font** (audit #33) — a small but real
   "type system" inconsistency of exactly the kind that breaks the "one considered
   production" feeling.
9. **No music fade-in** (audit #40, now fixed this session) and **the underline-width
   ffmpeg bug** (now fixed this session) were both real, previously-invisible technical
   defects undermining the "polished" bar even when the design intent was already correct
   on paper.
10. **The visual-vs-narration-vocabulary genre question is unresolved** (§1.7): the
    pipeline is attempting photorealistic-documentary credibility with automatically
    sourced, uncontrollable-quality stock assets — arguably a harder bar to hit
    consistently than a more motion-graphics-forward, illustrated approach would be. This
    isn't a bug, it's an open strategic question worth surfacing (§7) rather than deciding
    unilaterally here.

---

## 5. Target creative direction (the north star)

Not "make the AI video look better" — the bar is: **a viewer with no context should
plausibly mistake this for a short-form documentary segment made by a small, competent
production team (the tier of quality behind channels like Real Engineering, Extra
History, or a History Channel digital short), not an automated slideshow.** Concretely,
for this project's specific 30-45s vertical historical-story format:

- **Visual style**: real historical imagery, graded into one cohesive, slightly desaturated
  "archival-but-alive" palette (not each source's native color), consistent grain/contrast
  across every clip in a single video.
- **Cinematography (via sourcing/framing)**: named subjects framed on a rule-of-thirds
  point via face-aware crop, not blind center-crop; Ken Burns direction/rate chosen with
  intent (push in on a reveal, drift on a establishing beat), not alternating in/out by
  parity.
- **Editing**: shot duration varies with content — a hook beat is quick, a reveal beat
  holds; transitions are hard cuts by default, crossfades reserved for genuine subject
  continuity, exactly one accent transition per video at most, used only where it's
  earned.
- **Color**: corrected-then-graded, skin tones checked, one consistent look across every
  sourced clip.
- **Sound**: narration + music (faded in and out) + occasional, restrained sound-design
  accents (a soft whoosh on a motion-graphic reveal) + a very low ambient bed to avoid dead
  silence between narration phrases; mix lands near -14 LUFS with real dynamic range.
- **Music**: mood-matched (not just "documentary" as a single bucket), ducked cleanly,
  faded both ways.
- **Pacing**: a felt arc — hook, build, a specific reveal beat that's allowed to breathe,
  a closing beat that isn't rushed.
- **Storytelling**: the visual choice for each beat is *motivated* by that beat's specific
  content (a named person's portrait, a named place, an actual event image), never a
  generic scene filler standing in for something the sourcing couldn't find, without at
  least a deliberate, good-looking fallback (the animated placeholder, already shipped).
- **Graphics**: on-screen only when it adds real information, gone the instant its point
  lands, in the same typeface as the captions.
- **Realism**: zero visibly wrong footage-to-narration matches (no more chipmunks).
- **Emotional impact**: the viewer should feel like they learned a specific, surprising
  true story from someone who cared about telling it well — not that they watched a
  topic get automatically illustrated.

---

## 6. Proposed production pipeline (mapped to what we actually have)

| Stage | What should happen | Antiquary's actual mechanism today | Gap |
|---|---|---|---|
| **Concept → Script** | A specific, surprising, fact-checked narrative beat structure | `generate_script.py` (Ollama writer + fact-check pass) | Solid; the fact-check discipline is already a real strength here. |
| **Storyboard / Shot list** | Each narrative beat mapped to a specific visual intent (subject, framing, mood) | `beats` (`text`, `visual_query`, `entity_type`) | Real but thin — no framing/mood intent captured per beat, only a search query. |
| **Visual references / Camera-composition planning** | Reference imagery pre-vetted for quality/relevance before committing | `fetch_visuals.py`'s live waterfall search (Wikidata→Commons→Pexels→placeholder) | No pre-vetting; first-past-filter result is used; no relevance scoring (audit finding, pipeline section). |
| **Generation/Production** | N/A for us (no frame generation) — this stage *is* asset sourcing | Same as above | — |
| **Asset selection** | Best-of-several-candidates chosen per beat, face/composition-aware | Currently: first result that passes a size/MIME filter, no comparison between candidates | Real gap — no scoring step exists at all today. |
| **Editing** | Content-motivated cut timing, deliberate transition choice | `render.py`: beat-duration-driven clip length, `_transition_style()` keyed on `entity_type` match | Partially real (beats are semantic units now), but duration itself is still a TTS-length byproduct, and transition choice is a proxy, not the real claim (audit #34). |
| **Sound design** | Layered: narration, ambience, designed SFX, music — spotted per beat | `tts.py` + one music bed (`render.py`) | Real gap — no ambience layer, no SFX layer at all (#18, scoped, not started). |
| **Music** | Mood-matched, ducked, faded both ways | One "documentary" bucket, 5 tracks, ducked (now with a fade-in, fixed this session) | Real but shallow — one mood bucket regardless of story tone. |
| **Color** | Per-source correction, then one shared creative grade | One fixed `eq`/`curves` grade + vignette + grain applied uniformly | Real gap — no per-source correction step exists. |
| **Motion graphics/VFX** | Information-triggered, restrained, type-matched to captions | `motion_graphics.py`'s year/timeline marker (v1, now working correctly) | Narrow but genuinely working; font mismatch with captions still open (audit #33). |
| **Quality control** | A systematic pass against a defined bar before anything is called done | `Claude outputs/QUALITY_BAR.md` (created this session, used once) | Real process now exists; needs to become a genuine standing habit, and this roadmap's §9 below extends it. |
| **Final export** | Consistent technical delivery (loudness, resolution, format) | `render.py`'s fixed x264/AAC output | Solid; no loudness-normalization pass currently, worth adding as a cheap technical win. |

---

## 7. Implementation roadmap (prioritized, **not yet started** — planning only)

### Tier 1 — Highest impact

| # | Problem | Proposed solution | Expected impact | Complexity | Dependencies | How we'd measure it |
|---|---|---|---|---|---|---|
| 1 | No cross-clip color consistency | Per-clip auto color-correction pass (neutral-point/exposure normalization) before the existing shared grade | Single biggest "one cohesive production" signal | Medium (ffmpeg `eq`/histogram analysis per clip) | None new | Side-by-side frame comparison across clips in one video, before/after |
| 2 | Sourcing mismatches (chipmunk-footage class of bug) | A real relevance-scoring step comparing 2-3 candidate results per beat instead of first-past-filter | Directly prevents the single most damaging "generic/wrong" failure mode | Medium | None new | Re-run the Rosetta Stone generation that surfaced this; confirm no mismatch |
| 3 | Sound is one bed, not a mix | Add a low ambience layer + a small CC0 SFX set for motion-graphic reveals/accent transitions (#18) | Single highest-cited "amateur vs. pro" signal in the research | Medium | CC0 SFX sourcing (same licensing discipline as music) | A/B listen test against current output |
| 4 | Duration-driven, not content-driven cuts | A floor/ceiling + "does this beat need more/less time" heuristic (closes audit #38) | Directly implements Murch's "rhythm from content" principle | Medium | None new | Theo-persona review of shot-length variance across a video |

### Tier 2 — Important improvements

| # | Problem | Proposed solution | Expected impact | Complexity | Dependencies |
|---|---|---|---|---|---|
| 5 | Transitions keyed on a proxy, not the real subject claim | Compare normalized entity name, not just `entity_type` (closes audit #34) | Fixes a real, demonstrated wrong-continuity case | Low-medium | None |
| 6 | Prosody is two presets | Interpolate rate/pitch across beat position for a real arc (closes audit #41) | Removes robotic mid-video delivery | Medium | None new |
| 7 | Motion-graphic font mismatch | Thread the video's picked caption font into `motion_graphics.py` (closes audit #33) | Small but real type-system consistency fix | Low | None |
| 8 | No loudness normalization pass | Add a final `loudnorm` pass targeting ~-14 LUFS | Matches platform normalization target, avoids inconsistent perceived volume across videos | Low | None new |
| 9 | Face-unaware Ken Burns on non-photographic portraits | A documented fallback heuristic (bias upper-third for painting/bust-style imagery) (closes audit #35) | Better framing on the majority of pre-photography "person" beats | Medium | None new |

### Tier 3 — Advanced / premium improvements

| # | Problem | Proposed solution | Expected impact | Complexity | Dependencies |
|---|---|---|---|---|---|
| 10 | Single fixed grade, no correction step | Per-source auto white-balance/exposure correction before the shared grade, with skin-tone-aware secondary adjustment on portrait beats | The "professional vs. amateur grade" gap specifically called out in the research | High | None new, but needs real tuning/testing across many source types |
| 11 | Single mood bucket for music | Simple tone classification (already inferable from fact-check/topic) picking among 2-3 mood buckets | More emotionally matched scoring | Medium | More CC0 tracks per mood (licensing work, same discipline as existing `SOURCE.md`) |
| 12 | Genre-strategy question unresolved (§1.7) | A real user-facing decision: keep pushing photorealistic-documentary credibility, or lean further into the motion-graphics/illustrated register Kurzgesagt uses (which sidesteps the sourcing-consistency problem entirely for the beats it covers) | Could be the highest-leverage change of all, but is a product-direction call, not a technical one | N/A — decision, not build | Explicit user input (see open question below) |
| 13 | No per-beat framing/mood intent | Extend the beat schema with a lightweight framing hint (e.g. "push in," "hold static") the writer model proposes and the renderer honors | Closes the gap between "shot list" and "camera planning" stages | High | Schema change, writer-prompt work |

### Things to consider stopping (contribute to the generic feel today)

- Uniform Ken Burns direction alternating strictly by beat parity, regardless of content
  (already flagged in spirit by Theo's "even is not the same as intentional" principle).
- Treating `entity_type` match alone as "same subject" for transition selection (audit #34).
- Applying grade/grain/vignette as one global pass with no per-source awareness.

---

## 8. Quality-control system (repeatable, scored)

Extends `Claude outputs/QUALITY_BAR.md` (already created and used once this session) into
a systematic per-video scorecard, so "is this professional quality" has a checkable answer
instead of a gut-feel one. Suggested structure — a real scoring pass, not a checkbox
formality:

| Category | Check | Pass bar |
|---|---|---|
| Visual consistency | Do all clips in the video share a coherent grade/contrast/grain, or does one clip visibly look like a different source? | No visibly mismatched clip |
| Sourcing accuracy | Does every visual actually match its beat's narration content? | Zero "chipmunk-class" mismatches |
| Composition | Are named subjects framed on a rule-of-thirds point, not blind-centered? | At least the majority of "person"/"place" beats |
| Editing rhythm | Does shot duration vary with content, or is it flatly uniform? | At least one visibly shorter and one visibly longer beat per video |
| Transition motivation | Is every crossfade justified by genuine subject continuity? | No transition the reviewer can't explain |
| Color | Skin tones natural? No visible cast? | Pass/fail per video |
| Sound layering | Narration + music + at least occasional SFX/ambience present and audible? | At minimum narration + faded music this tier; SFX/ambience once Tier 1 #3 ships |
| Loudness | Final mix near -14 LUFS integrated? | Within ±2 LU once the normalization pass exists |
| Motion graphics | On-screen only while adding real information; gone promptly; type-matched to captions? | Pass/fail |
| Typography | Legible against every background; emphasis reserved for genuinely surprising words? | Pass/fail |
| Storytelling arc | Does pacing/intensity vary (hook → build → payoff), or is it flat? | Reviewer's honest judgment (Theo/Marcus persona lens) |
| Technical | No clipped audio, no banding, no caption truncation, no motion-graphic artifacts | Zero defects |
| **Overall verdict** | "Would this plausibly pass as made by a small professional team?" | Yes/no, with the specific reason if no |

A numeric score (e.g., 1 point per passing category, 13 max) is optional and can help
track trend over time, but the **written verdict with a specific reason** is the part that
actually matters — a score with no reasoning is exactly the kind of hollow "make it more
cinematic" feedback this whole task was set up to avoid.

---

## 9. Definition of the final end state

A finished Antiquary video, at the end of this roadmap, should be indistinguishable *in
perceived production value* from a short-form historical explainer segment made by a
small, competent, real production team — not because every frame is hand-crafted, but
because every automated decision (sourcing, cut timing, color, sound, typography) is made
with the same *intent* a human specialist in that domain would apply, consistently, video
after video. The test is not "does this look impressive once" — it's "would Theo Bramwell,
watching this cold with no context about how it was made, say 'leave it' rather than name
a specific place where the machinery shows through."

---

## Open question for the user before Tier 3 work starts

§1.7/§7 item 12: the research surfaced a genuine strategic fork, not just a technical gap
— our current approach chases photorealistic-documentary credibility with automatically
sourced stock assets of uncontrollable quality, while the project's own stated aspirational
reference (Kurzgesagt) succeeds by *not* attempting photorealism at all. Worth an explicit
decision at the right time: keep pushing the current direction harder (Tiers 1-2 do this),
or invest in a more illustrated/motion-graphics-forward register for at least some content
types. Not decided here — flagging it rather than picking silently.

---

Research and planning complete. Ready to begin implementation.
