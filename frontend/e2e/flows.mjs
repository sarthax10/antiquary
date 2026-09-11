// End-to-end flow checks against the mock API. Prints PASS/FAIL per step + screenshots.
// Run: see e2e/README.md. Requires `playwright` to be resolvable (e.g. `npx -p playwright node e2e/flows.mjs`).
import fs from "node:fs";
import { chromium } from "playwright";
const base = process.argv[2] || "http://localhost:5199";
const out = process.env.SHOTS || "e2e/shots"; fs.mkdirSync(out, { recursive: true });
let failures = 0;
const check = async (name, fn) => { try { await fn(); console.log("PASS", name); } catch (e) { failures++; console.log("FAIL", name, "-", e.message.split("\n")[0]); } };
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const shot = (n) => page.screenshot({ path: `${out}/${n}.png` });
const expect = async (locator, timeout = 4000) => { await locator.first().waitFor({ state: "visible", timeout }); };

await check("unauthenticated /review redirects to login and remembers destination", async () => {
  await page.goto(base + "/review?item=3da4ceb2cdb7");
  await expect(page.getByRole("heading", { name: "Welcome back." }));
});
await check("login with wrong password shows error", async () => {
  await page.getByLabel("Email").fill("admin@antiquary.test");
  await page.getByLabel("Password", { exact: true }).fill("nope-nope-nope");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Invalid email or password" }));
  await shot("login-error");
});
await check("password visibility toggle", async () => {
  await page.getByRole("button", { name: "Show password" }).click();
  if ((await page.getByLabel("Password", { exact: true }).getAttribute("type")) !== "text") throw new Error("not revealed");
  await page.getByRole("button", { name: "Hide password" }).click();
});
await check("login returns to the remembered story in review", async () => {
  await page.getByLabel("Password", { exact: true }).fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "The Forgotten Spy" }));
  if (!page.url().includes("item=3da4ceb2cdb7")) throw new Error("url " + page.url());
});
await check("review shows flagged warning and fact check", async () => {
  await expect(page.getByText(/1 claim needs a source/));
  await expect(page.getByText("Model confidence · High"));
  await shot("review-spy");
});
await check("F toggles verified claims", async () => {
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("f");
  await expect(page.getByText("Knitting was used to encode intelligence during the Second World War."));
});
await check("Ctrl+R style chord does NOT reject", async () => {
  const before = await page.locator(".review-position").innerText();
  await page.keyboard.down("Control"); await page.keyboard.press("KeyA"); await page.keyboard.up("Control");
  await page.waitForTimeout(600);
  const after = await page.locator(".review-position").innerText();
  if (before !== after) throw new Error(`queue changed ${before} -> ${after}`);
});
await check("A approves with stamp + undo toast, queue shrinks", async () => {
  await page.keyboard.press("a");
  await page.waitForTimeout(120);
  await shot("review-stamp");
  await expect(page.getByText("Approved — moved to Library"));
  await expect(page.locator(".review-position").filter({ hasText: "/ 05" }));
  await shot("review-toast");
});
await check("Undo restores the story to the queue and selects it", async () => {
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.locator(".review-position").filter({ hasText: "/ 06" }));
  await expect(page.getByRole("heading", { name: "The Forgotten Spy" }));
});
await check("J / K navigate and update URL", async () => {
  await page.keyboard.press("j");
  await page.waitForTimeout(200);
  if (page.url().includes("3da4ceb2cdb7")) throw new Error("url didn't change");
  await page.keyboard.press("k");
  await page.waitForTimeout(200);
  if (!page.url().includes("3da4ceb2cdb7")) throw new Error("url didn't return");
});
await check("reject via button", async () => {
  await page.getByRole("button", { name: /^Reject/ }).click();
  await expect(page.getByText("Rejected — moved to Archive"));
});
await check("g a navigates to archive (and does not approve)", async () => {
  await page.waitForTimeout(300);
  const before = await page.locator(".review-position").innerText();
  await page.keyboard.press("g"); await page.keyboard.press("a");
  await expect(page.getByRole("heading", { name: "Archive" }));
  await expect(page.getByRole("searchbox"));
  if (!before.includes("/ 05")) throw new Error("queue was " + before);
});
await check("archive search filters + return to review with undo", async () => {
  await page.keyboard.press("/");
  await page.keyboard.type("atlantis");
  await expect(page.getByText("1 of 2"));
  await page.getByRole("button", { name: "Return to review" }).click();
  await expect(page.getByText("Moved back to the review desk"));
  await shot("archive-restore");
});
await check("command menu finds a story and opens it", async () => {
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("combobox"));
  await page.keyboard.type("emu");
  await shot("command-menu");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "The Great Emu War" }));
});
await check("story detail return to review", async () => {
  await page.getByRole("button", { name: "Return to review" }).click();
  await expect(page.locator(".stamp").filter({ hasText: "Awaiting review" }));
  await expect(page.getByRole("button", { name: "Approve" }));
});
await check("? opens shortcuts dialog, Esc closes", async () => {
  await page.locator("body").click({ position: { x: 700, y: 880 } });
  await page.keyboard.press("Shift+Slash");
  await expect(page.getByRole("heading", { name: "Keyboard shortcuts" }));
  await page.keyboard.press("Escape");
  await page.getByRole("heading", { name: "Keyboard shortcuts" }).waitFor({ state: "hidden" });
});
await check("create: suggestion fills prompt, generate runs real stages, shows widget", async () => {
  await page.goto(base + "/create");
  await page.getByRole("button", { name: "An inventor history forgot" }).click();
  await expect(page.getByRole("button", { name: "Generate story" }));
  await page.getByRole("button", { name: "Generate story" }).click();
  await expect(page.getByText("Developing").first());
  await expect(page.locator(".gen-widget"));
  await page.waitForTimeout(2800);
  await shot("create-developing");
});
await check("stop asks for confirmation and cancels", async () => {
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByRole("heading", { name: "Stop this generation?" }));
  await shot("create-stop-confirm");
  await page.getByRole("button", { name: "Stop generation" }).click();
  await expect(page.getByText("The last generation was stopped"));
});
await check("surprise me → completes → toast offers review", async () => {
  await page.getByRole("button", { name: "Surprise me" }).click();
  await expect(page.getByText("Developing").first());
  await expect(page.getByText("A new story is ready for review"), 25000);
  await shot("create-done-toast");
  await page.getByRole("button", { name: "Review", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "The Clockmaker's Silent Mutiny" }));
});
await check("members: approve pending with undo; suspend requires confirm", async () => {
  await page.goto(base + "/admin/users");
  await expect(page.getByRole("tab", { name: /Requests/ }));
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText("Access approved"));
  await page.getByRole("tab", { name: /Active/ }).click();
  await page.getByRole("button", { name: "Suspend" }).first().click();
  await expect(page.getByRole("heading", { name: "Suspend this member?" }));
  await shot("members-confirm");
  await page.getByRole("button", { name: "Cancel" }).click();
});
await check("sign out lands on login", async () => {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back." }));
});
await check("signup: live hints, mismatch, success banner on login with email prefilled", async () => {
  await page.goto(base + "/signup");
  await page.getByLabel("Email").fill("new.person@example.com");
  await page.getByLabel("Password", { exact: true }).fill("short");
  await expect(page.getByText(/5 to go/));
  await page.getByLabel("Password", { exact: true }).fill("long-enough-pass");
  await page.getByLabel("Confirm password").fill("long-enough-pasX");
  await page.getByLabel("Confirm password").blur();
  await expect(page.getByText("Doesn’t match the password above."));
  await shot("signup-mismatch");
  await page.getByLabel("Confirm password").fill("long-enough-pass");
  await page.getByRole("button", { name: "Request access" }).click();
  await expect(page.getByText("Request sent"));
  if ((await page.getByLabel("Email").inputValue()) !== "new.person@example.com") throw new Error("email not prefilled");
  await shot("login-after-signup");
});
await check("pending account gets a clear message", async () => {
  await page.getByLabel("Password", { exact: true }).fill("long-enough-pass");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Your account is awaiting admin approval."));
});
await check("no uncaught page errors", async () => { if (errors.length) throw new Error(errors.join(" | ")); });

