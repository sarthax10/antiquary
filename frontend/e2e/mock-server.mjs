// Dependency-free mock of Antiquary's Flask JSON API for exercising the React SPA without
// Postgres/MinIO/Ollama. Mirrors the real routes and response shapes in app/studio,
// app/auth, app/admin and app/generation — if those change, update this too.
// Not used by the app or the deploy; see e2e/README.md.
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import url from "node:url";

const here = path.dirname(url.fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 5199);
const DIST = process.env.DIST || path.join(here, "..", "dist");
const LATENCY = Number(process.env.LATENCY || 180);
const EMPTY = process.env.EMPTY === "1"; // start with no stories

const now = Date.now();
const iso = (msAgo) => new Date(now - msAgo).toISOString();
const H = 3600e3, D = 24 * H;

const claim = (verdict, text, note = "") => ({ claim: text, verdict, note });

let stories = EMPTY ? [] : [
  {
    id: "e15da996b035", status: "pending", title: "The Forgotten Queen of Rome", topic: "",
    hook: "In 54 BC, a Roman general was forced into a marriage the Senate would never forget.",
    narration: "Rome's most powerful families traded marriages the way generals traded territory. When a rising commander was pressured into an alliance he never wanted, the woman at the centre of it quietly outmanoeuvred every man in the room. Her letters survive only in fragments, quoted by the very historians who tried to erase her. What they reveal is a strategist who shaped the late Republic from behind a curtain — and a name that was almost lost entirely.",
    duration_seconds: 42, created_at: iso(5 * H), decided_at: null, video: 1,
    fact_check: { overall_confidence: "medium", claims: [
      claim("verified", "Political marriages were common among Roman elite families in the late Republic."),
      claim("uncertain", "The marriage took place in 54 BC.", "The script gives a specific year but the surrounding events don't pin it down."),
      claim("verified", "Fragments of letters by Roman women survive through quotations by later authors."),
      claim("uncertain", "Her name was almost lost from the historical record.", "Framing is subjective; hard to verify as stated."),
      claim("verified", "The late Republic saw intense rivalry among senatorial families."),
    ] },
  },
  {
    id: "13e3bc07fa9b", status: "pending", title: "Mangasaurus vs. Redcoats", topic: "a story about an indian warrior who fought the british army",
    hook: "One warrior. One fort. Three British regiments that didn't see it coming.",
    narration: "In the hills of central India, a local chieftain held a hilltop fort against a British column for eleven days. Accounts from both sides disagree on almost everything — the number of defenders, who fired first, and how it ended. What they agree on is that the siege became a legend in the villages below, retold for generations long after the fort itself fell into ruin.",
    duration_seconds: 32.4, created_at: iso(7 * H), decided_at: null, video: 3,
    fact_check: { overall_confidence: "low", claims: [
      claim("false", "The siege lasted exactly eleven days.", "No consistent source for the duration was produced."),
      claim("uncertain", "Three British regiments took part.", "Regiment count isn't supported elsewhere in the script."),
      claim("false", "The chieftain's name was Mangasaurus.", "This name does not appear to be historical."),
      claim("uncertain", "The fort is now in ruins."),
      claim("uncertain", "The story was retold in local villages for generations."),
    ] },
  },
  {
    id: "3da4ceb2cdb7", status: "pending", title: "The Forgotten Spy", topic: "",
    hook: "She smuggled secrets past checkpoints hidden inside knitting patterns.",
    narration: "During the Second World War, resistance networks encoded observations about train movements into seemingly ordinary knitting. A dropped stitch could mean a troop convoy; a purl could mark an armoured car. Sympathetic grandmothers sat by windows overlooking rail yards, needles clicking, recording everything that passed.",
    duration_seconds: 24.8, created_at: iso(9 * H), decided_at: null, video: 2,
    fact_check: { overall_confidence: "high", claims: [
      claim("verified", "Knitting was used to encode intelligence during the Second World War."),
      claim("verified", "Observers monitored train movements from windows near rail yards."),
      claim("false", "A purl stitch universally marked an armoured car.", "No evidence of a standard code — overly specific."),
      claim("verified", "Resistance networks relied on civilians for observation."),
    ] },
  },
  {
    id: "5534d7d78ea0", status: "pending", title: "The Forgotten Pirate Queen", topic: "",
    hook: "She commanded 1,800 ships — and negotiated her own retirement.",
    narration: "In the early nineteenth century, Ching Shih rose from a Cantonese floating brothel to lead one of the largest pirate confederations in history. When the Qing government could not defeat her, it offered amnesty instead. She accepted, kept her fortune, and opened a gambling house.",
    duration_seconds: 26.2, created_at: iso(1.2 * D), decided_at: null, video: 0,
    fact_check: { overall_confidence: "medium", claims: [
      claim("verified", "Ching Shih led a large pirate confederation in the South China Sea."),
      claim("uncertain", "She commanded 1,800 ships.", "Figures vary widely between sources."),
      claim("verified", "The Qing government offered amnesty to pirates in 1810."),
      claim("uncertain", "She opened a gambling house after retiring."),
      claim("false", "She was never captured because she was invisible at sea.", "Hyperbole presented as fact."),
      claim("uncertain", "She was born in 1775."),
      claim("verified", "She retained much of her wealth after surrender."),
    ] },
  },
  {
    id: "128cbfa66b6e", status: "pending", title: "The Mary Celeste", topic: "",
    hook: "The table was set. The cargo untouched. The crew — gone.",
    narration: "In December 1872 the brigantine Mary Celeste was found drifting in the Atlantic, seaworthy and fully provisioned, with no one aboard. The lifeboat was missing. Theories have ranged from mutiny to sea monsters, but the likeliest explanation is far quieter: fumes from the alcohol cargo, a panicked captain, and a line that snapped.",
    duration_seconds: 38.2, created_at: iso(2 * D), decided_at: null, video: 0,
    fact_check: { overall_confidence: "medium", claims: [
      claim("verified", "The Mary Celeste was found abandoned in December 1872."),
      claim("verified", "The ship was carrying a cargo of alcohol."),
      claim("verified", "The lifeboat was missing when the ship was found."),
      claim("uncertain", "The table was set for a meal.", "Popular embellishment; contemporary reports differ."),
      claim("verified", "Theories have included mutiny and piracy."),
      claim("uncertain", "Alcohol fumes are the likeliest explanation."),
      claim("verified", "The ship was still seaworthy."),
      claim("verified", "It was found in the Atlantic Ocean."),
    ] },
  },
  {
    id: "25d8dbb27d42", status: "pending", title: "The Forgotten Creator", topic: "video game",
    hook: "A legendary game designer was erased from history by his biggest rival.",
    narration: "In 1981, a designer created a 3D fighting game that became a huge hit in arcades. But when a rival studio released a near-identical cabinet months later, the original creator's name vanished from magazine covers. Decades on, collectors are still arguing over who really built it first.",
    duration_seconds: 33, created_at: iso(2.4 * D), decided_at: null, video: 3, noVideo: true,
    fact_check: { overall_confidence: "low", claims: [
      claim("false", "A 3D fighting game was a hit in arcades in 1981.", "3D fighting games did not exist in 1981."),
      claim("uncertain", "A rival studio released a near-identical cabinet."),
      claim("false", "The designer's name vanished from magazine covers.", "No evidence provided."),
      claim("uncertain", "Collectors still argue about who built it first."),
      claim("verified", "Arcade games were popular in the early 1980s."),
      claim("verified", "Studios frequently cloned successful arcade games."),
      claim("uncertain", "The designer was considered legendary."),
    ] },
  },
  {
    id: "9aa86d137d09", status: "approved", title: "The Mary Celeste Mystery", topic: "",
    hook: "A ghost ship, a missing crew, and 150 years of theories.",
    narration: "Found drifting between the Azores and Portugal in 1872, the Mary Celeste has become the archetype of the ghost ship. Its captain, his wife and their two-year-old daughter were among those who vanished.",
    duration_seconds: 39.4, created_at: iso(3 * D), decided_at: iso(2.8 * D), video: 0,
    fact_check: { overall_confidence: "high", claims: [
      claim("verified", "The Mary Celeste was found between the Azores and Portugal."),
      claim("verified", "The captain's wife and daughter were aboard."),
      claim("uncertain", "The daughter was two years old."),
      claim("verified", "The ship was found in 1872."),
    ] },
  },
  {
    id: "7bb1c0de4411", status: "approved", title: "The Great Emu War", topic: "australia",
    hook: "In 1932, Australia sent soldiers with machine guns to fight birds. The birds won.",
    narration: "Farmers in Western Australia faced tens of thousands of emus destroying their wheat. The government dispatched soldiers armed with Lewis guns. After weeks of frustration and very few kills, the operation was withdrawn.",
    duration_seconds: 31, created_at: iso(5 * D), decided_at: iso(4.5 * D), video: 2,
    fact_check: { overall_confidence: "high", claims: [
      claim("verified", "The Emu War took place in 1932 in Western Australia."),
      claim("verified", "Soldiers used Lewis guns."),
      claim("verified", "The operation was withdrawn."),
    ] },
  },
  {
    id: "c41f00a9b2e7", status: "approved", title: "The Dancing Plague of 1518", topic: "",
    hook: "For weeks in Strasbourg, hundreds of people could not stop dancing.",
    narration: "It began with one woman in July 1518. Within weeks, dozens had joined her in the streets. Authorities, believing more dancing would cure them, hired musicians and built a stage.",
    duration_seconds: 36.5, created_at: iso(8 * D), decided_at: iso(7 * D), video: 1,
    fact_check: { overall_confidence: "medium", claims: [
      claim("verified", "The dancing plague occurred in Strasbourg in 1518."),
      claim("uncertain", "Hundreds of people were affected.", "Estimates vary."),
      claim("verified", "Authorities hired musicians."),
    ] },
  },
  {
    id: "d0a17e55f3c2", status: "rejected", title: "The Moon Treaty of Atlantis", topic: "atlantis",
    hook: "Atlantis signed a treaty with the moon in 3000 BC.",
    narration: "According to lost tablets, the kingdom of Atlantis formally agreed borders with lunar envoys.",
    duration_seconds: 22, created_at: iso(10 * D), decided_at: iso(9.5 * D), video: 3,
    fact_check: { overall_confidence: "low", claims: [
      claim("false", "Atlantis signed a treaty in 3000 BC.", "Atlantis is a legend from Plato."),
      claim("false", "Lunar envoys existed."),
    ] },
  },
];

