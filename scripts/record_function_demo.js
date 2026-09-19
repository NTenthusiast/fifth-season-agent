/* 录制真实网页交互：建档 → 匹配 → 交接包 → 唤醒。 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const outputDir = path.join(root, "docs", "video_assets", "demo");
const finalPath = path.join(outputDir, "功能演示.webm");
fs.mkdirSync(outputDir, { recursive: true });
if (fs.existsSync(finalPath)) fs.unlinkSync(finalPath);

async function banner(page, step, title, detail) {
  await page.evaluate(({ step, title, detail }) => {
    let el = document.getElementById("recording-callout");
    if (!el) {
      el = document.createElement("div");
      el.id = "recording-callout";
      Object.assign(el.style, {
        position: "fixed", top: "18px", left: "50%", transform: "translateX(-50%)",
        zIndex: "99999", padding: "10px 20px", borderRadius: "18px",
        background: "rgba(35,29,58,.92)", color: "white", boxShadow: "0 10px 34px rgba(40,30,80,.22)",
        fontFamily: "Microsoft YaHei, sans-serif", textAlign: "center", pointerEvents: "none",
      });
      document.body.appendChild(el);
    }
    el.innerHTML = `<b style="font-size:16px;color:#d9ccff">功能演示 ${step}/4</b>` +
      `<span style="font-size:16px;margin-left:12px">${title}</span>` +
      `<span style="font-size:13px;opacity:.78;margin-left:10px">${detail}</span>`;
  }, { step, title, detail });
}

async function waitReply(page) {
  await page.waitForFunction(() => {
    const btn = document.querySelector("#btn-send");
    return btn && btn.disabled;
  }, null, { timeout: 5000 });
  await page.waitForFunction(() => {
    const btn = document.querySelector("#btn-send");
    return btn && !btn.disabled;
  }, null, { timeout: 20000 });
  await page.waitForTimeout(500);
}

async function focusLatest(page) {
  await page.evaluate(() => {
    const starters = document.querySelector(".chat-starters");
    if (starters) starters.style.display = "none";
    const rows = Array.from(document.querySelectorAll("#chat-messages .bubble-row"));
    rows.forEach((row, index) => {
      row.style.display = index >= rows.length - 2 ? "flex" : "none";
    });
    const box = document.querySelector("#chat-messages");
    if (box) box.scrollTop = box.scrollHeight;
  });
}

async function typeAndSend(page, value) {
  const input = page.locator("#chat-input");
  await input.click();
  await input.pressSequentially(value, { delay: 22 });
  await page.waitForTimeout(500);
  await page.locator("#btn-send").click();
  await waitReply(page);
  await focusLatest(page);
  await page.waitForTimeout(2600);
}

(async () => {
  const browser = await chromium.launch({
    executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    recordVideo: { dir: outputDir, size: { width: 1600, height: 900 } },
  });
  const page = await context.newPage();
  const demoUrl = process.env.DEMO_URL || "http://127.0.0.1:8765/?view=chat";
  await page.goto(demoUrl, { waitUntil: "networkidle" });
  await page.waitForTimeout(1800);

  await banner(page, 1, "自然语言建档", "年级、专业、技能、兴趣与时间约束");
  await page.locator(".starter-card").first().click();
  await waitReply(page);
  await focusLatest(page);
  await page.waitForTimeout(2200);

  await banner(page, 2, "真实项目匹配", "检索项目库并解释为什么适合");
  await typeAndSend(page, "我是大二的小林，计算机专业，会前端开发和摄影，对无障碍校园感兴趣，每周可以投入三小时。");

  await banner(page, 3, "交接包五件套", "成果、经验、踩坑、遗留问题和资源");
  await typeAndSend(page, "请调出这个项目的完整交接包，让我看看前任留下了什么。 ");

  await banner(page, 4, "第五季唤醒", "确认接棒并写入传承记录");
  await typeAndSend(page, "我确认接棒，请帮我唤醒这个项目，并告诉我第一周做什么。 ");
  await page.waitForTimeout(2000);
  const finalRows = await page.locator("#chat-messages .bubble-row").evaluateAll((rows) =>
    rows.map((row) => ({ text: row.innerText.slice(0, 120), display: getComputedStyle(row).display }))
  );
  console.log(JSON.stringify(finalRows));
  await page.screenshot({ path: path.join(outputDir, "最终状态.png") });

  const video = page.video();
  await context.close();
  await browser.close();
  const rawPath = await video.path();
  if (path.resolve(rawPath) !== path.resolve(finalPath)) fs.renameSync(rawPath, finalPath);
  console.log(finalPath);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
