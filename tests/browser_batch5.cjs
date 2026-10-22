const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const assert = require("node:assert/strict");
const root = process.argv[2];
if (!root)
  throw Error("Usage: node tests/browser_batch5.cjs <test-media-folder>");
const repo = path.resolve(__dirname, "..");
const fixture = JSON.parse(
  fs.readFileSync(
    path.join(root, ".studylens/logs/batch3/fixture-paths.json"),
    "utf8",
  ),
);
const evidence = { checks: [], pageErrors: [], externalRequests: [] };
const log = path.join(root, ".studylens/logs/batch5");
fs.mkdirSync(log, { recursive: true });
let browser;
function check(name) {
  evidence.checks.push(name);
  console.log("PASS " + name);
}
(async () => {
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.STUDYLENS_BROWSER_EXECUTABLE || undefined,
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
  });
  await context.setOffline(true);
  const page = await context.newPage();
  page.on("pageerror", (e) => evidence.pageErrors.push(String(e)));
  page.on("request", (r) => {
    if (/^https?:/.test(r.url())) evidence.externalRequests.push(r.url());
  });
  await page.goto(
    pathToFileURL(fixture.real_report).href + `#v=${fixture.voice_id}&t=47`,
  );
  await page.waitForFunction(() => {
    const v = document.querySelector("#player");
    return v.readyState >= 2 && Math.abs(v.currentTime - 47) < 0.3;
  });
  const data = (await page.locator("#studylens-data").count())
    ? await page.locator("#studylens-data").textContent()
    : await page.locator('script[type="application/json"]').textContent();
  const videos = JSON.parse(data).videos;
  const ids = () =>
    page
      .locator(".video-entry")
      .evaluateAll((nodes) => nodes.map((n) => n.dataset.videoId));
  const sorted = videos
    .map((v, i) => ({ v, i }))
    .sort((a, b) => b.v.relevance - a.v.relevance || a.i - b.i)
    .map((x) => x.v.id);
  assert.deepEqual(await ids(), sorted);
  check("default relevance descending, stable ties");
  await page.locator("#catalog-order").selectOption("original");
  assert.deepEqual(
    await ids(),
    videos.map((v) => v.id),
  );
  check("original manifest order");
  await page.locator("#catalog-order").selectOption("relevance");
  await page.locator("#search").fill("学习");
  const subset = await ids();
  assert.deepEqual(
    subset,
    sorted.filter((id) => subset.includes(id)),
  );
  await page.locator("#search").fill("");
  check("filter preserves relevance order");
  assert.equal(
    await page.locator("#player").evaluate((v) => v.controls),
    false,
  );
  assert.equal(await page.locator("#seek-bar").count(), 1);
  check("single custom control bar");
  const voice = videos.find((v) => v.id === fixture.voice_id);
  const target = voice.segments.length > 2 ? 2 : voice.segments.length - 1;
  const block = page.locator(
    `#seek-strip button[data-segment-index="${target}"]`,
  );
  assert.equal(
    await page.locator("#seek-strip button").count(),
    voice.segments.length,
  );
  await block.hover();
  await page.locator("#strip-tip").waitFor({ state: "visible" });
  assert(
    (await page.locator("#strip-tip").textContent()).includes(
      voice.segments[target].title,
    ),
  );
  await block.click();
  await page.waitForFunction(
    (start) =>
      Math.abs(document.querySelector("#player").currentTime - start) < 0.5,
    voice.segments[target].start,
  );
  assert.equal(await block.evaluate((n) => n.classList.contains("active")), true);
  await page.locator("#player").evaluate((v) => v.pause());
  check("segment strip shows title on hover and jumps on click");
  await page.locator("#volume").fill("0.35");
  assert.equal(await page.locator("#player").evaluate((v) => v.volume), 0.35);
  await page.locator("#mute-toggle").click();
  assert.equal(await page.locator("#player").evaluate((v) => v.muted), true);
  assert.equal(
    await page.locator("#mute-toggle").getAttribute("aria-pressed"),
    "true",
  );
  await page.locator("#mute-toggle").click();
  assert.equal(await page.locator("#player").evaluate((v) => v.muted), false);
  check("volume and mute roundtrip");
  await page.locator("#player").evaluate((v) => {
    v.volume = 0.6;
    v.muted = true;
  });
  await page.waitForFunction(
    () =>
      document.querySelector("#volume").value === "0.6" &&
      document.querySelector("#mute-toggle").getAttribute("aria-label") ===
        "取消静音",
  );
  check("native volume state reflected in controls");
  await page.locator("#fullscreen-toggle").click();
  await page.waitForFunction(
    () => document.fullscreenElement?.id === "player-panel",
  );
  assert.equal(
    await page.locator("#player").evaluate((v) => v.controls),
    false,
  );
  await page.locator("#fullscreen-toggle").click();
  await page.waitForFunction(() => !document.fullscreenElement);
  check("enter and exit fullscreen with custom controls");
  await page.evaluate(() => {
    document.querySelector("#player-panel").requestFullscreen = () =>
      Promise.reject(Error("denied"));
  });
  await page.locator("#fullscreen-toggle").click();
  await page.waitForFunction(() =>
    document
      .querySelector("#control-status")
      .textContent.includes("不支持全屏"),
  );
  check("fullscreen rejection has visible fallback");
  assert(
    !(await page.locator("body").innerText()).includes("LOCAL LEARNING NOTES"),
  );
  check("Chinese header");
  for (const width of [390, 720, 1050]) {
    await page.setViewportSize({ width, height: 844 });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
  }
  check("controls fit mobile and tablet");
  await page.locator("#control-status").evaluate((n) => (n.textContent = ""));
  await page
    .locator("#share-link")
    .evaluate(
      (n) => (n.value = "file:///本地课程/studylens-report.html#v=课程&t=47"),
    );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: path.join(repo, "examples/screenshots/release-controls-mobile.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.screenshot({
    path: path.join(repo, "examples/screenshots/release-controls.png"),
    fullPage: true,
  });
  assert.deepEqual(evidence.pageErrors, []);
  assert.deepEqual(evidence.externalRequests, []);
  check("offline without JS errors or external requests");
  evidence.status = "passed";
})()
  .catch((e) => {
    evidence.status = "failed";
    evidence.error = String(e.stack);
    process.exitCode = 1;
    console.error(e);
  })
  .finally(async () => {
    if (browser) await browser.close();
    fs.writeFileSync(
      path.join(log, "browser-evidence.json"),
      JSON.stringify(evidence, null, 2),
    );
  });
