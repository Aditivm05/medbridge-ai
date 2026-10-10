const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const artifactDir = 'C:\\Users\\ADITI\\.gemini\\antigravity-ide\\brain\\ecad6a64-3674-48b9-a728-56e56bbb39c4\\screenshots';

if (!fs.existsSync(artifactDir)) {
  fs.mkdirSync(artifactDir, { recursive: true });
}

async function run() {
  console.log('Launching Chrome via puppeteer-core...');
  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
  });

  const page = await browser.newPage();

  const screens = [
    { name: '1_patient_dashboard', buttonText: '1. Dashboard' },
    { name: '2_intake_screen', buttonText: '2. Intake' },
    { name: '3_document_upload', buttonText: '3. Upload' },
    { name: '4_doctor_brief_review', buttonText: '4. Doctor Brief' },
    { name: '5_clinician_dashboard', buttonText: '5. Clinician Pool' },
    { name: '6_consultation_workspace', buttonText: '6. Consultation' },
    { name: '7_follow_up', buttonText: '7. Follow-Up' },
  ];

  // Helper to click workflow button by text
  async function navigateToScreen(btnText) {
    const buttons = await page.$$('button');
    for (const b of buttons) {
      const text = await (await b.getProperty('innerText')).jsonValue();
      if (text && text.includes(btnText)) {
        await b.click();
        await new Promise(r => setTimeout(r, 600));
        return true;
      }
    }
    return false;
  }

  // 1. DESKTOP VIEWPORTS (1280x800)
  console.log('\n--- Capturing Desktop Viewports (1280x800) ---');
  await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 });
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 1000));

  for (const s of screens) {
    console.log(`Navigating to ${s.name} (desktop)...`);
    await navigateToScreen(s.buttonText);
    const dest = path.join(artifactDir, `desktop_${s.name}.png`);
    await page.screenshot({ path: dest, fullPage: false });
    console.log(`Saved: ${dest}`);
  }

  // 2. MOBILE VIEWPORTS (360x740)
  console.log('\n--- Capturing Mobile Viewports (360x740) ---');
  await page.setViewport({ width: 360, height: 740, deviceScaleFactor: 1, isMobile: true });
  await page.reload({ waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 1000));

  for (const s of screens) {
    console.log(`Navigating to ${s.name} (mobile 360px)...`);
    await navigateToScreen(s.buttonText);
    const dest = path.join(artifactDir, `mobile_${s.name}.png`);
    await page.screenshot({ path: dest, fullPage: false });
    console.log(`Saved: ${dest}`);
  }

  await browser.close();
  console.log('\nAll 14 screenshots (7 desktop + 7 mobile) successfully generated!');
}

run().catch(err => {
  console.error('Error during screenshot capture:', err);
  process.exit(1);
});
