const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const artifactDir = 'C:\\Users\\ADITI\\.gemini\\antigravity-ide\\brain\\ecad6a64-3674-48b9-a728-56e56bbb39c4\\screenshots';

async function run() {
  console.log('Launching Chrome for Phase 4 Security Screenshot verification...');
  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 1000));

  // Find Test 1: Cross-Patient Read button and click it
  console.log('Testing Cross-Patient Read...');
  const buttons = await page.$$('button');
  for (const b of buttons) {
    const text = await (await b.getProperty('innerText')).jsonValue();
    if (text && text.includes('Test 1: Cross-Patient Read')) {
      await b.click();
      await new Promise(r => setTimeout(r, 800));
      break;
    }
  }

  const dest1 = path.join(artifactDir, 'phase4_security_cross_patient_test.png');
  await page.screenshot({ path: dest1, fullPage: false });
  console.log('Saved:', dest1);

  // Click Test 2: Unverified Clinician Claim
  console.log('Testing Unverified Clinician Claim...');
  const buttons2 = await page.$$('button');
  for (const b of buttons2) {
    const text = await (await b.getProperty('innerText')).jsonValue();
    if (text && text.includes('Test 2: Unverified Clinician Claim')) {
      await b.click();
      await new Promise(r => setTimeout(r, 800));
      break;
    }
  }

  const dest2 = path.join(artifactDir, 'phase4_security_unverified_clinician_test.png');
  await page.screenshot({ path: dest2, fullPage: false });
  console.log('Saved:', dest2);

  await browser.close();
  console.log('Phase 4 security screenshots successfully captured!');
}

run().catch(err => {
  console.error('Error during screenshot capture:', err);
  process.exit(1);
});
