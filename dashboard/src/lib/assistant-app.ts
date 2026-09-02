declare global {
  interface Window {
    __API_BASE_URL__: string;
  }
}

const API_BASE_URL = window.__API_BASE_URL__;

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ToolCallLog {
  name: string;
  args: Record<string, unknown>;
}

const TOOL_LABELS: Record<string, string> = {
  list_indicators: "Liste des indicateurs",
  list_countries: "Liste des pays",
  get_indicator_timeseries: "Série temporelle",
  get_indicator_ranking: "Classement",
  get_projections: "Projections 2025-2029",
  get_country_profile: "Fiche pays",
  compare_countries: "Comparaison de pays",
  get_data_quality: "Qualité des données",
};

let history: ChatMessage[] = [];
let sending = false;

const messagesEl = document.getElementById("chat-messages")!;
const emptyEl = document.getElementById("chat-empty")!;
const form = document.getElementById("chat-form") as HTMLFormElement;
const input = document.getElementById("chat-input") as HTMLTextAreaElement;
const sendBtn = document.getElementById("chat-send") as HTMLButtonElement;
const resetBtn = document.getElementById("chat-reset") as HTMLButtonElement;

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

// Minimal, safe markdown: escape everything first, then re-introduce **bold**
// and bullet lists. The system prompt asks the model to stick to this exact
// subset, but LLMs don't always comply perfectly — as a fallback, headers
// ("#"/"##"/"###") are downgraded to bold text, numbered lists ("1. ") are
// treated as bullets too, and horizontal rules ("---") are dropped, so an
// occasional slip still renders cleanly instead of showing raw syntax.
function renderMarkdown(text: string): string {
  const escaped = escapeHtml(text);
  const lines = escaped.split("\n");
  let html = "";
  let inList = false;
  const closeList = () => {
    if (inList) {
      html += "</ul>";
      inList = false;
    }
  };
  for (let line of lines) {
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) continue; // horizontal rule
    const heading = line.match(/^\s{0,3}#{1,6}\s+(.*)/);
    if (heading) line = `**${heading[1]}**`;

    const bulletMatch = line.match(/^\s*(?:[-*]|\d+[.)])\s+(.*)/);
    if (bulletMatch) {
      if (!inList) {
        html += '<ul class="list-disc pl-4 my-1 space-y-0.5">';
        inList = true;
      }
      html += `<li>${bulletMatch[1]}</li>`;
    } else {
      closeList();
      html += line ? `<p>${line}</p>` : "<br/>";
    }
  }
  closeList();
  return html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function appendUserMessage(text: string) {
  emptyEl.classList.add("hidden");
  const el = document.createElement("div");
  el.className = "flex justify-end";
  el.innerHTML = `<div class="max-w-[85%] sm:max-w-[70%] bg-brand text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(el);
  scrollToBottom();
}

function appendAssistantMessage(text: string, toolCalls: ToolCallLog[]): HTMLElement {
  emptyEl.classList.add("hidden");
  const wrap = document.createElement("div");
  wrap.className = "flex flex-col items-start gap-1.5";

  const toolsHtml = toolCalls.length
    ? `<div class="flex flex-wrap gap-1.5">${toolCalls
        .map(
          (tc) =>
            `<span class="inline-flex items-center gap-1 text-[10.5px] font-semibold text-infrastructure bg-infrastructure-soft px-2 py-1 rounded-full">
              <svg width="10" height="10"><use href="#ic-node"/></svg> ${TOOL_LABELS[tc.name] || tc.name}
            </span>`
        )
        .join("")}</div>`
    : "";

  wrap.innerHTML = `
    ${toolsHtml}
    <div class="max-w-[85%] sm:max-w-[70%] bg-surface-2 text-ink rounded-2xl rounded-bl-md px-4 py-2.5 text-sm leading-relaxed [&_p]:my-0.5 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
      ${renderMarkdown(text)}
    </div>
  `;
  messagesEl.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function appendTypingIndicator(): HTMLElement {
  emptyEl.classList.add("hidden");
  const el = document.createElement("div");
  el.className = "flex justify-start";
  el.innerHTML = `
    <div class="bg-surface-2 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1.5">
      <span class="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style="animation-delay:0ms"></span>
      <span class="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style="animation-delay:150ms"></span>
      <span class="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style="animation-delay:300ms"></span>
    </div>`;
  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function appendErrorMessage(text: string) {
  emptyEl.classList.add("hidden");
  const el = document.createElement("div");
  el.className = "flex justify-start";
  el.innerHTML = `<div class="max-w-[85%] sm:max-w-[70%] bg-health-soft text-health rounded-2xl rounded-bl-md px-4 py-2.5 text-sm leading-relaxed font-medium">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(el);
  scrollToBottom();
}

async function sendMessage(text: string) {
  if (sending || !text.trim()) return;
  sending = true;
  sendBtn.disabled = true;

  appendUserMessage(text);
  history.push({ role: "user", content: text });
  const typing = appendTypingIndicator();

  try {
    const res = await fetch(`${API_BASE_URL}/agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
    });

    typing.remove();

    if (!res.ok) {
      const body = await res.json().catch(() => ({}) as any);
      const detail = body?.detail || `Erreur ${res.status}`;
      appendErrorMessage(detail);
      history.pop();
      return;
    }

    const data = await res.json();
    appendAssistantMessage(data.reply, data.tool_calls || []);
    history.push({ role: "assistant", content: data.reply });
  } catch (e) {
    typing.remove();
    appendErrorMessage("Impossible de contacter l'API OpenDataViz. Vérifie qu'elle est bien démarrée et accessible.");
    history.pop();
  } finally {
    sending = false;
    sendBtn.disabled = false;
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value;
  input.value = "";
  input.style.height = "auto";
  sendMessage(text);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 128)}px`;
});

document.getElementById("chat-starters")?.addEventListener("click", (e) => {
  const btn = (e.target as HTMLElement).closest<HTMLButtonElement>("[data-starter]");
  if (btn) sendMessage(btn.dataset.starter!);
});

resetBtn.addEventListener("click", () => {
  history = [];
  messagesEl.innerHTML = "";
  messagesEl.appendChild(emptyEl);
  emptyEl.classList.remove("hidden");
});
