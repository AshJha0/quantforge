// Diagnostic only, never a verdict (KR-227): prints axe-core's own failure summary (foreground and background
// colours, ratio, or why axe could not decide) for the colour-contrast errors of a few pages, because pa11y-ci's
// JSON drops those details; pa11y 6.2.3 reports axe "incomplete" results of serious or unknown impact as errors.
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
      await page.setViewport({ width: 1280, height: 1024 });
      await page.goto(url, { waitUntil: "load", timeout: 120000 });
      await new Promise((r) => setTimeout(r, 1500));
      await page.addScriptTag({ content: axeSrc });
      const lines = await page.evaluate(async () => {
        const res = await window.axe.run(document, { runOnly: ["color-contrast"] });
        const show = (kind, list) => list.flatMap((v) => (v.error ? [kind + " rule error: " + String(v.error.message || v.error)] : [])
          .concat(v.nodes.slice(0, 4).map((n) => kind + " " + n.target.join(" ") + " :: " +
            (n.failureSummary || "").replace(/\s+/g, " ") + " " +
            JSON.stringify(((n.any || [])[0] || {}).data || {}).slice(0, 200))));
        return show("violation", res.violations).concat(show("incomplete", res.incomplete));
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
