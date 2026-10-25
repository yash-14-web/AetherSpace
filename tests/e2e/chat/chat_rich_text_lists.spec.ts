import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-contributor-id', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});
}

test.describe('Chat Composer Rich-Text List Formatting', () => {

  test('bulleted and numbered lists create items, preserve markers, support Enter continuation, and render after reload', async ({ page }) => {
    await signIn(page);

    // Navigate to smart-classroom #general channel
    await page.goto('/chat/w/smart-classroom/c/general/');
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const editor = page.locator('.aether-chat-editor');
    await editor.click();

    // 1. Click Bulleted List button
    const bulletBtn = page.locator('button[title="Bulleted List"]').first();
    await expect(bulletBtn).toBeVisible();
    await bulletBtn.click();

    // Verify <ul> and <li> exist in the editor
    const editorUl = editor.locator('ul');
    await expect(editorUl).toBeVisible();
    const firstBulletLi = editorUl.locator('li').first();
    await expect(firstBulletLi).toBeVisible();

    // Verify list-style-type is disc in the composer editor
    const bulletStyle = await firstBulletLi.evaluate((el) => window.getComputedStyle(el).listStyleType);
    expect(bulletStyle).toBe('disc');

    // 2. Type first bullet and press Enter
    await page.keyboard.type('First automated bullet');
    await page.keyboard.press('Enter');

    // Verify Enter key did NOT submit the message and instead created a second <li>
    const bulletItems = editorUl.locator('li');
    await expect(bulletItems).toHaveCount(2);

    // Type second bullet
    await page.keyboard.type('Second automated bullet');

    // Press Enter to create empty item, then Enter again to exit list
    await page.keyboard.press('Enter');
    await page.keyboard.press('Enter');

    // 3. Click Numbered List button
    const numberBtn = page.locator('button[title="Numbered List"]').first();
    await numberBtn.click();

    // Verify <ol> exists in the editor
    const editorOl = editor.locator('ol');
    await expect(editorOl).toBeVisible();
    const firstNumLi = editorOl.locator('li').first();
    await expect(firstNumLi).toBeVisible();

    // Verify list-style-type is decimal in the composer editor
    const numStyle = await firstNumLi.evaluate((el) => window.getComputedStyle(el).listStyleType);
    expect(numStyle).toBe('decimal');

    // Type first numbered item, press Enter, type second numbered item
    await page.keyboard.type('Step One: Initialize');
    await page.keyboard.press('Enter');
    await expect(editorOl.locator('li')).toHaveCount(2);
    await page.keyboard.type('Step Two: Execute');

    // 4. Send the message
    const sendBtn = page.locator('button[type="submit"]:has-text("Send")').first();
    await sendBtn.click();

    // 5. Verify the sent message appears in .aether-message-content
    const sentMessage = page.locator('.aether-message-content', { hasText: 'First automated bullet' }).last();
    await expect(sentMessage).toBeVisible({ timeout: 10000 });

    // Verify rendered <ul> and <ol> in message stream
    const sentUl = sentMessage.locator('ul');
    await expect(sentUl).toBeVisible();
    await expect(sentUl.locator('li')).toHaveCount(2);
    await expect(sentUl.locator('li').first()).toHaveText('First automated bullet');

    const sentOl = sentMessage.locator('ol');
    await expect(sentOl).toBeVisible();
    await expect(sentOl.locator('li')).toHaveCount(2);
    await expect(sentOl.locator('li').first()).toHaveText('Step One: Initialize');
    await expect(sentOl.locator('li').nth(1)).toHaveText('Step Two: Execute');

    // Verify computed list markers in rendered stream
    const renderedBulletMarker = await sentUl.locator('li').first().evaluate((el) => window.getComputedStyle(el).listStyleType);
    expect(renderedBulletMarker).toBe('disc');
    const renderedNumMarker = await sentOl.locator('li').first().evaluate((el) => window.getComputedStyle(el).listStyleType);
    expect(renderedNumMarker).toBe('decimal');

    // 6. Reload page to verify database persistence & historical rendering
    await page.reload();
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const persistedMessage = page.locator('.aether-message-content', { hasText: 'First automated bullet' }).last();
    await expect(persistedMessage).toBeVisible();
    await expect(persistedMessage.locator('ul li')).toHaveCount(2);
    await expect(persistedMessage.locator('ol li')).toHaveCount(2);

    const persistedBulletMarker = await persistedMessage.locator('ul li').first().evaluate((el) => window.getComputedStyle(el).listStyleType);
    expect(persistedBulletMarker).toBe('disc');
    const persistedNumMarker = await persistedMessage.locator('ol li').first().evaluate((el) => window.getComputedStyle(el).listStyleType);
    expect(persistedNumMarker).toBe('decimal');
  });

  test('nested lists with Tab indent and formatted content inside items serialize and render accurately', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/w/smart-classroom/c/general/');
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const editor = page.locator('.aether-chat-editor');
    await editor.click();

    // 1. Click Bulleted List button
    const bulletBtn = page.locator('button[title="Bulleted List"]').first();
    await bulletBtn.click();

    // Type parent item
    await page.keyboard.type('Parent Category');
    await page.keyboard.press('Enter');

    // Press Tab to indent sub-item
    await page.keyboard.press('Tab');
    await page.keyboard.type('Child subcategory item');

    // Press Enter to create second sub-item
    await page.keyboard.press('Enter');
    await page.keyboard.type('Second subcategory');

    // Press Enter, then Shift+Tab to outdent new item back to parent level
    await page.keyboard.press('Enter');
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.type('Back to parent level');

    // Press Enter twice to exit list
    await page.keyboard.press('Enter');
    await page.keyboard.press('Enter');

    // 2. Type bullet with formatted bold and code content
    await bulletBtn.click();
    await page.keyboard.press('Control+b');
    await page.keyboard.type('Critical task:');
    await page.keyboard.press('Control+b');
    await page.keyboard.type(' run deploy script');

    // Send the message
    const sendBtn = page.locator('button[type="submit"]:has-text("Send")').first();
    await sendBtn.click();

    // Verify rendered message contains nested list structure
    const nestedMsg = page.locator('.aether-message-content', { hasText: 'Parent Category' }).last();
    await expect(nestedMsg).toBeVisible({ timeout: 10000 });

    // Check nested list element (ul inside li)
    const nestedUl = nestedMsg.locator('ul ul');
    await expect(nestedUl).toBeVisible();
    await expect(nestedUl.locator('li')).toHaveCount(2);
    await expect(nestedUl.locator('li').first()).toHaveText('Child subcategory item');

    // Check bold formatted item
    const formattedItem = page.locator('.aether-message-content', { hasText: 'Critical task:' }).last();
    await expect(formattedItem.locator('strong')).toHaveText('Critical task:');
  });

});