let users = [
  { id: 1, email: "admin@antiquary.test", role: "admin", status: "approved", created_at: iso(30 * D), approved_at: iso(30 * D), password: "correct-horse-battery" },
  { id: 2, email: "mira.okafor@example.com", role: "user", status: "pending", created_at: iso(3 * H), approved_at: null, password: "x" },
  { id: 3, email: "j.lindqvist@example.org", role: "user", status: "pending", created_at: iso(1.5 * D), approved_at: null, password: "x" },
  { id: 4, email: "sam.ito@example.com", role: "user", status: "approved", created_at: iso(12 * D), approved_at: iso(11 * D), password: "correct-horse-battery" },
  { id: 5, email: "spam-bot-4411@example.net", role: "user", status: "rejected", created_at: iso(6 * D), approved_at: null, password: "x" },
  { id: 6, email: "r.castellanos@example.com", role: "user", status: "suspended", created_at: iso(20 * D), approved_at: iso(19 * D), password: "x" },
];

const sessions = new Map(); // sid -> userId
let job = null; // {id, status, topic, stage, started_at, finished_at, error, story_id, timer}
const STAGES = ["writing", "fact_checking", "sourcing_visuals", "recording_narration", "generating_captions", "rendering"];
const STAGE_MS = Number(process.env.STAGE_MS || 2500);