// Mobile pass
const m = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const mp = await m.newPage();
mp.on("pageerror", (e) => errors.push("mobile: " + e.message));
await mp.request.post(base + "/api/auth/login", { data: { email: "admin@antiquary.test", password: "correct-horse-battery" } });
await check("mobile: review sticky decision bar visible and usable", async () => {
  await mp.goto(base + "/review");
  await mp.getByRole("button", { name: /^Approve/ }).waitFor({ state: "visible" });
  const box = await mp.getByRole("button", { name: /^Approve/ }).boundingBox();
  if (!box || box.y + box.height > 844 - 64) throw new Error("approve hidden under tab bar: " + JSON.stringify(box));
  await mp.screenshot({ path: `${out}/mobile-review-sticky.png` });
});
await check("mobile: account sheet shows members + sign out", async () => {
  await mp.getByRole("button", { name: "Account menu" }).click();
  await mp.getByRole("link", { name: /Members/ }).waitFor();
  await mp.screenshot({ path: `${out}/mobile-account-sheet.png` });
  await mp.keyboard.press("Escape");
});
await check("mobile: no horizontal overflow on any page", async () => {
  for (const r of ["/create", "/review", "/library", "/archive", "/admin/users", "/stories/9aa86d137d09"]) {
    await mp.goto(base + r); await mp.waitForTimeout(500);
    const [sw, cw] = await mp.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    if (sw > cw) throw new Error(`${r} overflows ${sw} > ${cw}`);
  }
});
await browser.close();
console.log(failures ? `${failures} FAILED` : "ALL PASSED");
