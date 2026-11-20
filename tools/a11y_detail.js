// Diagnostic only, never a verdict (KR-227): prints axe-core's own failure summary (foreground and background
// colours, ratio) for the colour-contrast errors of a few pages, because pa11y-ci's JSON drops those numbers.
// Uses the puppeteer and axe-core that `npx pa11y-ci@3.1.0` already installed: no other download.
//     node tools/a11y_detail.js NODE_MODULES_DIR URL [URL ...]
const nm = process.argv[2];
const paths = [nm + "/pa11y", nm];
const puppeteer = require(require.resolve("puppeteer", { paths }));
const axeSrc = require("fs").readFileSync(require.resolve("axe-core/axe.min.js", { paths }), "utf8");
(async () => {
  const browser = await puppeteer.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  for (const url of process.argv.slice(3)) {
    try {
      const page = await browser.newPage();
      await page.goto(url, { waitUntil: "load", timeout: 120000 });
      await new Promise((r) => setTimeout(r, 1500));
      await page.addScriptTag({ content: axeSrc });
      const lines = await page.evaluate(async () => {
        const res = await window.axe.run(document, { runOnly: ["color-contrast"] });
        return res.violations.flatMap((v) => v.nodes.slice(0, 4).map((n) =>
          n.target.join(" ") + " :: " + (n.failureSummary || "").replace(/\s+/g, " ")));
      });
      console.log(url + " (axe " + (await page.evaluate(() => window.axe.version)) + ")");
      lines.forEach((l) => console.log("  " + l));
      await page.close();
    } catch (e) {
      console.log(url + ": detail failed: " + e.message);
    }
  }
  await browser.close();
})().catch((e) => console.log("detail failed: " + e.message));
