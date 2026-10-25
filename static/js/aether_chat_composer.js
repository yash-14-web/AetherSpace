/**
 * AetherSpace Chat Rich-Text Composer Engine
 * 
 * Features:
 * - Framework-independent rich-text editor compatible with Alpine.js and Django templates.
 * - Selection-preserving formatting controls (Bold, Italic, Strikethrough, Bulleted list,
 *   Numbered list, Inline code, Code block, Blockquote, Hyperlink, Undo, Redo, Mentions).
 * - Active state detection for toolbar buttons.
 * - Safe URL validation rejecting dangerous protocols (javascript:, data:, vbscript:).
 * - DOM-to-CommonMark serialization preserving 100% backward compatibility with Message.content.
 * - Teammate and File mention insertion with interactive pills.
 * - Enter-to-send with Shift+Enter for multiline growth.
 */

(function () {
    'use strict';

    /**
     * Protocol validator for URLs
     */
    function isValidUrl(url) {
        if (!url || typeof url !== 'string') return false;
        const trimmed = url.trim().toLowerCase();
        return trimmed.startsWith('https://') || trimmed.startsWith('http://') || trimmed.startsWith('mailto:');
    }

    /**
     * DOM-to-CommonMark Serializer
     * Converts contenteditable DOM structure into standard CommonMark.
     */
    function domToMarkdown(rootNode) {
        if (!rootNode) return '';

        function serializeList(listNode, indentLevel) {
            const isOrdered = listNode.tagName.toLowerCase() === 'ol';
            const indent = '    '.repeat(indentLevel);
            const items = [];
            let itemIdx = 1;

            for (const child of Array.from(listNode.childNodes)) {
                if (child.nodeType === Node.ELEMENT_NODE && child.tagName.toLowerCase() === 'li') {
                    let inlineText = '';
                    const nestedLists = [];

                    for (const liChild of Array.from(child.childNodes)) {
                        if (liChild.nodeType === Node.ELEMENT_NODE && 
                            (liChild.tagName.toLowerCase() === 'ul' || liChild.tagName.toLowerCase() === 'ol')) {
                            nestedLists.push(serializeList(liChild, indentLevel + 1));
                        } else {
                            inlineText += walk(liChild, indentLevel);
                        }
                    }

                    inlineText = inlineText.trim();
                    if (!inlineText && nestedLists.length === 0) {
                        continue;
                    }

                    const prefix = isOrdered ? `${itemIdx}. ` : '- ';
                    itemIdx++;

                    let itemResult = `${indent}${prefix}${inlineText}`;
                    if (nestedLists.length > 0) {
                        itemResult += '\n' + nestedLists.join('\n');
                    }
                    items.push(itemResult);
                } else if (child.nodeType === Node.ELEMENT_NODE && 
                           (child.tagName.toLowerCase() === 'ul' || child.tagName.toLowerCase() === 'ol')) {
                    items.push(serializeList(child, indentLevel + 1));
                }
            }

            return items.join('\n');
        }

        function walk(node, indentLevel = 0) {
            if (!node) return '';

            // Text node
            if (node.nodeType === Node.TEXT_NODE) {
                return node.textContent;
            }

            // Element node
            if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName.toLowerCase();

                // Mention pill: <span class="aether-mention" ...>
                if (node.classList && node.classList.contains('aether-mention')) {
                    const userId = node.getAttribute('data-user-id');
                    const cid = node.getAttribute('data-contributor-id');
                    const fileUrl = node.getAttribute('data-file-url');
                    const fileName = node.getAttribute('data-file-name');
                    const userName = node.getAttribute('data-user-name') || node.textContent.replace(/^@/, '');
                    if (fileUrl) {
                        return `[${fileName || node.textContent.replace(/^📄\s*/, '')}](${fileUrl})`;
                    }
                    if (userId) {
                        return `@[${userName}](${userId})`;
                    } else if (cid) {
                        return `@${cid}`;
                    }
                    return `@${userName}`;
                }

                // Bold
                if (tag === 'b' || tag === 'strong') {
                    const inner = Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('');
                    return inner.trim() ? `**${inner.trim()}**` : '';
                }

                // Italic
                if (tag === 'i' || tag === 'em') {
                    const inner = Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('');
                    return inner.trim() ? `*${inner.trim()}*` : '';
                }

                // Strikethrough
                if (tag === 's' || tag === 'strike' || tag === 'del') {
                    const inner = Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('');
                    return inner.trim() ? `~~${inner.trim()}~~` : '';
                }

                // Code block: <pre><code>...</code></pre>
                if (tag === 'pre') {
                    let inner = node.textContent || '';
                    inner = inner.replace(/\u200B/g, '');
                    if (inner.endsWith('\n')) {
                        inner = inner.slice(0, -1);
                    }
                    const backtickRuns = inner.match(/`{3,}/g) || [];
                    let maxRun = 2;
                    for (const run of backtickRuns) {
                        if (run.length > maxRun) maxRun = run.length;
                    }
                    const fence = '`'.repeat(maxRun + 1);
                    return `\n${fence}\n${inner}\n${fence}\n`;
                }

                // Inline code: <code> (not in pre)
                if (tag === 'code') {
                    let inner = Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('');
                    inner = inner.replace(/\u200B/g, '');
                    if (!inner) return '';

                    const backtickRuns = inner.match(/`+/g) || [];
                    let maxRun = 0;
                    for (const run of backtickRuns) {
                        if (run.length > maxRun) maxRun = run.length;
                    }
                    const fence = '`'.repeat(maxRun > 0 ? maxRun + 1 : 1);
                    const pad = (inner.startsWith('`') || inner.endsWith('`')) ? ' ' : '';
                    return `${fence}${pad}${inner}${pad}${fence}`;
                }

                // Blockquote
                if (tag === 'blockquote') {
                    const inner = Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('').trim();
                    const lines = inner.split('\n');
                    return '\n' + lines.map(l => `> ${l}`).join('\n') + '\n';
                }

                // Bulleted and Numbered lists: <ul> and <ol>
                if (tag === 'ul' || tag === 'ol') {
                    const serialized = serializeList(node, indentLevel);
                    return serialized ? `\n\n${serialized}\n\n` : '';
                }

                // List item (if directly walked outside serializeList)
                if (tag === 'li') {
                    return Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('');
                }

                // Hyperlink: <a>
                if (tag === 'a') {
                    const href = node.getAttribute('href') || '';
                    const text = Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('').trim();
                    if (isValidUrl(href)) {
                        return `[${text || href}](${href})`;
                    }
                    return text;
                }

                // Newlines & line breaks
                if (tag === 'br') {
                    return '\n';
                }
                if (tag === 'p' || tag === 'div') {
                    const inner = Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('');
                    return inner ? `\n${inner}` : '\n';
                }

                // Generic child walk
                return Array.from(node.childNodes).map(c => walk(c, indentLevel)).join('');
            }

            return '';
        }

        const raw = Array.from(rootNode.childNodes).map(c => walk(c, 0)).join('').trim();
        return raw.replace(/\n{3,}/g, '\n\n');
    }

    /**
     * Helper to set cursor after a specific node
     */
    function setCursorAfterNode(node) {
        if (!node) return;
        const sel = window.getSelection();
        if (!sel) return;
        const range = document.createRange();
        range.setStartAfter(node);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
    }

    /**
     * Rich Editor Alpine.js Mixin Factory
     */
    function createComposerMixin() {
        return {
            editorIsEmpty: true,
            activeFormatting: {
                bold: false,
                italic: false,
                strike: false,
                code: false,
                codeblock: false,
                quote: false,
                bullet: false,
                number: false,
                link: false
            },
            showLinkModal: false,
            linkText: '',
            linkUrl: '',
            linkError: '',
            savedSelectionRange: null,

            showEmojiPicker: false,
            activeEmojiCategory: 0,
            quickEmojis: ['👍', '❤️', '🔥', '🎉', '🚀', '👀', '👏', '✅'],
            emojiCategories: [
                {
                    name: 'Smileys',
                    icon: '😀',
                    emojis: [
                        '😀', '😃', '😄', '😁', '😆', '😅', '😂', '🤣', '🙂', '😉',
                        '😊', '😇', '🥰', '😍', '🤩', '😘', '😋', '😜', '🤪', '😎',
                        '🥳', '😏', '🤔', '🫡', '🤫', '😶', '🙄', '😬', '😴', '😷',
                        '🤯', '🤠', '😭', '😱', '😡', '💀', '💩', '🤡', '👻', '🤖'
                    ]
                },
                {
                    name: 'Gestures',
                    icon: '👍',
                    emojis: [
                        '👍', '👎', '👏', '🙌', '👐', '🤲', '🤝', '🙏', '✍️', '💪',
                        '👈', '👉', '👆', '👇', '✌️', '🤞', '🫰', '🤟', '🤘', '🤙',
                        '👋', '🫡', '🧑‍💻', '👨‍💻', '👩‍💻'
                    ]
                },
                {
                    name: 'Symbols',
                    icon: '🚀',
                    emojis: [
                        '🚀', '🔥', '✨', '🎉', '🎊', '💯', '❤️', '🧡', '💛', '💚',
                        '💙', '💜', '🖤', '🤍', '💔', '❤️‍🔥', '⭐', '🌟', '⚡', '💡',
                        '✅', '❌', '⚠️', '🎯', '🏆', '💻', '📱', '📊', '📈', '📌',
                        '📍', '📎', '🔒', '🔑', '⚙️', '⏱️', '☕', '🍕', '🍻'
                    ]
                }
            ],

            saveSelection() {
                const sel = window.getSelection();
                const editor = this.$refs.chatEditor;
                if (sel && sel.rangeCount > 0 && editor) {
                    const range = sel.getRangeAt(0);
                    if (editor.contains(range.commonAncestorContainer)) {
                        this.savedSelectionRange = range.cloneRange();
                    }
                }
            },

            restoreSelection() {
                const editor = this.$refs.chatEditor;
                if (!editor) return;
                const sel = window.getSelection();
                if (sel && this.savedSelectionRange && editor.contains(this.savedSelectionRange.commonAncestorContainer)) {
                    sel.removeAllRanges();
                    sel.addRange(this.savedSelectionRange);
                }
            },

            getOrRestoreSelection() {
                const editor = this.$refs.chatEditor;
                if (!editor) return null;
                const sel = window.getSelection();
                if (sel && sel.rangeCount > 0) {
                    const currentRange = sel.getRangeAt(0);
                    if (editor.contains(currentRange.commonAncestorContainer)) {
                        this.savedSelectionRange = currentRange.cloneRange();
                        return currentRange;
                    }
                }
                if (this.savedSelectionRange && editor.contains(this.savedSelectionRange.commonAncestorContainer)) {
                    this.restoreSelection();
                    if (sel && sel.rangeCount > 0) {
                        return sel.getRangeAt(0);
                    }
                }
                editor.focus();
                const range = document.createRange();
                range.selectNodeContents(editor);
                range.collapse(false);
                if (sel) {
                    sel.removeAllRanges();
                    sel.addRange(range);
                }
                this.savedSelectionRange = range.cloneRange();
                return range;
            },

            applyFormat(command, value = null) {
                return this.format(command, value);
            },

            format(command, value = null) {
                const editor = this.$refs.chatEditor;
                if (!editor) return;

                if (command === 'code') {
                    this.toggleInlineCode();
                    return;
                }
                if (command === 'codeblock') {
                    this.toggleCodeBlock();
                    return;
                }

                this.getOrRestoreSelection();
                editor.focus();

                if (command === 'bold') {
                    document.execCommand('bold', false, null);
                } else if (command === 'italic') {
                    document.execCommand('italic', false, null);
                } else if (command === 'strike') {
                    document.execCommand('strikeThrough', false, null);
                } else if (command === 'bullet') {
                    document.execCommand('insertUnorderedList', false, null);
                } else if (command === 'number') {
                    document.execCommand('insertOrderedList', false, null);
                } else if (command === 'undo') {
                    document.execCommand('undo', false, null);
                } else if (command === 'redo') {
                    document.execCommand('redo', false, null);
                } else if (command === 'quote') {
                    const sel = window.getSelection();
                    if (sel && sel.anchorNode) {
                        let node = sel.anchorNode;
                        if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
                        const bq = node.closest('blockquote');
                        if (bq) {
                            document.execCommand('formatBlock', false, '<p>');
                        } else {
                            document.execCommand('formatBlock', false, '<blockquote>');
                        }
                    }
                }

                this.saveSelection();
                this.onEditorInput();
                this.updateActiveFormatting();
            },

            toggleInlineCode() {
                const editor = this.$refs.chatEditor;
                if (!editor) return;

                const range = this.getOrRestoreSelection();
                if (!range) return;

                const sel = window.getSelection();
                let node = range.commonAncestorContainer;
                if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
                const existingCode = node.closest('code');

                if (existingCode && !existingCode.closest('pre')) {
                    // Unwrap code
                    const parent = existingCode.parentNode;
                    while (existingCode.firstChild) {
                        parent.insertBefore(existingCode.firstChild, existingCode);
                    }
                    parent.removeChild(existingCode);
                } else {
                    if (range.collapsed) {
                        // Empty inline code span with a zero-width space; caret placed INSIDE it
                        const code = document.createElement('code');
                        code.className = 'aether-inline-code px-1.5 py-0.5 rounded bg-slate-200/80 dark:bg-zinc-800 text-rose-600 dark:text-rose-400 font-mono text-xs border border-slate-300 dark:border-zinc-700';
                        const zwsp = document.createTextNode('\u200B');
                        code.appendChild(zwsp);
                        range.insertNode(code);

                        // Place caret inside code element after the zero-width space
                        const newRange = document.createRange();
                        newRange.setStart(zwsp, 1);
                        newRange.collapse(true);
                        if (sel) {
                            sel.removeAllRanges();
                            sel.addRange(newRange);
                        }
                    } else {
                        // Wrap selected text in <code> and preserve selection
                        const content = range.extractContents();
                        const code = document.createElement('code');
                        code.className = 'aether-inline-code px-1.5 py-0.5 rounded bg-slate-200/80 dark:bg-zinc-800 text-rose-600 dark:text-rose-400 font-mono text-xs border border-slate-300 dark:border-zinc-700';
                        code.appendChild(content);
                        range.insertNode(code);

                        const newRange = document.createRange();
                        newRange.selectNodeContents(code);
                        if (sel) {
                            sel.removeAllRanges();
                            sel.addRange(newRange);
                        }
                    }
                }

                this.saveSelection();
                this.onEditorInput();
                this.updateActiveFormatting();
            },

            toggleCodeBlock() {
                const editor = this.$refs.chatEditor;
                if (!editor) return;

                const range = this.getOrRestoreSelection();
                if (!range) return;

                const sel = window.getSelection();
                let node = range.commonAncestorContainer;
                if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
                const existingPre = node.closest('pre');

                if (existingPre) {
                    // Unwrap pre into p
                    const p = document.createElement('p');
                    p.textContent = existingPre.textContent;
                    existingPre.parentNode.replaceChild(p, existingPre);
                    const newRange = document.createRange();
                    newRange.selectNodeContents(p);
                    newRange.collapse(false);
                    if (sel) {
                        sel.removeAllRanges();
                        sel.addRange(newRange);
                    }
                } else {
                    const pre = document.createElement('pre');
                    pre.className = 'aether-code-block bg-slate-900 text-slate-100 p-3 rounded-xl text-xs font-mono my-2 border border-slate-800 overflow-x-auto whitespace-pre';
                    const code = document.createElement('code');
                    code.className = 'block font-mono';

                    if (range.collapsed) {
                        const zwsp = document.createTextNode('\u200B');
                        code.appendChild(zwsp);
                        pre.appendChild(code);
                        range.insertNode(pre);

                        // Place caret inside code element
                        const newRange = document.createRange();
                        newRange.setStart(zwsp, 1);
                        newRange.collapse(true);
                        if (sel) {
                            sel.removeAllRanges();
                            sel.addRange(newRange);
                        }
                    } else {
                        const content = range.extractContents();
                        code.appendChild(content);
                        pre.appendChild(code);
                        range.insertNode(pre);

                        // Place caret at end of code element
                        const newRange = document.createRange();
                        newRange.selectNodeContents(code);
                        newRange.collapse(false);
                        if (sel) {
                            sel.removeAllRanges();
                            sel.addRange(newRange);
                        }
                    }
                }

                this.saveSelection();
                this.onEditorInput();
                this.updateActiveFormatting();
            },

            openLinkModal() {
                this.saveSelection();
                const sel = window.getSelection();
                this.linkText = sel ? sel.toString().trim() : '';
                this.linkUrl = 'https://';
                this.linkError = '';
                this.showLinkModal = true;
            },

            closeLinkModal() {
                this.showLinkModal = false;
                this.linkError = '';
                const editor = this.$refs.chatEditor;
                if (editor) editor.focus();
                this.restoreSelection();
            },

            insertLink() {
                const url = this.linkUrl.trim();
                if (!isValidUrl(url)) {
                    this.linkError = 'Please enter a valid URL starting with https://, http://, or mailto:';
                    return;
                }

                this.showLinkModal = false;
                const editor = this.$refs.chatEditor;
                if (!editor) return;
                editor.focus();
                this.restoreSelection();

                const text = this.linkText.trim() || url;
                const sel = window.getSelection();
                if (sel && sel.rangeCount > 0) {
                    const range = sel.getRangeAt(0);
                    range.deleteContents();
                    const a = document.createElement('a');
                    a.href = url;
                    a.textContent = text;
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    a.className = 'aether-chat-link text-blue-600 dark:text-sky-400 underline font-medium';
                    range.insertNode(a);
                    setCursorAfterNode(a);
                } else {
                    document.execCommand('createLink', false, url);
                }

                this.onEditorInput();
                this.updateActiveFormatting();
            },

            insertEmoji(emoji) {
                const editor = this.$refs.chatEditor;
                if (!editor) return;

                editor.focus();
                this.restoreSelection();

                const sel = window.getSelection();
                if (sel && sel.rangeCount > 0 && editor.contains(sel.anchorNode)) {
                    if (!document.execCommand('insertText', false, emoji)) {
                        const range = sel.getRangeAt(0);
                        range.deleteContents();
                        const textNode = document.createTextNode(emoji);
                        range.insertNode(textNode);
                        range.setStartAfter(textNode);
                        range.collapse(true);
                        sel.removeAllRanges();
                        sel.addRange(range);
                    }
                } else {
                    const textNode = document.createTextNode(emoji);
                    editor.appendChild(textNode);
                    const range = document.createRange();
                    range.setStartAfter(textNode);
                    range.collapse(true);
                    if (sel) {
                        sel.removeAllRanges();
                        sel.addRange(range);
                    }
                }

                this.saveSelection();
                this.showEmojiPicker = false;
                this.onEditorInput();
                this.updateActiveFormatting();
            },

            updateActiveFormatting() {
                try {
                    this.activeFormatting.bold = document.queryCommandState('bold');
                    this.activeFormatting.italic = document.queryCommandState('italic');
                    this.activeFormatting.strike = document.queryCommandState('strikeThrough');

                    let isBullet = false;
                    let isNumber = false;
                    try {
                        isBullet = document.queryCommandState('insertUnorderedList');
                        isNumber = document.queryCommandState('insertOrderedList');
                    } catch (e) {}

                    const sel = window.getSelection();
                    const editor = this.$refs.chatEditor;
                    if (sel && sel.anchorNode) {
                        let node = sel.anchorNode;
                        if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
                        if (node && editor && editor.contains(node)) {
                            this.activeFormatting.code = !!(node.closest('code') && !node.closest('pre'));
                            this.activeFormatting.codeblock = !!node.closest('pre');
                            this.activeFormatting.quote = !!node.closest('blockquote');
                            this.activeFormatting.link = !!node.closest('a');

                            if (node.closest('ul')) isBullet = true;
                            if (node.closest('ol')) isNumber = true;
                        }
                    }

                    this.activeFormatting.bullet = !!isBullet;
                    this.activeFormatting.number = !!isNumber;
                } catch (e) {
                    // Ignore DOM query failures in non-standard selections
                }
            },

            onEditorInput() {
                const editor = this.$refs.chatEditor;
                if (!editor) return;

                const text = editor.innerText || editor.textContent || '';
                this.editorIsEmpty = !text.trim() && !editor.querySelector('img, pre, code');

                // Sync markdown to hidden input
                const md = domToMarkdown(editor);
                this.messageContent = md;
                if (this.$refs.hiddenContent) {
                    this.$refs.hiddenContent.value = md;
                }

                this.checkMentionTrigger();
            },

            checkMentionTrigger() {
                const sel = window.getSelection();
                if (!sel || !sel.isCollapsed) {
                    this.showMentions = false;
                    return;
                }

                const node = sel.anchorNode;
                if (!node || node.nodeType !== Node.TEXT_NODE) {
                    this.showMentions = false;
                    return;
                }

                const textBeforeCursor = node.textContent.slice(0, sel.anchorOffset);
                const match = textBeforeCursor.match(/@([a-zA-Z0-9._-]*)$/);

                if (match) {
                    this.mentionQuery = match[1];
                    this.cursorPos = sel.anchorOffset;
                    this.showMentions = true;
                    this.activeIndex = 0;
                    if (typeof this.searchMentions === 'function') {
                        this.searchMentions(this.mentionQuery);
                    } else if (typeof this.filterMentions === 'function') {
                        this.filterMentions();
                    }
                } else {
                    this.showMentions = false;
                }
            },

            insertMentionPill(item) {
                const editor = this.$refs.chatEditor;
                if (!editor) return;
                editor.focus();

                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return;
                const range = sel.getRangeAt(0);

                let node = sel.anchorNode;
                let offset = sel.anchorOffset;
                if (!node || node.nodeType !== Node.TEXT_NODE) {
                    node = range.startContainer;
                    offset = range.startOffset;
                }

                if (node && node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent;
                    const atIndex = text.lastIndexOf('@', offset > 0 ? offset - 1 : 0);

                    if (atIndex !== -1) {
                        // Replace the typed @query portion
                        node.textContent = text.slice(0, atIndex) + text.slice(offset);
                        range.setStart(node, atIndex);
                        range.collapse(true);
                    }
                }

                // Create mention pill span
                const span = document.createElement('span');
                span.className = 'aether-mention select-none';
                span.setAttribute('contenteditable', 'false');

                if (item.type === 'file') {
                    span.setAttribute('data-file-id', item.id || '');
                    span.setAttribute('data-file-name', item.name || '');
                    span.setAttribute('data-file-url', item.url || '');
                    span.textContent = `📄 ${item.name}`;
                } else {
                    const displayName = (item.full_name || item.name || item.username || (item.email ? item.email.split('@')[0] : 'Teammate')).trim();
                    span.setAttribute('data-user-id', item.id || '');
                    if (item.contributor_id) {
                        span.setAttribute('data-contributor-id', item.contributor_id);
                    }
                    span.setAttribute('data-user-name', displayName);
                    span.textContent = `@${displayName}`;
                }

                range.insertNode(span);

                // Add a space after the mention
                const space = document.createTextNode('\u00A0');
                if (span.nextSibling) {
                    span.parentNode.insertBefore(space, span.nextSibling);
                } else if (span.parentNode) {
                    span.parentNode.appendChild(space);
                }
                setCursorAfterNode(space);

                this.showMentions = false;
                this.onEditorInput();
            },

            handleEditorKeydown(e) {
                if (this.showMentions) {
                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        this.navigateMentions(1);
                        return;
                    }
                    if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        this.navigateMentions(-1);
                        return;
                    }
                    if (e.key === 'Enter' || e.key === 'Tab') {
                        e.preventDefault();
                        this.selectActiveMention();
                        return;
                    }
                    if (e.key === 'Escape') {
                        this.showMentions = false;
                        return;
                    }
                }

                // Check caret position and enclosing block
                const sel = window.getSelection();
                const editor = this.$refs.chatEditor;
                let anchorEl = sel && sel.anchorNode ? (sel.anchorNode.nodeType === Node.TEXT_NODE ? sel.anchorNode.parentElement : sel.anchorNode) : null;
                const inEditor = anchorEl && editor && editor.contains(anchorEl);
                const currentLi = inEditor ? anchorEl.closest('li') : null;
                const currentPre = inEditor ? anchorEl.closest('pre') : null;

                // Tab / Shift+Tab inside a list: Indent / Outdent
                if (e.key === 'Tab' && inEditor && currentLi) {
                    e.preventDefault();
                    if (e.shiftKey) {
                        document.execCommand('outdent', false, null);
                    } else {
                        document.execCommand('indent', false, null);
                    }
                    this.onEditorInput();
                    this.updateActiveFormatting();
                    return;
                }

                // Tab / Shift+Tab inside a code block (<pre>): Insert 4 spaces
                if (e.key === 'Tab' && inEditor && currentPre) {
                    e.preventDefault();
                    document.execCommand('insertText', false, '    ');
                    this.onEditorInput();
                    return;
                }

                if (e.key === 'Enter') {
                    // Shift+Enter creates a line break within current block
                    if (e.shiftKey) {
                        return;
                    }

                    // Ctrl+Enter or Cmd+Enter ALWAYS sends the message
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        this.handleSendMessage(e);
                        return;
                    }

                    // Inside a code block (<pre>): Enter inserts a newline, never sends message
                    if (currentPre) {
                        e.preventDefault();
                        if (!document.execCommand('insertText', false, '\n')) {
                            const sel = window.getSelection();
                            if (sel && sel.rangeCount > 0) {
                                const range = sel.getRangeAt(0);
                                range.deleteContents();
                                const textNode = document.createTextNode('\n');
                                range.insertNode(textNode);
                                range.setStartAfter(textNode);
                                range.collapse(true);
                                sel.removeAllRanges();
                                sel.addRange(range);
                            }
                        }
                        this.saveSelection();
                        this.onEditorInput();
                        return;
                    }

                    // Inside a list item (<li>): Enter creates the next list item, or exits an empty list
                    if (currentLi) {
                        setTimeout(() => {
                            this.onEditorInput();
                            this.updateActiveFormatting();
                        }, 0);
                        return;
                    }

                    // Normal Enter outside of lists: Send message
                    e.preventDefault();
                    this.handleSendMessage(e);
                    return;
                }

                const isMod = e.ctrlKey || e.metaKey;
                if (isMod) {
                    const key = e.key.toLowerCase();
                    if (key === 'b') {
                        e.preventDefault();
                        this.format('bold');
                    } else if (key === 'i') {
                        e.preventDefault();
                        this.format('italic');
                    } else if (key === 'k') {
                        e.preventDefault();
                        this.openLinkModal();
                    } else if (key === 'z' && !e.shiftKey) {
                        e.preventDefault();
                        this.format('undo');
                    } else if (key === 'y' || (key === 'z' && e.shiftKey)) {
                        e.preventDefault();
                        this.format('redo');
                    }
                }
            },

            handleEditorPaste(e) {
                e.preventDefault();
                const text = (e.clipboardData || window.clipboardData).getData('text/plain');
                if (text) {
                    document.execCommand('insertText', false, text);
                    this.onEditorInput();
                }
            },

            clearComposer() {
                const editor = this.$refs.chatEditor;
                if (editor) {
                    editor.innerHTML = '';
                }
                this.messageContent = '';
                this.editorIsEmpty = true;
                if (this.$refs.hiddenContent) {
                    this.$refs.hiddenContent.value = '';
                }
                this.updateActiveFormatting();
            }
        };
    }

    window.AetherChatComposer = {
        domToMarkdown,
        isValidUrl,
        createComposerMixin
    };

})();
