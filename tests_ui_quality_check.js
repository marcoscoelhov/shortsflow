const { chromium } = require('playwright');
const assert = require('assert');

const base = process.env.SHORTSFLOW_UI_BASE || 'http://127.0.0.1:8080';

async function visibleRect(locator) {
  return await locator.evaluate(el => {
    const r = el.getBoundingClientRect();
    return {x:r.x, y:r.y, width:r.width, height:r.height, bottom:r.bottom, visible: !!(r.width && r.height)};
  });
}

(async () => {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 390, height: 844}, deviceScaleFactor: 1});

  await page.goto(base + '/', {waitUntil: 'networkidle'});
  await page.getByRole('button', {name: /Novo Projeto|Criar/}).first().click();
  const createSubmit = page.locator('#create-job-modal button[type="submit"]').last();
  const r = await visibleRect(createSubmit);
  assert(r.visible && r.bottom <= 844, 'CTA Criar vídeo deve ficar visível no primeiro viewport mobile');
  await page.keyboard.press('Escape');

  await page.goto(base + '/calendar', {waitUntil: 'networkidle'});
  assert(await page.locator('.calendar-mobile-agenda').isVisible(), 'Calendário mobile deve mostrar agenda/lista, não só grade mensal');
  const calH = await page.evaluate(() => document.body.scrollHeight);
  assert(calH < 4300, `Calendário mobile alto demais: ${calH}`);

  await page.goto(base + '/library', {waitUntil: 'networkidle'});
  assert(await page.locator('.library-state-tabs').isVisible(), 'Biblioteca deve ter triagem por estado');
  const hasRawEnglish = await page.locator('text=/\b(consumed|batch|gate aprovado)\b/i').count();
  assert.strictEqual(hasRawEnglish, 0, 'UI não deve expor slugs/copy interna em inglês');

  await page.goto(base + '/', {waitUntil: 'networkidle'});
  const firstJobRow = page.locator('.job-row-card.jobs-grid-row').first();
  assert(await firstJobRow.getAttribute('data-href'), 'Card de job deve expor destino clicável');
  await firstJobRow.focus();
  await page.keyboard.press('Enter');
  await page.waitForURL(/\/jobs\//);
  assert(/\/jobs\//.test(new URL(page.url()).pathname), 'Enter no card do job deve abrir o detalhe');
  const discoveredJobUrl = page.url();

  await page.goto(base + '/', {waitUntil: 'networkidle'});
  const secondJobRow = page.locator('.job-row-card.jobs-grid-row').nth(1);
  assert(await secondJobRow.getAttribute('data-href'), 'Segundo card de job deve expor destino clicável');
  await secondJobRow.click({position: {x: 320, y: 96}});
  await page.waitForURL(/\/jobs\//);
  assert(/\/jobs\//.test(new URL(page.url()).pathname), 'Clique em área não textual do card deve abrir o detalhe');

  await page.goto(discoveredJobUrl, {waitUntil: 'networkidle'});
  assert(await page.locator('.job-local-nav').count(), 'Detalhe do job deve renderizar navegação local');
  assert(await page.locator('.job-mobile-tabs').isVisible(), 'Detalhe mobile deve ter abas por tarefa');
  const initialJobHeight = await page.evaluate(() => document.body.scrollHeight);
  assert(initialJobHeight < 4200, `Detalhe mobile inicial ainda está longo demais: ${initialJobHeight}`);
  await page.getByRole('tab', {name: /Técnico/}).click();
  const technicalPanel = page.locator('[data-job-panel="tecnico"]');
  assert(await technicalPanel.isVisible(), 'A aba Técnica deve revelar dados técnicos no mobile');
  const technicalRect = await visibleRect(technicalPanel);
  assert(technicalRect.y < 760, `Aba técnica deve trazer o conteúdo para perto do viewport: y=${technicalRect.y}`);
  const technicalJobHeight = await page.evaluate(() => document.body.scrollHeight);
  assert(technicalJobHeight < 4300, `Aba técnica mobile ainda está longa demais: ${technicalJobHeight}`);

  await page.getByRole('tab', {name: /Vídeo/}).click();
  const videoPanel = page.locator('[data-job-panel="video"]').first();
  const selectedVideoTab = await page.getByRole('tab', {name: /Vídeo/}).getAttribute('aria-selected');
  const videoRect = await visibleRect(videoPanel);
  assert.strictEqual(selectedVideoTab, 'true', 'Aba Vídeo deve selecionar o painel mobile correspondente');
  assert(videoRect.y < 760, `Aba Vídeo deve trazer o conteúdo para perto do viewport: y=${videoRect.y}`);

  await page.getByRole('tab', {name: /Qualidade/}).click();
  const qualityPanel = page.locator('[data-job-panel="qualidade"]');
  const selectedQualityTab = await page.getByRole('tab', {name: /Qualidade/}).getAttribute('aria-selected');
  const qualityRect = await visibleRect(qualityPanel);
  assert.strictEqual(selectedQualityTab, 'true', 'Aba Qualidade deve selecionar o painel mobile correspondente');
  assert(qualityRect.y < 760, `Aba Qualidade deve trazer o conteúdo para perto do viewport: y=${qualityRect.y}`);

  await page.setViewportSize({width: 1280, height: 900});
  await page.goto(discoveredJobUrl, {waitUntil: 'networkidle'});
  assert(await page.locator('.job-local-nav').isVisible(), 'Detalhe desktop deve ter navegação local sticky');
  await page.locator('.job-local-nav a[href="#video-final"]').click();
  assert.strictEqual(new URL(page.url()).hash, '#video-final', 'Navegação local desktop deve apontar para Vídeo');
  await page.locator('.job-local-nav a[href="#qualidade-job"]').click();
  assert.strictEqual(new URL(page.url()).hash, '#qualidade-job', 'Navegação local desktop deve apontar para Qualidade');

  await page.setViewportSize({width: 390, height: 844});
  await page.goto(discoveredJobUrl, {waitUntil: 'networkidle'});
  const emptyHeadings = await page.locator('h1,h2,h3,h4,h5,h6').evaluateAll(nodes => nodes.filter(n => !n.textContent.trim()).length);
  assert.strictEqual(emptyHeadings, 0, 'Detalhe não pode ter headings vazios');

  const smallInputs = await page.locator('input[type="checkbox"]').evaluateAll(nodes => nodes.filter(el => {
    const label = el.closest('label');
    const r = (label || el).getBoundingClientRect();
    const style = getComputedStyle(label || el);
    if (!r.width || !r.height || style.visibility === 'hidden' || style.display === 'none') return false;
    return r.width < 44 || r.height < 44;
  }).length);
  assert.strictEqual(smallInputs, 0, 'Checkboxes precisam de área clicável >=44px');

  await browser.close();
  console.log('ui quality checks passed');
})().catch(async (err) => { console.error(err.message); process.exit(1); });
