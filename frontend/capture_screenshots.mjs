import { chromium } from 'playwright';
import { spawn } from 'child_process';
import { existsSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = resolve(__dirname, '..');
const SCREENSHOTS_DIR = resolve(ROOT_DIR, 'screenshots');

if (!existsSync(SCREENSHOTS_DIR)) {
  mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function run() {
  console.log('--- Starting Backend Server on port 8120 ---');
  const backend = spawn('uv', ['run', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8120'], {
    cwd: resolve(ROOT_DIR, 'backend'),
    env: { ...process.env, PYTHONPATH: '.' },
    stdio: 'ignore'
  });

  console.log('--- Starting Frontend Server on port 3120 ---');
  const frontend = spawn('pnpm', ['start', '-p', '3120'], {
    cwd: resolve(ROOT_DIR, 'frontend'),
    stdio: 'ignore'
  });

  // Give servers time to boot
  console.log('Waiting 8s for servers to warm up...');
  await sleep(8000);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2
  });

  const page = await context.newPage();

  try {
    console.log('Navigating to http://localhost:3120...');
    await page.goto('http://localhost:3120', { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(2000);

    // 1. Initial Landing Page (Step 1 Onboarding)
    console.log('Capturing 01_landing_initial.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '01_landing_initial.png'), fullPage: false });

    // 2. Adjust parameters in Step 1 (e.g. toggle market dislocation or change AUM)
    console.log('Configuring presets...');
    const dislocationSwitch = page.locator('button[role="switch"]').first();
    if (await dislocationSwitch.count() > 0) {
      await dislocationSwitch.click();
      await sleep(1000);
    }
    console.log('Capturing 02_preset_configured.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '02_preset_configured.png'), fullPage: false });

    // Click Proceed to Step 2 Workspace
    const proceedBtn = page.locator('button:has-text("Proceed to Simulation Cockpit")').first();
    if (await proceedBtn.count() > 0) {
      await proceedBtn.click();
      await sleep(1500);
    }

    // 3. Workspace Idle
    console.log('Capturing 03_workspace_idle.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '03_workspace_idle.png'), fullPage: false });

    // 4. Run Scenario A (Golden Path / Positive Cleared)
    console.log('Executing Scenario A...');
    const scenABtn = page.locator('button:has-text("SCEN-A")').first();
    if (await scenABtn.count() > 0) {
      await scenABtn.click();
      await sleep(1000);
    }
    const runBtn = page.locator('button:has-text("Run Outflow Stress Simulation")').first();
    if (await runBtn.count() > 0) {
      await runBtn.click();
      await sleep(3000);
    }
    console.log('Capturing 04_scenario_positive_cleared.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '04_scenario_positive_cleared.png'), fullPage: false });

    // 5. Run Scenario C (Breach / Negative Blocked or Heavy Swing)
    console.log('Executing Scenario C...');
    const scenCBtn = page.locator('button:has-text("SCEN-C")').first();
    if (await scenCBtn.count() > 0) {
      await scenCBtn.click();
      await sleep(1000);
    }
    if (await runBtn.count() > 0) {
      await runBtn.click();
      await sleep(3000);
    }
    console.log('Capturing 05_scenario_negative_blocked.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '05_scenario_negative_blocked.png'), fullPage: false });

    // 6. Switch to PII Redaction Tab / PII Sandbox View
    console.log('Switching to PII Data Protection Tab...');
    const piiTab = page.locator('button[role="tab"]:has-text("1. Data Protection")').first();
    if (await piiTab.count() > 0) {
      await piiTab.click();
      await sleep(1000);
    }
    console.log('Capturing 06_scenario_negative_pii_redacted.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '06_scenario_negative_pii_redacted.png'), fullPage: false });

    // 7. Switch to Statutory Guardrails (CEL Engine) Tab
    console.log('Switching to Statutory Guardrails Tab...');
    const celTab = page.locator('button[role="tab"]:has-text("2. Statutory Guardrails")').first();
    if (await celTab.count() > 0) {
      await celTab.click();
      await sleep(1000);
    }
    console.log('Capturing 07_scenario_held_human_review.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '07_scenario_held_human_review.png'), fullPage: false });

    // 8. Audit Trace & Historical Ledger
    console.log('Switching to Stress Liquidation / Overview Tab for Audit...');
    const mathTab = page.locator('button[role="tab"]:has-text("3. Stress Liquidation")').first();
    if (await mathTab.count() > 0) {
      await mathTab.click();
      await sleep(1000);
    }
    console.log('Capturing 08_audit_trace_expanded.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '08_audit_trace_expanded.png'), fullPage: false });

    // 9. Dark Mode View
    console.log('Capturing 09_dark_mode_view.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '09_dark_mode_view.png'), fullPage: false });

    // 10. Switch to Light Mode
    console.log('Switching to Light Mode...');
    const themeToggle = page.locator('header button').last();
    if (await themeToggle.count() > 0) {
      await themeToggle.click();
      await sleep(1500);
    }
    console.log('Capturing 10_light_mode_view.png');
    await page.screenshot({ path: resolve(SCREENSHOTS_DIR, '10_light_mode_view.png'), fullPage: false });

    console.log('--- All 10 screenshots captured successfully! ---');
  } catch (err) {
    console.error('Error during screenshot capture:', err);
  } finally {
    await browser.close();
    backend.kill('SIGKILL');
    frontend.kill('SIGKILL');
    process.exit(0);
  }
}

run();
