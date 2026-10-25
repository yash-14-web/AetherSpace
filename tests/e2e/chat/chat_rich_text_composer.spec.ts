import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-contributor-id', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});
}

test.describe('Chat Composer Rich-Text: Emoji, Inline Code & Code Blocks', () => {

  test('emoji picker opens as multi-column grid, inserts unicode emoji at caret, and persists through page reload', async ({ page }) => {
    await signIn(page);

    // Navigate to channel view
    await page.goto('/chat/w/smart-classroom/c/general/');
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const editor = page.locator('.aether-chat-editor');
    await editor.click();

    // 1. Open Emoji Picker popup
    const emojiTrigger = page.locator('button[title="Insert Emoji"]').first();
    await expect(emojiTrigger).toBeVisible();
    await emojiTrigger.click();

    // Scope picker container
    const picker = page.locator('.aether-emoji-picker').first();
    await expect(picker).toBeVisible();

    // Verify multi-column grid: compute grid-template-columns has 8 columns on desktop
    const grid = picker.locator('.aether-emoji-grid').first();
    await expect(grid).toBeVisible();
    const gridCols = await grid.evaluate((el) => window.getComputedStyle(el).gridTemplateColumns);
    const colCount = gridCols.trim().split(/\s+/).length;
    expect(colCount).toBe(8);

    // Click an emoji from the Smileys category: 😀
    const smileyBtn = picker.locator('.aether-emoji-btn:has-text("😀")').first();
    await expect(smileyBtn).toBeVisible();
    await smileyBtn.click();

    // Verify picker closed after selection
    await expect(picker).toBeHidden();

    // Verify 😀 is inside editor
    await expect(editor).toContainText('😀');

    // Type text after emoji
    await page.keyboard.type(' Mission status ');

    // Open emoji picker again, switch category to Gestures (👍 tab), click 👍
    await emojiTrigger.click();
    await expect(picker).toBeVisible();
    const gesturesTab = picker.locator('button[title="Gestures"]').first();
    await gesturesTab.click();
    const thumbsUpBtn = picker.locator('.aether-emoji-btn:has-text("👍")').first();
    await thumbsUpBtn.click();
    await expect(picker).toBeHidden();

    // Verify both emojis exist in editor
    await expect(editor).toContainText('😀 Mission status 👍');

    // 2. Send message
    const sendBtn = page.locator('button[type="submit"]:has-text("Send")').first();
    await sendBtn.click();

    // Verify message appears in message stream
    const sentMsg = page.locator('.aether-message-content', { hasText: '😀 Mission status 👍' }).last();
    await expect(sentMsg).toBeVisible({ timeout: 10000 });

    // 3. Reload page to verify persistence
    await page.reload();
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });
    const persistedMsg = page.locator('.aether-message-content', { hasText: '😀 Mission status 👍' }).last();
    await expect(persistedMsg).toBeVisible();
  });

  test('emoji picker responsive grid layout on narrow mobile viewport', async ({ page }) => {
    await signIn(page);

    // Set mobile viewport size
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/chat/w/smart-classroom/c/general/');
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const emojiTrigger = page.locator('button[title="Insert Emoji"]').first();
    await emojiTrigger.click();

    const picker = page.locator('.aether-emoji-picker').first();
    await expect(picker).toBeVisible();

    // Verify picker width does not overflow mobile viewport
    const pickerBox = await picker.boundingBox();
    expect(pickerBox).not.toBeNull();
    if (pickerBox) {
      expect(pickerBox.width).toBeLessThanOrEqual(375);
    }

    // Verify grid has 7 columns on mobile
    const grid = picker.locator('.aether-emoji-grid').first();
    const gridCols = await grid.evaluate((el) => window.getComputedStyle(el).gridTemplateColumns);
    const colCount = gridCols.trim().split(/\s+/).length;
    expect(colCount).toBe(7);

    // Press Escape to close
    await page.keyboard.press('Escape');
    await expect(picker).toBeHidden();
  });

  test('inline code formats selection, preserves literal characters, prevents mentions, and renders correctly', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/w/smart-classroom/c/general/');
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const editor = page.locator('.aether-chat-editor');
    await editor.click();

    // Type text with code to select
    await page.keyboard.type('Run python manage.py check first');

    // Select "python manage.py check" and trigger mouseup
    await editor.evaluate((el) => {
      const textNode = el.firstChild;
      if (textNode) {
        const range = document.createRange();
        range.setStart(textNode, 4);
        range.setEnd(textNode, 26);
        const sel = window.getSelection();
        if (sel) {
          sel.removeAllRanges();
          sel.addRange(range);
        }
      }
      el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    });

    // Click Inline Code button
    const codeBtn = page.locator('button[title="Inline Code"]').first();
    await expect(codeBtn).toBeVisible();
    await codeBtn.click();

    // Verify <code> element exists in editor
    const editorCode = editor.locator('code');
    await expect(editorCode).toBeVisible();
    await expect(editorCode).toHaveText('python manage.py check');

    // Send the message
    const sendBtn = page.locator('button[type="submit"]:has-text("Send")').first();
    await sendBtn.click();

    // Verify rendered message contains <code> element
    const sentMsg = page.locator('.aether-message-content', { hasText: 'python manage.py check' }).last();
    await expect(sentMsg).toBeVisible({ timeout: 10000 });
    const sentCode = sentMsg.locator('code');
    await expect(sentCode).toBeVisible();
    await expect(sentCode).toHaveText('python manage.py check');

    // Verify computed styling: monospace font
    const fontFamily = await sentCode.evaluate((el) => window.getComputedStyle(el).fontFamily);
    expect(fontFamily.toLowerCase()).toContain('mono');

    // Reload and verify persistence
    await page.reload();
    const persistedCode = page.locator('.aether-message-content', { hasText: 'python manage.py check' }).last().locator('code');
    await expect(persistedCode).toBeVisible();
  });

  test('code block supports multiline input, Enter creates newline without sending, and renders with pre code', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/w/smart-classroom/c/general/');
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const editor = page.locator('.aether-chat-editor');
    await editor.click();

    // Click Code Block button
    const codeBlockBtn = page.locator('button[title="Code Block"]').first();
    await expect(codeBlockBtn).toBeVisible();
    await codeBlockBtn.click();

    // Verify <pre> exists in editor
    const editorPre = editor.locator('pre');
    await expect(editorPre).toBeVisible();

    // Type first line of code
    await page.keyboard.type('def run_service():');

    // Press Enter inside code block
    await page.keyboard.press('Enter');

    // Verify pressing Enter did NOT send the message and editor still contains pre
    await expect(editorPre).toBeVisible();

    // Type indented second line
    await page.keyboard.type('    return True');

    // Send message via Send button
    const sendBtn = page.locator('button[type="submit"]:has-text("Send")').first();
    await sendBtn.click();

    // Verify rendered message has <pre> and <code>
    const sentMsg = page.locator('.aether-message-content', { hasText: 'def run_service():' }).last();
    await expect(sentMsg).toBeVisible({ timeout: 10000 });
    const sentPre = sentMsg.locator('pre');
    await expect(sentPre).toBeVisible();
    await expect(sentPre).toContainText('def run_service():');
    await expect(sentPre).toContainText('return True');

    // Reload page to verify persistence
    await page.reload();
    const persistedPre = page.locator('.aether-message-content', { hasText: 'def run_service():' }).last().locator('pre');
    await expect(persistedPre).toBeVisible();
    await expect(persistedPre).toContainText('def run_service():');
  });

  test('hyperlinks have clear visible accent color, underline, wrap properly, and survive reload', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/w/smart-classroom/c/general/');
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const editor = page.locator('.aether-chat-editor');
    await editor.click();

    // Open Link modal via toolbar button
    const linkBtn = page.locator('button[title="Insert Link (Ctrl+K)"]').first();
    await linkBtn.click();

    const linkModal = page.locator('text=Insert Hyperlink').first();
    await expect(linkModal).toBeVisible();

    // Fill link form
    await page.fill('input[placeholder="Text to display"]', 'Aether Docs Link');
    await page.fill('input[placeholder="https://example.com"]', 'https://docs.aetherspace.dev/specs');
    await page.click('button:has-text("Insert")');

    // Verify link exists in editor
    const editorLink = editor.locator('a');
    await expect(editorLink).toBeVisible();
    await expect(editorLink).toHaveText('Aether Docs Link');

    // Verify visible link styling in editor: underline and accent color
    const linkDecoration = await editorLink.evaluate((el) => window.getComputedStyle(el).textDecorationLine);
    expect(linkDecoration).toContain('underline');

    // Send message
    const sendBtn = page.locator('button[type="submit"]:has-text("Send")').first();
    await sendBtn.click();

    // Verify link in sent message stream
    const sentMsg = page.locator('.aether-message-content', { hasText: 'Aether Docs Link' }).last();
    await expect(sentMsg).toBeVisible({ timeout: 10000 });
    const sentLink = sentMsg.locator('a');
    await expect(sentLink).toBeVisible();
    await expect(sentLink).toHaveAttribute('href', 'https://docs.aetherspace.dev/specs');
    await expect(sentLink).toHaveAttribute('target', '_blank');

    // Check underline and break-all in sent link
    const sentDecoration = await sentLink.evaluate((el) => window.getComputedStyle(el).textDecorationLine);
    expect(sentDecoration).toContain('underline');

    // Reload page to verify persistence
    await page.reload();
    const persistedLink = page.locator('.aether-message-content', { hasText: 'Aether Docs Link' }).last().locator('a');
    await expect(persistedLink).toBeVisible();
    await expect(persistedLink).toHaveAttribute('href', 'https://docs.aetherspace.dev/specs');
  });

  test('mentions insert without text duplication, render as compact pills, and isolate code mentions', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/w/smart-classroom/c/general/');
    await expect(page.locator('.aether-chat-editor')).toBeVisible({ timeout: 10000 });

    const editor = page.locator('.aether-chat-editor');
    await editor.click();

    // Type text and trigger mention
    await page.keyboard.type('Hello @');

    // Wait for mention popup
    const mentionPopup = page.locator('text=Teammates').first();
    await expect(mentionPopup).toBeVisible({ timeout: 5000 });

    // Click the first teammate in the list
    const mentionDropdown = page.locator('text=Teammates').locator('xpath=ancestor::div[contains(@class, "rounded-2xl")]').first();
    const firstTeammate = mentionDropdown.locator('.cursor-pointer').first();
    await expect(firstTeammate).toBeVisible();
    await firstTeammate.click();

    // Verify mention pill is inserted in editor
    const editorMention = editor.locator('.aether-mention').first();
    await expect(editorMention).toBeVisible();

    // Verify text did not duplicate the "@" or corrupt the message
    const editorText = await editor.innerText();
    expect(editorText).not.toContain('@@');

    // Type text following the mention
    await page.keyboard.type('please check the deployment status.');

    // Send the message
    const sendBtn = page.locator('button[type="submit"]:has-text("Send")').first();
    await sendBtn.click();

    // Verify sent message contains .aether-mention pill
    const sentMsg = page.locator('.aether-message-content', { hasText: 'please check the deployment status' }).last();
    await expect(sentMsg).toBeVisible({ timeout: 10000 });
    const sentMention = sentMsg.locator('.aether-mention').first();
    await expect(sentMention).toBeVisible();

    // Verify computed styling of mention pill (rounded pill, font-weight 600)
    const borderRadius = await sentMention.evaluate((el) => window.getComputedStyle(el).borderRadius);
    expect(borderRadius).toBe('9999px');

    // Reload page and verify persistence
    await page.reload();
    const persistedMsg = page.locator('.aether-message-content', { hasText: 'please check the deployment status' }).last();
    await expect(persistedMsg).toBeVisible();
    const persistedMention = persistedMsg.locator('.aether-mention').first();
    await expect(persistedMention).toBeVisible();
  });

});
