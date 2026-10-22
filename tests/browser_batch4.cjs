const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const assert = require("node:assert/strict");
const repo = path.resolve(__dirname, "..");
const media = process.argv[2];
if (!media)
  throw new Error("Usage: node tests/browser_batch4.cjs <test-media-folder>");
const logs = path.join(media, ".studylens", "logs", "batch4");
fs.mkdirSync(logs, { recursive: true });
const fixtures = JSON.parse(
  fs.readFileSync(
    path.join(media, ".studylens", "logs", "batch3", "fixture-paths.json"),
    "utf8",
  ),
);
const evidence = { status: "running", checks: [], pageErrors: [] };
let browser;
(async () => {
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.STUDYLENS_BROWSER_EXECUTABLE || undefined,
    args: ["--autoplay-policy=no-user-gesture-required"],
  });
  evidence.browserVersion = browser.version();
  for (const [width, reducedMotion] of [
    [390, "reduce"],
    [720, "reduce"],
    [1050, "reduce"],
    [1051, "reduce"],
    [390, "no-preference"],
  ]) {
    const context = await browser.newContext({
      viewport: { width, height: 844 },
      reducedMotion,
    });
    await context.setOffline(true);
    await context.addInitScript(() => {
      window.studyLensScrollCalls = [];
      const original = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (options) {
        if (this.id === "player-panel")
          window.studyLensScrollCalls.push(options);
        return original.call(this, options);
      };
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => evidence.pageErrors.push(String(error)));
    await page.goto(
      pathToFileURL(fixtures.real_report).href +
        "#v=" +
        fixtures.voice_id +
        "&t=0",
    );
    await page.waitForFunction(
      () => document.getElementById("player").readyState >= 2,
    );
    await page.locator("#player").evaluate((v) => (v.muted = true));
    await page
      .locator(
        `.segment-jump[data-video-id="${fixtures.voice_id}"][data-segment-index="2"]`,
      )
      .click();
    if (width <= 1050) {
      await page.waitForFunction(() => window.studyLensScrollCalls.length > 0);
      await page.waitForFunction(() => {
        const top = document
          .getElementById("player-panel")
          .getBoundingClientRect().top;
        return top >= -2 && top <= 26;
      });
      const calls = await page.evaluate(() => window.studyLensScrollCalls);
      assert.equal(
        calls[0].behavior,
        reducedMotion === "reduce" ? "auto" : "smooth",
      );
      if (width === 390 && reducedMotion === "reduce") {
        await page.waitForFunction(() => {
          const video = document.getElementById("player");
          return (
            !video.seeking && video.readyState >= 3 && video.videoWidth > 0
          );
        });
        await page
          .locator("#share-link")
          .evaluate(
            (n) => (n.value = "file:///本地课程/studylens-report.html"),
          );
        await page.screenshot({
          path: path.join(
            repo,
            "examples",
            "screenshots",
            "mobile-after-click.png",
          ),
        });
      }
      evidence.checks.push({
        width,
        reducedMotion,
        action: "segment",
        calls,
        playerTop: await page
          .locator("#player-panel")
          .evaluate((e) => e.getBoundingClientRect().top),
      });
      await page.evaluate(() => {
        window.studyLensScrollCalls = [];
      });
      await page.locator(".path-step").first().click();
      await page.waitForFunction(() => window.studyLensScrollCalls.length > 0);
      evidence.checks.push({
        width,
        reducedMotion,
        action: "learning_path",
        calls: await page.evaluate(() => window.studyLensScrollCalls),
      });
    } else {
      assert.equal(
        (await page.evaluate(() => window.studyLensScrollCalls)).length,
        0,
      );
      evidence.checks.push({
        width,
        reducedMotion,
        action: "desktop_no_forced_scroll",
        calls: [],
      });
    }
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await context.close();
  }
  assert.deepEqual(evidence.pageErrors, []);
  evidence.status = "passed";
  console.log(
    "PASS responsive scroll:",
    evidence.checks.length,
    "checks, including 1050/1051 boundary and reduced motion",
  );
})()
  .catch((error) => {
    evidence.status = "failed";
    evidence.error = String(error.stack || error);
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
    fs.writeFileSync(
      path.join(logs, "browser-scroll-evidence.json"),
      JSON.stringify(evidence, null, 2),
    );
  });
