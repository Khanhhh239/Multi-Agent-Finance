// Isolated pilot rehearsal; driven by rehearse_web.py with a fresh state directory.
const { chromium } = require("playwright");
const path = require("node:path");
const assert = require("node:assert/strict");
(async () => {
  const b = await chromium.launch({
    channel: process.env.AGENT1_BROWSER || "msedge",
    headless: true,
  });
  try {
    const page = await b.newPage({ viewport: { width: 1280, height: 720 } });
    page.setDefaultTimeout(25000);
    const errors = [];
    const shots = process.env.AGENT1_GUIDE_IMAGES;
    async function shot(name, selector) {
      if (!shots) return;
      require("node:fs").mkdirSync(shots, { recursive: true });
      await page.evaluate(() => document.fonts.ready);
      await page.locator(selector).first().screenshot({path:path.join(shots,name+".png"),animations:"disabled"});
    }
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(process.env.PILOT_TEST_URL + "/workspace");
    await page.locator("#connect-top").click();
    await shot("01-ket-noi","#connect-dialog");
    await page.locator("#token-input").fill(process.env.PILOT_TEST_TOKEN);
    await page.locator("#token-input").press("Enter");
    await page.locator("#connect-dialog").waitFor({ state: "hidden" });
    console.log("Connected");
    await page.locator("nav [data-view=data]").click();
    for (const kind of ["invoices", "bank", "statements", "outflows"]) {
      await page.locator("#table-kind").selectOption(kind);
      await page
        .locator("#import-file")
        .setInputFiles(path.resolve("pilot", "fixtures", kind + ".csv"));
      if(kind==="invoices") await shot("02-nap-file","#import-form");
      await page.locator("#import-form button[type=submit]").click();
      if(kind==="invoices") await shot("03-xem-truoc","#preview-panel");
      const committed = page.waitForResponse((r) =>
        r.url().endsWith("/commit"),
      );
      await page.locator("#commit-import").click();
      assert((await committed).ok());
      await page.locator("#preview-panel").waitFor({ state: "hidden" });
      console.log("Committed " + kind);
    }
    for (const [id, amount] of [
      ["30", 30000000],
      ["70", 70000000],
    ]) {
      for (const [field, v] of Object.entries({
        bank: "DEMO_BANK100",
        id: "P" + id,
        invoice: "DEMO_" + id,
        amount: String(amount),
      }))
        await page.locator("#allocate-" + field).fill(v);
      const ok = page.waitForResponse((r) => r.url().endsWith("/allocations"));
      await page.locator("#allocate-form button").click();
      assert((await ok).ok());
      if(shots && id==="30"){
        await page.locator("#pending-rows").getByText(/70\.000\.000/).first().waitFor();
        await shot("04-phan-bo","article:has(#allocate-form)");
      }
    }
    if(shots){
      await page.locator("nav [data-view=training]").click();
      await shot("05-kiem-dinh","#view-training .split-layout");
    }
    await page.locator("nav [data-view=forecast]").click();
    await page.locator("#forecast-cutoff").fill("2026-09-30");
    await page.locator("#opening-balance").fill("20000000");
    await page.locator("#forecast-complete").check();
    await shot("06-lap-ke-hoach","article:has(#forecast-form)");
    const forecast = page.waitForResponse((r) => r.url().endsWith("/predict"));
    await page.locator("#forecast-form button[type=submit]").click();
    const plan = await (await forecast).json();
    assert.equal(plan.weeks.length, 13);
    assert(plan.unknown_outflow_weeks.length > 0);
    if(shots){
      await page.locator("#forecast-chart canvas").first().waitFor();
      await shot("07-duong-tien","#forecast-chart");
      console.log("Guide week one:",JSON.stringify(plan.weeks[0]));
    }
    await page.locator("#saved-plans").click();
    await page.locator("#plans-list button").first().click();
    await page.locator("#actuals-date").fill("2026-10-31");
    const results = page.waitForResponse((r) => r.url().includes("/actuals?"));
    await page.locator("#compare-actuals").click();
    const truth = await (await results).json();
    assert.equal(truth.weeks[0].actual_balance, 120000000);
    await page.locator("#actuals-result table").waitFor();
    await shot("08-thuc-te","#actuals-result");
    await page.setViewportSize({ width: 390, height: 844 });
    await page
      .waitForFunction(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
        {},
        { timeout: 2500 },
      )
      .catch(async () => {
        throw new Error(
          "Mobile overflow: " +
            JSON.stringify(
              await page.evaluate(() =>
                Array.from(document.querySelectorAll("body *"))
                  .filter(
                    (e) =>
                      e.offsetWidth &&
                      e.getBoundingClientRect().right > innerWidth + 2 &&
                      !e.closest(".table-scroll"),
                  )
                  .map((e) => [
                    e.id || e.className || e.tagName,
                    Math.round(e.getBoundingClientRect().right),
                  ])
                  .slice(0, 18),
              ),
            ),
        );
      });
    assert.deepEqual(errors, []);
    console.log(
      "OK: CSV import, 30/70 allocation, forecast, history, actuals, mobile width, zero page errors.",
    );
  } finally {
    await b.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exitCode = 1;
});