if (process.env.JOB === "running") {
  job = { id: 1, status: "running", topic: "The strangest rituals of Ancient Rome", stage: "sourcing_visuals", started_at: now / 1000 - 94, finished_at: null, error: null, story_id: null };
} else if (process.env.JOB === "error") {
  job = { id: 1, status: "error", topic: "", stage: "rendering", started_at: now / 1000 - 400, finished_at: now / 1000 - 200, error: "Traceback (most recent call last):\n  File \"run_pipeline.py\", line 88, in main\n    render(...)\nffmpeg exited with code 1: Invalid data found when processing input", story_id: null };
}

const counts = (s) => {
  const c = { verified: 0, uncertain: 0, false: 0 };
  for (const x of s.fact_check?.claims || []) if (x.verdict in c) c[x.verdict]++;
  return c;
};
const storyJson = (s, withUrl) => {
  const { video, noVideo, ...rest } = s;
  const out = { ...rest, claim_counts: counts(s), needs_human_review: true };
  if (withUrl) out.video_url = noVideo ? null : `/api/stories/${s.id}/video`;
  return out;
};
const userJson = ({ password, ...u }) => u;

function send(res, status, body, headers = {}) {
  const data = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(data);
}
const readBody = (req) => new Promise((resolve) => {
  let buf = "";
  req.on("data", (c) => (buf += c));
  req.on("end", () => { try { resolve(JSON.parse(buf || "{}")); } catch { resolve({}); } });
});
const currentUser = (req) => {
  const sid = /(?:^|;\s*)sid=([^;]+)/.exec(req.headers.cookie || "")?.[1];
  const u = users.find((x) => x.id === sessions.get(sid));
  return u && u.status === "approved" ? u : null;
};

