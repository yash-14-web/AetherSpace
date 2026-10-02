/**
 * AetherSpace Central Markdown & Live Preview Engine
 *
 * Implements the single markdown architecture:
 * USER MARKDOWN -> EDITOR -> CENTRAL MARKDOWN RENDERER -> SANITIZED HTML -> LIVE PREVIEW
 * AND
 * USER MARKDOWN -> DATABASE -> CENTRAL MARKDOWN RENDERER -> SANITIZED HTML -> FINAL RENDERED MESSAGE
 *
 * Principle: LIVE PREVIEW == SAVED MESSAGE
 */

(function () {
    'use strict';

    window.AetherMarkdown = {
        cache: new Map(),

        getCookie(name) {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        },

        getCSRFToken() {
            const el = document.querySelector('[name=csrfmiddlewaretoken]');
            return el ? el.value : (this.getCookie('csrftoken') || '');
        },

        /**
         * Authoritative Render Function
         * @param {string} rawText - Markdown source input by user
         * @param {function} callback - Receives the rendered HTML string
         */
        async render(rawText, callback) {
            if (!rawText || !rawText.trim()) {
                const emptyNotice = '<p class="text-xs text-slate-400 dark:text-zinc-500 italic">Nothing to preview</p>';
                if (callback) callback(emptyNotice);
                return emptyNotice;
            }

            const trimmed = rawText.trim();

            // 1. Instant Cache Hit (0ms latency)
            if (this.cache.has(trimmed)) {
                const cachedHtml = this.cache.get(trimmed);
                if (callback) callback(cachedHtml);
                return cachedHtml;
            }

            // 2. Immediate Client-Side Optimistic Preview (prevents any visual delay)
            const optimisticHtml = this.fallbackClientRender(rawText);
            if (callback) callback(optimisticHtml);

            // 3. Authoritative Server-Side Pipeline Execution
            const url = window.AETHER_MARKDOWN_PREVIEW_URL || '/api/markdown-preview/';
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({ content: rawText })
                });

                if (response.ok) {
                    const data = await response.json();
                    const authoritativeHtml = data.html || '';
                    this.cache.set(trimmed, authoritativeHtml);
                    if (callback) callback(authoritativeHtml);
                    return authoritativeHtml;
                }
            } catch (err) {
                console.warn('AetherMarkdown server-side render fetch failed, using optimistic preview:', err);
            }

            return optimisticHtml;
        },

        /**
         * Resilient Client-Side Fallback Markdown Parser
         * Handles standard markdown safely if offline or before server response resolves.
         */
        fallbackClientRender(text) {
            if (!text || !text.trim()) {
                return '<p class="text-xs text-slate-400 dark:text-zinc-500 italic">Nothing to preview</p>';
            }

            // 1. Escape HTML special characters
            let s = text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');

            // 2. Extract & preserve code blocks from being mangled by line-breaks/mentions
            const codeBlocks = [];
            s = s.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
                const langClass = lang ? ` class="language-${lang}"` : '';
                const html = `<pre class="bg-slate-900 text-slate-100 p-3 rounded-xl text-xs font-mono my-2 overflow-x-auto border border-slate-800"><code${langClass}>${code}</code></pre>`;
                codeBlocks.push(html);
                return `\n__AETHER_CODE_BLOCK_${codeBlocks.length - 1}__\n`;
            });

            // 3. Extract & preserve inline code
            s = s.replace(/`([^`\n]+)`/g, (match, code) => {
                const html = `<code class="bg-slate-100 dark:bg-zinc-800 text-rose-500 px-1.5 py-0.5 rounded text-xs font-mono">${code}</code>`;
                codeBlocks.push(html);
                return `__AETHER_CODE_BLOCK_${codeBlocks.length - 1}__`;
            });

            // 4. Headings
            s = s.replace(/^###### (.*$)/gim, '<h6 class="text-xs font-bold text-slate-900 dark:text-zinc-100 my-1">$1</h6>');
            s = s.replace(/^##### (.*$)/gim, '<h5 class="text-xs font-bold text-slate-900 dark:text-zinc-100 my-1">$1</h5>');
            s = s.replace(/^#### (.*$)/gim, '<h4 class="text-sm font-bold text-slate-900 dark:text-zinc-100 my-1">$1</h4>');
            s = s.replace(/^### (.*$)/gim, '<h3 class="text-sm font-bold text-slate-900 dark:text-zinc-100 my-1.5">$1</h3>');
            s = s.replace(/^## (.*$)/gim, '<h2 class="text-base font-bold text-slate-900 dark:text-zinc-100 my-2">$1</h2>');
            s = s.replace(/^# (.*$)/gim, '<h1 class="text-lg font-bold text-slate-900 dark:text-zinc-100 my-2">$1</h1>');

            // 5. Blockquotes
            s = s.replace(/^\> (.*$)/gim, '<blockquote class="border-l-4 border-aether-blue pl-3 my-1.5 italic text-slate-600 dark:text-zinc-400 text-xs">$1</blockquote>');

            // 6. Bold, Italic, Strikethrough (trim inner whitespace to match server pipeline)
            s = s.replace(/\*\*([^\*\n]+?)\*\*/g, (m, p1) => `<strong>${p1.trim()}</strong>`);
            s = s.replace(/\*([^\*\n]+?)\*/g, (m, p1) => `<em>${p1.trim()}</em>`);
            s = s.replace(/~~([^~\n]+?)~~/g, (m, p1) => `<del class="line-through text-slate-400">${p1.trim()}</del>`);

            // 7. Links (Safe protocols only)
            s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-aether-blue dark:text-sky-400 underline font-medium hover:text-blue-600">$1</a>');

            // 8. Mentions in prose
            s = s.replace(/@\[([^\]]+)\]\(([a-zA-Z0-9_-]+)\)/g, '<span class="aether-mention inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/25">@$1</span>');
            s = s.replace(/@(\d{5}[A-Za-z])\b/g, '<span class="aether-mention inline-flex items-center space-x-1 px-1.5 py-0.5 rounded-full text-xs font-mono font-bold bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/25">@$1</span>');

            // 9. Lists & Task Checkboxes (Properly wrapped in <ul> and <ol>)
            // First normalize standalone bracket checkboxes [ ] or [x] to - [ ] or - [x]
            s = s.replace(/^(?:\s*)(\[[ xX]\]\s+.*)$/gm, '- $1');

            s = s.replace(/((?:^\s*-\s+.*(?:\n|$))+)/gm, (match) => {
                let hasTasks = false;
                const itemsHtml = match.trim().split('\n').map(line => {
                    let content = line.replace(/^\s*-\s+/, '');
                    let isTask = false;
                    let isChecked = false;
                    if (/^\[\s*\]\s+/.test(content)) {
                        isTask = true;
                        hasTasks = true;
                        content = content.replace(/^\[\s*\]\s+/, '');
                    } else if (/^\[[xX]\]\s+/.test(content)) {
                        isTask = true;
                        isChecked = true;
                        hasTasks = true;
                        content = content.replace(/^\[[xX]\]\s+/, '');
                    }
                    content = content.replace(/^### (.*$)/, '<h3 class="text-sm font-bold my-1 text-slate-900 dark:text-zinc-100">$1</h3>');
                    content = content.replace(/^## (.*$)/, '<h2 class="text-base font-bold my-1 text-slate-900 dark:text-zinc-100">$1</h2>');
                    content = content.replace(/^# (.*$)/, '<h1 class="text-lg font-bold my-1 text-slate-900 dark:text-zinc-100">$1</h1>');
                    if (isTask) {
                        if (isChecked) {
                            return `<li class="task-list-item flex items-center space-x-2 my-1 list-none"><input type="checkbox" checked disabled class="rounded border-slate-300 dark:border-zinc-700 text-aether-blue pointer-events-none mr-1.5" /><span class="line-through text-slate-400 dark:text-zinc-500">${content}</span></li>`;
                        }
                        return `<li class="task-list-item flex items-center space-x-2 my-1 list-none"><input type="checkbox" disabled class="rounded border-slate-300 dark:border-zinc-700 text-aether-blue pointer-events-none mr-1.5" /><span>${content}</span></li>`;
                    }
                    return `<li>${content}</li>`;
                }).join('');
                const listClass = hasTasks ? 'space-y-1 my-1.5 text-xs text-slate-800 dark:text-zinc-200' : 'list-disc ml-5 my-1.5 space-y-0.5 text-xs text-slate-800 dark:text-zinc-200';
                return `<ul class="${listClass}">${itemsHtml}</ul>`;
            });

            s = s.replace(/((?:^\s*\d+\.\s+.*(?:\n|$))+)/gm, (match) => {
                const itemsHtml = match.trim().split('\n').map(line => {
                    let content = line.replace(/^\s*\d+\.\s+/, '');
                    content = content.replace(/^### (.*$)/, '<h3 class="text-sm font-bold my-1 text-slate-900 dark:text-zinc-100">$1</h3>');
                    content = content.replace(/^## (.*$)/, '<h2 class="text-base font-bold my-1 text-slate-900 dark:text-zinc-100">$1</h2>');
                    content = content.replace(/^# (.*$)/, '<h1 class="text-lg font-bold my-1 text-slate-900 dark:text-zinc-100">$1</h1>');
                    return `<li>${content}</li>`;
                }).join('');
                return `<ol class="list-decimal ml-5 my-1.5 space-y-0.5 text-xs text-slate-800 dark:text-zinc-200">${itemsHtml}</ol>`;
            });

            // 10. Horizontal Rules
            s = s.replace(/^(?:---|\*\*\*|___)\s*$/gm, '<hr class="my-3 border-slate-200 dark:border-zinc-800"/>');

            // 11. Tables (Markdown tables)
            s = s.replace(/((?:^\|.+?\|(?:\n|$))+)/gm, (match) => {
                const lines = match.trim().split('\n').map(l => l.trim()).filter(Boolean);
                if (lines.length < 2) retur  n match;
                // Header line
                const headers = lines[0].split('|').slice(1, -1).map(h => `<th class="px-3 py-1.5 text-left text-xs font-bold border border-slate-200 dark:border-zinc-700 bg-slate-100 dark:bg-zinc-800">${h.trim()}</th>`).join('');
                // Data rows (skip line 1 which is separator |---|---|)
                const rows = lines.slice(2).map(row => {
                    const cells = row.split('|').slice(1, -1).map(c => `<td class="px-3 py-1.5 text-xs border border-slate-200 dark:border-zinc-800">${c.trim()}</td>`).join('');
                    return `<tr>${cells}</tr>`;
                }).join('');
                return `<div class="overflow-x-auto my-2"><table class="min-w-full border-collapse border border-slate-200 dark:border-zinc-800"><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div>`;
            });

            // 12. Restore Code Blocks
            if (codeBlocks.length > 0) {
                s = s.replace(/__AETHER_CODE_BLOCK_(\d+)__/g, (match, idx) => {
                    return codeBlocks[parseInt(idx, 10)] || '';
                });
            }

            // 13. Line breaks outside tags
            s = s.replace(/\n(?!(?:<\/?(ul|ol|li|pre|code|table|thead|tbody|tr|th|td|blockquote|h[1-6]|hr)\b))/g, '<br/>');

            return s;
        }
    };

    // Backward compatibility alias
    window.renderSafeMarkdown = function (text) {
        return window.AetherMarkdown.fallbackClientRender(text);
    };

})();
