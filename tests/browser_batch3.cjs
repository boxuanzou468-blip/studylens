/* Offline Chromium acceptance against actual file:// reports and decoded media. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const assert = require("node:assert/strict");
const repo = path.resolve(__dirname, "..");
const media = process.argv[2];
if (!media)
  throw new Error("Usage: node tests/browser_batch3.cjs <test-media-folder>");
const logs = path.join(media, ".studylens", "logs", "batch3");
const fixtures = JSON.parse(
  fs.readFileSync(path.join(logs, "fixture-paths.json"), "utf8"),
);
const screenshots = path.join(repo, "examples", "screenshots");
fs.mkdirSync(screenshots, { recursive: true });
const evidence = {
  status: "running",
  checks: [],
  screenshots: [],
  pageErrors: [],
  dialogs: [],
  externalRequests: [],
};
let browser;
function check(name, details) {
  evidence.checks.push({ name, details });
  console.log("PASS " + name, JSON.stringify(details ?? ""));
}
async function shot(page, name) {
  const file = path.join(screenshots, name + ".png");
  const input = page.locator("#share-link");
  const old = await input.inputValue();
  await input.evaluate(
    (node) => (node.value = "file:///本地课程/studylens-report.html"),
  );
  await page.screenshot({ path: file, fullPage: true });
  await input.evaluate((node, value) => (node.value = value), old);
  evidence.screenshots.push(file);
}
function track(page) {
  page.on("pageerror", (err) => evidence.pageErrors.push(String(err)));
  page.on("dialog", async (d) => {
    evidence.dialogs.push(d.message());
    await d.dismiss();
  });
  page.on("request", (r) => {
    if (/^https?:/i.test(r.url())) evidence.externalRequests.push(r.url());
  });
}
const state = (page) =>
  page
    .locator("#player")
    .evaluate((v) => ({
      time: v.currentTime,
      duration: v.duration,
      rate: v.playbackRate,
      paused: v.paused,
      ended: v.ended,
      width: v.videoWidth,
      ready: v.readyState,
      src: v.currentSrc,
    }));
async function voiceReady(page, t = 0) {
  await page.goto(
    pathToFileURL(fixtures.real_report).href + `#v=${fixtures.voice_id}&t=${t}`,
  );
  await page.waitForFunction((t) => {
    const v = document.getElementById("player");
    return v.readyState >= 2 && Math.abs(v.currentTime - t) < 0.3;
  }, t);
}
(async () => {
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.STUDYLENS_BROWSER_EXECUTABLE || undefined,
    args: ["--autoplay-policy=no-user-gesture-required"],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
    colorScheme: "light",
    recordVideo: {
      dir: path.join(logs, "browser-recording"),
      size: { width: 1280, height: 900 },
    },
  });
  await context.setOffline(true);
  const example = await context.newPage();
  track(example);
  await example.goto(pathToFileURL(fixtures.example_report).href);
  await example.locator(".video-title").first().waitFor();
  assert.equal(await example.locator(".video-entry").count(), 2);
  await shot(example, "report-light");
  await example.locator("#theme-toggle").click();
  assert.equal(
    await example.locator("html").getAttribute("data-theme"),
    "dark",
  );
  await example.waitForTimeout(180);
  await shot(example, "report-dark");
  await example.setViewportSize({ width: 390, height: 844 });
  await example.locator("#theme-toggle").click();
  await example.waitForTimeout(180);
  assert(
    await example.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  await shot(example, "report-mobile");
  check("three screenshots and mobile without horizontal overflow", {
    width: 390,
  });
  await example.setViewportSize({ width: 1440, height: 1050 });
  await example.locator("#search").fill("闭卷");
  assert.equal(await example.locator(".video-entry").count(), 1);
  await example.locator("#search").fill("");
  await example.locator("#must-only").check();
  assert.deepEqual(await example.locator(".segment .badge").allTextContents(), [
    "重点",
    "重点",
  ]);
  await example.locator("#topic-filter").selectOption("主动回忆");
  assert.equal(await example.locator(".segment").count(), 1);
  await example.locator("#search").fill("没有这个关键词");
  assert.equal(await example.locator("#catalog .empty").count(), 1);
  check("keyword, must-only, topic and empty results");
  const page = await context.newPage();
  track(page);
  await voiceReady(page, 0);
  await page.locator("#player").evaluate((v) => (v.muted = true));
  assert.equal(await page.locator('img[src="x"]').count(), 0);
  assert(
    (await page.locator(".video-title").allTextContents()).includes(
      "</script><img src=x onerror=alert(1)>",
    ),
  );
  assert.equal(await page.locator("script").count(), 2);
  check("malicious title remains inert text", {
    dialogs: evidence.dialogs.length,
  });
  await page
    .locator(
      `.segment-jump[data-video-id="${fixtures.voice_id}"][data-segment-index="1"]`,
    )
    .click();
  await page.waitForFunction(() => {
    const v = document.getElementById("player");
    return (
      v.currentTime > 24.05 &&
      v.currentTime < 27 &&
      !v.paused &&
      v.videoWidth > 0
    );
  });
  check(
    "click segment starts decoded real video at 24 seconds",
    await state(page),
  );
  await shot(page, "real-playback");
  await page.locator("#play-toggle").click();
  await page.locator("#base-rate").selectOption("1.5");
  await page.locator("#smart-mode").check();
  await page
    .locator(
      `.segment-jump[data-video-id="${fixtures.voice_id}"][data-segment-index="2"]`,
    )
    .click();
  await page.waitForFunction(
    () =>
      Math.abs(document.getElementById("player").playbackRate - 1.75) < 0.001,
  );
  check("smart speed uses 1.75", await state(page));
  await page.locator("#player").evaluate((v) => {
    v.pause();
    v.currentTime = 25;
  });
  await page.waitForFunction(() => {
    const v = document.getElementById("player");
    return !v.seeking && Math.abs(v.playbackRate - 1.5) < 0.001;
  });
  check("leaving speed restores user 1.5 base rate", await state(page));
  // Real currentTime changes generate native seeking/seeked events; playback then
  // naturally crosses the 79s boundary. No synthetic timeupdate event is used.
  await page.locator("#player").evaluate((v) => {
    v.currentTime = 78.3;
  });
  await page.waitForFunction(() => !document.getElementById("player").seeking);
  await page.locator("#play-toggle").click();
  await page.locator("#skip-toast").waitFor({ state: "visible" });
  await page.waitForFunction(
    () => document.getElementById("player").currentTime >= 85,
  );
  check(
    "natural playback automatically skips tail and shows notice",
    await state(page),
  );
  await shot(page, "smart-skip");
  await page.locator("#skip-back").click();
  await page.waitForFunction(() => {
    const v = document.getElementById("player");
    return v.currentTime >= 79 && v.currentTime < 81 && !v.paused;
  });
  await page.waitForTimeout(250);
  assert((await state(page)).time < 82);
  check("go-back respects chosen skip segment", await state(page));
  await page.locator("#player").evaluate((v) => {
    v.pause();
    v.currentTime = 79.3;
  });
  await page.waitForFunction(() => !document.getElementById("player").seeking);
  await page.locator("#play-toggle").click();
  await page.waitForTimeout(200);
  assert((await state(page)).time < 82);
  check("manual native seek into skip does not jump away", await state(page));
  await page.locator("#player").evaluate((v) => {
    v.pause();
    v.currentTime = 25;
  });
  await page.waitForFunction(() => !document.getElementById("player").seeking);
  await page.locator("#player").evaluate((v) => {
    v.currentTime = 78.3;
  });
  await page.waitForFunction(() => !document.getElementById("player").seeking);
  await page.locator("#play-toggle").click();
  await page.locator("#skip-toast").waitFor({ state: "visible" });
  await page.locator("#skip-toast").waitFor({ state: "hidden", timeout: 4500 });
  check("skip notice expires after 3 seconds");
  await page.locator("#player").evaluate((v) => {
    v.pause();
    v.currentTime = 24.5;
  });
  await page.waitForFunction(() => !document.getElementById("player").seeking);
  await page.locator("#share-button").click();
  const link = await page.locator("#share-link").inputValue();
  assert(link.includes("v=" + fixtures.voice_id) && link.includes("t=24.5"));
  const deep = await context.newPage();
  track(deep);
  await deep.goto(link);
  await deep.waitForFunction(() => {
    const v = document.getElementById("player");
    return v.readyState >= 2 && Math.abs(v.currentTime - 24.5) < 0.2;
  });
  assert((await state(deep)).paused);
  check(
    "copied deep link selects correct video and 24.5s while paused",
    await state(deep),
  );
  assert(await deep.locator("#smart-mode").isChecked());
  check("smart preference persists across new page");
  const special = `.video-entry[data-video-id="${fixtures.special_id}"]`;
  await page.locator(special + " summary").click();
  await page.locator(special + " .segment-jump").click();
  await page.waitForFunction(() => {
    const v = document.getElementById("player");
    return v.readyState >= 2 && v.videoWidth > 0 && v.duration < 9;
  });
  const specialState = await state(page);
  assert(
    specialState.src.includes("%23") &&
      specialState.src.includes("%25") &&
      specialState.src.includes("%20"),
  );
  check(
    "Chinese, spaces, hash and percent path decodes actual MP4",
    specialState,
  );
  const unsupported = `.video-entry[data-video-id="${fixtures.unsupported_id}"]`;
  await page.locator(unsupported + " summary").click();
  await page.locator(unsupported + " .segment-jump").click();
  await page.locator("#play-error").waitFor({ state: "visible" });
  assert((await page.locator("#error-path").textContent()).includes(".avi"));
  assert(await page.locator(unsupported + " .segment-jump").count());
  await shot(page, "unsupported-format");
  check("unsupported AVI shows path and keeps catalog");
  const blocked = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  await blocked.setOffline(true);
  await blocked.addInitScript(() => {
    Storage.prototype.getItem = () => {
      throw new DOMException("blocked", "SecurityError");
    };
    Storage.prototype.setItem = () => {
      throw new DOMException("blocked", "SecurityError");
    };
  });
  const restricted = await blocked.newPage();
  track(restricted);
  await voiceReady(restricted, 0);
  await restricted.locator("#smart-mode").check();
  await restricted.locator("#theme-toggle").click();
  assert.equal(await restricted.locator(".video-entry").count(), 6);
  check("storage denial leaves report and controls usable");
  assert.equal(evidence.dialogs.length, 0);
  assert.deepEqual(evidence.pageErrors, []);
  assert.deepEqual(evidence.externalRequests, []);
  check("offline file reports issue no external requests and no page errors");
  await blocked.close();
  await context.close();
  evidence.status = "passed";
})()
  .catch((err) => {
    evidence.status = "failed";
    evidence.error = String(err.stack || err);
    console.error(err);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
    fs.writeFileSync(
      path.join(logs, "browser-evidence.json"),
      JSON.stringify(evidence, null, 2),
    );
  });