function tickJob() {
  if (!job || job.status !== "running") return;
  const i = STAGES.indexOf(job.stage);
  if (i < STAGES.length - 1) {
    job.stage = STAGES[i + 1];
    job.timer = setTimeout(tickJob, STAGE_MS);
  } else {
    const id = Math.random().toString(16).slice(2, 14);
    stories.push({
      id, status: "pending", title: job.topic ? `The Untold Story of ${job.topic.replace(/^the /i, "").slice(0, 40)}` : "The Clockmaker's Silent Mutiny",
      topic: job.topic, hook: "Nobody noticed the clocks had stopped — until the ships ran aground.",
      narration: "A harbour town kept its tide clocks wound by a single family for ninety years. When a dispute over wages went unresolved, the clocks quietly stopped, and within a week three merchant ships misjudged the tide.",
      duration_seconds: 35.2, created_at: new Date().toISOString(), decided_at: null, video: 1,
      fact_check: { overall_confidence: "medium", claims: [claim("uncertain", "The family kept the clocks for ninety years."), claim("verified", "Tide clocks were used in harbour towns.")] },
    });
    Object.assign(job, { status: "done", finished_at: Date.now() / 1000, story_id: id });
  }
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, "http://x");
  const p = u.pathname;

  if (!p.startsWith("/api/")) {
    let file = path.join(DIST, p === "/" ? "index.html" : p);
    if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(DIST, "index.html");
    const ext = path.extname(file);
    const type = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".woff2": "font/woff2" }[ext] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": type });
    return fs.createReadStream(file).pipe(res);
  }

  await new Promise((r) => setTimeout(r, LATENCY));
  const me = currentUser(req);
  const method = req.method;

  if (p === "/api/health") return send(res, 200, { ok: true });
  if (p === "/api/auth/csrf") return send(res, 200, { csrf_token: "dev-token" });
  if (p === "/api/auth/me") return send(res, 200, { user: me ? { id: me.id, email: me.email, role: me.role, status: me.status } : null });
  if (p === "/api/auth/login" && method === "POST") {
    const b = await readBody(req);
    const user = users.find((x) => x.email === (b.email || "").trim().toLowerCase());
    if (!user || user.password !== b.password) return send(res, 401, { error: "Invalid email or password." });
    if (user.status === "pending") return send(res, 401, { error: "Your account is awaiting admin approval." });
    if (user.status === "rejected") return send(res, 401, { error: "Your access request was not approved." });
    if (user.status === "suspended") return send(res, 401, { error: "Your account has been suspended." });
    const sid = Math.random().toString(36).slice(2);
    sessions.set(sid, user.id);
    return send(res, 200, { user: userJson(user) }, { "Set-Cookie": `sid=${sid}; Path=/; HttpOnly` });
  }
  if (p === "/api/auth/signup" && method === "POST") {
    const b = await readBody(req);
    const email = (b.email || "").trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return send(res, 400, { error: "Enter a valid email address." });
    if (!b.password || b.password.length < 10) return send(res, 400, { error: "Password must be at least 10 characters." });
    if (users.some((x) => x.email === email)) return send(res, 409, { error: "An account with this email already exists." });
    users.push({ id: users.length + 1, email, role: "user", status: "pending", created_at: new Date().toISOString(), approved_at: null, password: b.password });
    return send(res, 201, { message: "Request received — an admin will review it shortly." });
  }
  if (p === "/api/auth/logout" && method === "POST") {
    if (!me) return send(res, 401, { error: "unauthorized" });
    return send(res, 200, { message: "Logged out." }, { "Set-Cookie": "sid=; Path=/; Max-Age=0" });
  }

  if (!me) return send(res, 401, { error: "Login required" });

  if (p === "/api/stories" && method === "GET") {
    const recent = Number(u.searchParams.get("recent"));
    const status = u.searchParams.get("status");
    let list;
    if (recent) list = [...stories].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, recent);
    else if (status === "pending") list = stories.filter((s) => s.status === "pending").sort((a, b) => a.created_at.localeCompare(b.created_at));
    else if (["approved", "rejected"].includes(status)) list = stories.filter((s) => s.status === status).sort((a, b) => (b.decided_at || "").localeCompare(a.decided_at || ""));
    else return send(res, 400, { error: "pass ?status=pending|approved|rejected or ?recent=N" });
    return send(res, 200, { stories: list.map((s) => storyJson(s)) });
  }
  let m;
  if ((m = /^\/api\/stories\/([^/]+)$/.exec(p))) {
    const s = stories.find((x) => x.id === m[1]);
    return s ? send(res, 200, { story: storyJson(s, true) }) : send(res, 404, { error: "not found" });
  }
  if ((m = /^\/api\/stories\/([^/]+)\/video$/.exec(p))) {
    const s = stories.find((x) => x.id === m[1]);
    if (!s || s.noVideo) return send(res, 404, { error: "video not available" });
    if (!fs.existsSync(path.join(process.env.VIDEOS || path.join(here, "videos"), `v${s.video}.${process.env.VIDEO_EXT || "mp4"}`))) return send(res, 404, { error: "no sample video" });
    const file = path.join(process.env.VIDEOS || path.join(here, "videos"), `v${s.video}.${process.env.VIDEO_EXT || "mp4"}`);
    const size = fs.statSync(file).size;
    const range = /bytes=(\d*)-(\d*)/.exec(req.headers.range || "");
    if (range) {
      const start = Number(range[1] || 0), end = range[2] ? Number(range[2]) : size - 1;
      res.writeHead(206, { "Content-Type": `video/${process.env.VIDEO_EXT || "mp4"}`, "Content-Length": end - start + 1, "Content-Range": `bytes ${start}-${end}/${size}`, "Accept-Ranges": "bytes" });
      return fs.createReadStream(file, { start, end }).pipe(res);
    }
    res.writeHead(200, { "Content-Type": `video/${process.env.VIDEO_EXT || "mp4"}`, "Content-Length": size, "Accept-Ranges": "bytes" });
    return fs.createReadStream(file).pipe(res);
  }
  if ((m = /^\/api\/stories\/([^/]+)\/decide$/.exec(p)) && method === "POST") {
    const b = await readBody(req);
    if (!["approve", "reject"].includes(b.action)) return send(res, 400, { error: "action must be 'approve' or 'reject'" });
    const s = stories.find((x) => x.id === m[1]);
    if (!s) return send(res, 404, { error: "not found" });
    s.status = b.action === "approve" ? "approved" : "rejected";
    s.decided_at = new Date().toISOString();
    return send(res, 200, { story: storyJson(s) });
  }
  if ((m = /^\/api\/stories\/([^/]+)\/restore$/.exec(p)) && method === "POST") {
    const s = stories.find((x) => x.id === m[1]);
    if (!s) return send(res, 404, { error: "not found" });
    s.status = "pending"; s.decided_at = null;
    return send(res, 200, { story: storyJson(s) });
  }
  if (p === "/api/generate" && method === "POST") {
    const b = await readBody(req);
    if (job?.status === "running") return send(res, 200, { started: false, message: "A generation is already running." });
    job = { id: (job?.id || 0) + 1, status: "running", topic: (b.topic || "").trim(), stage: "writing", started_at: Date.now() / 1000, finished_at: null, error: null, story_id: null };
    job.timer = setTimeout(tickJob, STAGE_MS);
    return send(res, 200, { started: true, message: "started" });
  }
  if (p === "/api/generate/cancel" && method === "POST") {
    if (job?.status !== "running") return send(res, 200, { cancelled: false, message: "Nothing is running." });
    clearTimeout(job.timer);
    Object.assign(job, { status: "cancelled", finished_at: Date.now() / 1000 });
    return send(res, 200, { cancelled: true, message: "cancelled" });
  }
  if (p === "/api/generate/status") {
    if (!job) return send(res, 200, { status: "idle" });
    const { timer, id, ...rest } = job;
    return send(res, 200, { ...rest, pid: 1234 });
  }
  if (p === "/api/admin/users") {
    if (me.role !== "admin") return send(res, 403, { error: "forbidden" });
    const status = u.searchParams.get("status");
    const list = users.filter((x) => !status || x.status === status).sort((a, b) => b.created_at.localeCompare(a.created_at));
    return send(res, 200, { users: list.map(userJson) });
  }
  if ((m = /^\/api\/admin\/users\/(\d+)\/status$/.exec(p)) && method === "POST") {
    if (me.role !== "admin") return send(res, 403, { error: "forbidden" });
    const b = await readBody(req);
    if (!["pending", "approved", "rejected", "suspended"].includes(b.status)) return send(res, 400, { error: "invalid status" });
    if (Number(m[1]) === me.id && b.status !== "approved") return send(res, 400, { error: "you can't change your own account's status" });
    const target = users.find((x) => x.id === Number(m[1]));
    if (!target) return send(res, 404, { error: "not found" });
    target.status = b.status;
    if (b.status === "approved") target.approved_at = new Date().toISOString();
    return send(res, 200, { user: userJson(target) });
  }
  return send(res, 404, { error: "not found" });
});

server.listen(PORT, () => console.log(`mock api + spa on http://localhost:${PORT} (dist=${DIST})`));
