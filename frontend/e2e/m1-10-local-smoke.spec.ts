import { expect, test } from '@playwright/test';

const smokeQuery = '헬스장 계약 해지 환불 위약금';
const requireChatComplete = process.env.M1_10_REQUIRE_CHAT_COMPLETE === 'true';

test.describe('M1-10 local frontend smoke', () => {
  test('proxies health and search through the frontend origin', async ({ request }) => {
    const health = await request.get('/health');
    expect(health.status()).toBe(200);
    const healthPayload = await health.json();
    expect(healthPayload).toMatchObject({ status: 'healthy', database: 'connected' });

    const search = await request.post('/search', {
      data: { query: smokeQuery, top_k: 3 },
    });
    expect(search.status()).toBe(200);
    const searchPayload = await search.json();
    expect(searchPayload.query).toBe(smokeQuery);
    expect(searchPayload.results_count).toBeGreaterThan(0);
    expect(searchPayload.results.length).toBeGreaterThan(0);

    console.log(
      'm1-10 frontend-origin search:',
      JSON.stringify({
        results_count: searchPayload.results_count,
        top_results: searchPayload.results.slice(0, 3).map((item: Record<string, unknown>) => ({
          chunk_id: item.chunk_id,
          doc_id: item.doc_id,
          doc_type: item.doc_type,
          chunk_type: item.chunk_type,
          similarity: item.similarity,
        })),
      })
    );
  });

  test('renders /chat and sends a UI-initiated streaming chat request', async ({ page }) => {
    test.setTimeout(180_000);
    const consoleErrors: string[] = [];

    page.on('console', (message) => {
      if (message.type() === 'error') {
        consoleErrors.push(message.text());
      }
    });

    await page.goto('/chat');
    await expect(page.getByRole('heading', { name: 'AI 상담 챗봇' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '일반 상담' })).toBeVisible();

    const input = page.getByPlaceholder('질문을 입력하세요...');
    await expect(input).toBeVisible();

    const streamResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/chat/stream') && response.request().method() === 'POST',
      { timeout: 30_000 }
    );

    await input.fill(smokeQuery);
    await input.press('Enter');

    const streamResponse = await streamResponsePromise;
    expect(streamResponse.status()).toBe(200);

    const streamBody = await streamResponse.text();
    const hasCompleteEvent = /"type"\s*:\s*"complete"/.test(streamBody);
    const hasErrorEvent = /"type"\s*:\s*"error"/.test(streamBody);

    console.log(
      'm1-10 chat stream:',
      JSON.stringify({
        status: streamResponse.status(),
        hasCompleteEvent,
        hasErrorEvent,
        bodyBytes: Buffer.byteLength(streamBody, 'utf8'),
      })
    );

    if (requireChatComplete) {
      expect(hasCompleteEvent).toBe(true);
    } else {
      expect(hasCompleteEvent || hasErrorEvent).toBe(true);
    }

    await expect(input).toBeEnabled({ timeout: 30_000 });

    const unexpectedErrors = consoleErrors.filter(
      (text) => !text.includes('favicon') && !text.includes('[vite]')
    );
    expect(unexpectedErrors).toEqual([]);
  });
});
