const STATUS_LABELS = {
  draft: "черновик",
  research: "исследование",
  generation: "генерация",
  audit: "аудит",
  approval: "ожидает согласования",
  revision: "правка",
  disputed: "спорный",
  approved: "одобрен",
  rejected: "отклонён",
  scheduled: "запланирован",
  published: "опубликован",
  error: "ошибка",
};

const VERDICT_LABELS = {
  pass: "принято",
  revise: "на доработку",
  reject: "отклонено",
};

const state = {
  tasks: [],
  selectedId: null,
};

const els = {
  list: document.getElementById("task-list"),
  detail: document.getElementById("task-detail"),
  spend: document.getElementById("spend-box"),
  weekly: document.getElementById("weekly-box"),
  clicks: document.getElementById("clicks-box"),
  toast: document.getElementById("toast"),
  filter: document.getElementById("status-filter"),
  runForm: document.getElementById("run-form"),
  btnRun: document.getElementById("btn-run"),
};

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function verdictLabel(verdict) {
  return VERDICT_LABELS[verdict] || verdict;
}

function toast(message, isError = false) {
  els.toast.hidden = false;
  els.toast.textContent = message;
  els.toast.classList.toggle("error", isError);
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    els.toast.hidden = true;
  }, 3200);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail = data?.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function topicTitle(task) {
  return task.generated_texts?.at(-1)?.title || task.topic?.text || "Без названия";
}

function renderList() {
  const filter = els.filter.value;
  const tasks = [...state.tasks]
    .filter((t) => !filter || t.status === filter)
    .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

  if (!tasks.length) {
    els.list.innerHTML = `<p class="detail-empty">Пока нет задач. Запустите цикл слева.</p>`;
    return;
  }

  els.list.innerHTML = tasks
    .map(
      (t) => `
      <button type="button" class="task-row ${t.id === state.selectedId ? "active" : ""}" data-id="${t.id}" role="listitem">
        <div class="title">${escapeHtml(topicTitle(t))}</div>
        <div class="meta">
          <span class="badge ${t.status}">${escapeHtml(statusLabel(t.status))}</span>
          <span>${escapeHtml(t.direction)}</span>
          <span>правки ${t.revision_count ?? 0}</span>
        </div>
      </button>`
    )
    .join("");

  els.list.querySelectorAll(".task-row").forEach((btn) => {
    btn.addEventListener("click", () => selectTask(btn.dataset.id));
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function selectedTask() {
  return state.tasks.find((t) => t.id === state.selectedId) || null;
}

function renderDetail() {
  const task = selectedTask();
  if (!task) {
    els.detail.className = "detail-empty";
    els.detail.textContent = "Выберите задачу из списка";
    return;
  }

  const text = task.generated_texts?.at(-1);
  const audit = task.audit_result;
  const pub = task.publication;
  const platform = task.platform_publication;
  const preview = [text?.lead, text?.body].filter(Boolean).join("\n\n").slice(0, 900);

  const actions = [];
  if (task.status === "approval" || task.status === "disputed") {
    actions.push(`<button type="button" class="btn ok" data-act="approve">Одобрить</button>`);
    actions.push(`<button type="button" class="btn danger" data-act="reject">Отклонить</button>`);
  }
  if (task.status === "approved") {
    actions.push(`<button type="button" class="btn primary" data-act="schedule">Telegram: запланировать (−1 мин)</button>`);
    if (!platform) {
      actions.push(`<button type="button" class="btn primary" data-act="platform">Опубликовать на площадку</button>`);
    }
  }
  if (platform?.short_code) {
    actions.push(`<button type="button" class="btn ghost" data-act="click">Симулировать клик (${platform.short_code})</button>`);
  }

  els.detail.className = "detail-block";
  els.detail.innerHTML = `
    <p class="kicker">${escapeHtml(task.id)}</p>
    <h3>${escapeHtml(topicTitle(task))}</h3>
    <div class="meta">
      <span class="badge ${task.status}">${escapeHtml(statusLabel(task.status))}</span>
      <span class="badge">${escapeHtml(task.direction)}</span>
    </div>
    ${
      audit
        ? `<p class="kicker">Аудит: ${escapeHtml(verdictLabel(audit.verdict))} · оценка ${(audit.score ?? 0).toFixed(2)}</p>`
        : ""
    }
    ${text ? `<div class="preview">${escapeHtml(preview)}</div>` : "<p class='detail-empty'>Нет сгенерированного текста</p>"}
    ${
      pub
        ? `<p class="kicker">Telegram: сообщение ${escapeHtml(pub.message_id)} · ${escapeHtml(pub.utm_url || "")}</p>`
        : ""
    }
    ${
      platform
        ? `<p class="kicker">Площадка: ${escapeHtml(platform.short_url || "")}<br/>цель ${escapeHtml(platform.target_url || "")}</p>`
        : ""
    }
    <div class="row-actions">${actions.join("") || "<span class='detail-empty'>Нет доступных действий для этого статуса</span>"}</div>
  `;

  els.detail.querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => handleAction(btn.dataset.act, task));
  });
}

async function handleAction(act, task) {
  try {
    if (act === "approve") {
      await api(`/tasks/${task.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ approved: true }),
      });
      toast("Одобрено");
    } else if (act === "reject") {
      await api(`/tasks/${task.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ approved: false }),
      });
      toast("Отклонено");
    } else if (act === "schedule") {
      const when = new Date(Date.now() - 60_000).toISOString().replace(/\.\d{3}Z$/, "");
      await api(`/tasks/${task.id}/schedule`, {
        method: "POST",
        body: JSON.stringify({ scheduled_at: when }),
      });
      const due = await api("/publish/due", { method: "POST" });
      toast(`Telegram: запланировано и опубликовано (${due.count})`);
    } else if (act === "platform") {
      await api(`/tasks/${task.id}/publish-platform`, { method: "POST" });
      toast("Опубликовано на площадку (mock)");
    } else if (act === "click") {
      const code = task.platform_publication?.short_code;
      const result = await api(`/links/${code}/click`, { method: "POST" });
      toast(`Клик записан: ${result.clicks}`);
    }
    await refreshAll();
  } catch (err) {
    toast(err.message, true);
  }
}

async function loadTasks() {
  const data = await api("/tasks");
  state.tasks = data.tasks || [];
  if (state.selectedId && !state.tasks.some((t) => t.id === state.selectedId)) {
    state.selectedId = null;
  }
  renderList();
  renderDetail();
}

async function loadMetrics() {
  const [spend, weekly, clicks] = await Promise.all([
    api("/spending"),
    api("/reports/weekly?direction=mental_health"),
    api("/analytics/clicks"),
  ]);

  els.spend.textContent = [
    `день   $${spend.daily.spent_usd.toFixed(4)} / ${spend.daily.limit_usd} (${spend.daily.percentage.toFixed(1)}%)`,
    `  предупреждение=${spend.daily.warning} превышен=${spend.daily.exceeded}`,
    `месяц  $${spend.monthly.spent_usd.toFixed(4)} / ${spend.monthly.limit_usd}`,
    `  предупреждение=${spend.monthly.warning} превышен=${spend.monthly.exceeded}`,
  ].join("\n");

  els.weekly.textContent = weekly.summary_text || JSON.stringify(weekly, null, 2);

  if (!clicks.rows?.length) {
    els.clicks.textContent = "Кликов пока нет. Опубликуйте на площадку и нажмите «Симулировать клик».";
  } else {
    els.clicks.textContent = [
      `всего_кликов=${clicks.total_clicks}`,
      ...clicks.rows.map(
        (r) => `[${r.channel}] ${r.text_title} → ${r.clicks} (${r.short_code})`
      ),
    ].join("\n");
  }
}

async function refreshAll() {
  await Promise.all([loadTasks(), loadMetrics()]);
}

async function selectTask(id) {
  state.selectedId = id;
  renderList();
  try {
    const fresh = await api(`/tasks/${id}`);
    const idx = state.tasks.findIndex((t) => t.id === id);
    if (idx >= 0) state.tasks[idx] = fresh;
    else state.tasks.unshift(fresh);
    renderDetail();
  } catch (err) {
    toast(err.message, true);
  }
}

els.runForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(els.runForm);
  const payload = {
    direction: String(fd.get("direction") || "mental_health"),
    topic_text: String(fd.get("topic_text") || "") || null,
    topic_rubric: String(fd.get("topic_rubric") || "research"),
  };
  els.btnRun.disabled = true;
  try {
    const task = await api("/tasks/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.selectedId = task.id;
    toast(`Цикл готов → ${statusLabel(task.status)}`);
    await refreshAll();
  } catch (err) {
    toast(err.message, true);
  } finally {
    els.btnRun.disabled = false;
  }
});

document.getElementById("btn-refresh").addEventListener("click", () => {
  refreshAll().catch((err) => toast(err.message, true));
});

document.getElementById("btn-publish-due").addEventListener("click", async () => {
  try {
    const due = await api("/publish/due", { method: "POST" });
    toast(`Опубликовано due: ${due.count}`);
    await refreshAll();
  } catch (err) {
    toast(err.message, true);
  }
});

els.filter.addEventListener("change", renderList);

refreshAll().catch((err) => toast(err.message, true));
