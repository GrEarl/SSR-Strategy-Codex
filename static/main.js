const personaForm = document.getElementById("persona-form");
const criterionForm = document.getElementById("criterion-form");
const templateForm = document.getElementById("template-form");
const taskForm = document.getElementById("task-form");
const personaList = document.getElementById("persona-list");
const criterionList = document.getElementById("criterion-list");
const templateList = document.getElementById("template-list");
const personaOptions = document.getElementById("persona-options");
const criterionOptions = document.getElementById("criterion-options");
const templateSelect = document.getElementById("template-select");
const taskList = document.getElementById("task-list");
const taskStatus = document.getElementById("task-status");
const sessionList = document.getElementById("session-list");
const bootstrapBtn = document.getElementById("bootstrap-btn");
const bootstrapStatus = document.getElementById("bootstrap-status");
const benchmarkForm = document.getElementById("benchmark-form");
const benchmarkList = document.getElementById("benchmark-list");
const evaluationTable = document.getElementById("evaluation-table");
const evaluationSummary = document.getElementById("evaluation-summary");
const evaluateBtn = document.getElementById("evaluate-btn");
const personaCount = document.getElementById("persona-count");
const criterionCount = document.getElementById("criterion-count");
const templateCount = document.getElementById("template-count");
const taskCount = document.getElementById("task-count");
const taskDone = document.getElementById("task-done");
const taskFailed = document.getElementById("task-failed");
const refreshClock = document.getElementById("refresh-clock");
const forceRefresh = document.getElementById("force-refresh");
let aggregateChart = null;

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return await res.json();
}

function renderPersonas(personas) {
  personaList.innerHTML = "";
  personaOptions.innerHTML = "";
  if (personaCount) personaCount.textContent = personas.length;
  personas.forEach((p) => {
    const li = document.createElement("li");
    li.textContent = `${p.name} (${p.age}/${p.gender}) ${p.notes || ""}`;
    const btn = document.createElement("button");
    btn.textContent = "Delete";
    btn.onclick = async () => {
      await fetch(`/api/personas/${p.id}`, { method: "DELETE" });
      loadPersonas();
    };
    li.appendChild(btn);
    personaList.appendChild(li);

    const checkbox = document.createElement("label");
    checkbox.className = "option-row";
    checkbox.innerHTML = `<input type="checkbox" value="${p.id}"> <span>${p.name} (${p.age}/${p.gender})</span>`;
    personaOptions.appendChild(checkbox);
  });
}

function renderCriteria(criteria) {
  criterionList.innerHTML = "";
  criterionOptions.innerHTML = "";
  if (criterionCount) criterionCount.textContent = criteria.length;
  criteria.forEach((c) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${c.label}</strong> - ${c.question}`;
    const btn = document.createElement("button");
    btn.textContent = "Delete";
    btn.onclick = async () => {
      await fetch(`/api/criteria/${c.id}`, { method: "DELETE" });
      loadCriteria();
    };
    li.appendChild(btn);
    criterionList.appendChild(li);

    const checkbox = document.createElement("label");
    checkbox.className = "option-row";
    checkbox.innerHTML = `<input type="checkbox" value="${c.id}"> <span>${c.label}</span>`;
    criterionOptions.appendChild(checkbox);
  });
}

function renderTemplates(templates) {
  templateList.innerHTML = "";
  templateSelect.innerHTML = '<sl-option value="">Not specified</sl-option>';
  if (templateCount) templateCount.textContent = templates.length;
  templates.forEach((t) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${t.name}</strong> - ${t.description || ""}`;
    const btn = document.createElement("button");
    btn.textContent = "Delete";
    btn.onclick = async () => {
      await fetch(`/api/prompt-templates/${t.id}`, { method: "DELETE" });
      loadTemplates();
    };
    li.appendChild(btn);
    templateList.appendChild(li);

    const option = document.createElement("sl-option");
    option.value = t.id;
    option.textContent = t.name;
    templateSelect.appendChild(option);
  });
}

function renderTasks(data) {
  taskList.innerHTML = "";
  if (taskCount) taskCount.textContent = data.length;
  if (taskDone) taskDone.textContent = data.filter((d) => d.task.status === "completed").length;
  if (taskFailed) taskFailed.textContent = data.filter((d) => d.task.status === "failed").length;
  data.forEach(({ task, results }) => {
    const wrapper = document.createElement("div");
    wrapper.className = "task-card";
    const header = document.createElement("div");
    header.className = "task-header";
    const statusClass =
      task.status === "completed" ? "success" : task.status === "failed" ? "error" : "";
    header.innerHTML = `<div><strong>${task.title}</strong>
      <div class="meta"><span class="status-pill ${statusClass}">${task.status}</span><span class="timestamp">${task.created_at}</span></div></div>`;
    wrapper.appendChild(header);
    if (task.error) {
      const err = document.createElement("div");
      err.className = "error";
      err.textContent = task.error;
      wrapper.appendChild(err);
    }
    const details = document.createElement("div");
    const ctx = task.operation_context || {};
    const ctxText = Object.entries(ctx)
      .filter(([, v]) => v)
      .map(([k, v]) => `${k}:${v}`)
      .join(" | ");
    const templateLabel = task.prompt_template_id ? `Template #${task.prompt_template_id}` : "Template not set";
    details.innerHTML = `<p class="muted">${task.stimulus_text || "(no text)"}</p>
      <div class="meta-line">${ctxText || "No operations context"}</div>
      <div class="meta-line chips"><span class="chip">${templateLabel}</span><span class="chip">Similarity: ${task.similarity_method}</span><span class="chip">Seed: ${task.run_seed ?? "-"}</span></div>`;
    wrapper.appendChild(details);

    const resList = document.createElement("ul");
    results.forEach((r) => {
      const li = document.createElement("li");
      li.innerHTML = `<div>${r.summary}</div><div class="distribution">Distribution: ${r.distribution
        .map((v, idx) => `${idx + 1}:${v}`)
        .join(" | ")} / Mode: ${r.rating}</div>`;
      resList.appendChild(li);
    });
    wrapper.appendChild(resList);

    const controls = document.createElement("div");
    controls.className = "task-actions";
    const requeue = document.createElement("button");
    requeue.textContent = "Re-queue";
    requeue.onclick = async () => {
      await fetchJSON(`/api/tasks/${task.id}/enqueue`, { method: "POST" });
      loadTasks();
    };
    const pdf = document.createElement("a");
    pdf.textContent = "PDF report";
    pdf.className = "ghost";
    pdf.href = `/api/tasks/${task.id}/report`;
    pdf.target = "_blank";
    controls.appendChild(requeue);
    controls.appendChild(pdf);
    wrapper.appendChild(controls);

    taskList.appendChild(wrapper);
  });
}

function renderSessions(files) {
  sessionList.innerHTML = "";
  files.forEach((f) => {
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = `/api/sessions/${f.path}`;
    link.textContent = `${f.path} (updated: ${f.updated})`;
    li.appendChild(link);
    sessionList.appendChild(li);
  });
}

function renderBenchmarks(benchmarks) {
  benchmarkList.innerHTML = "";
  benchmarks.forEach((b) => {
    const li = document.createElement("li");
    const tag = b.session_label ? `${b.session_label}` : b.label;
    li.innerHTML = `<strong>${tag}</strong> / ${b.criterion_label} / n=${b.sample_size} / [${b.distribution
      .map((v) => v.toFixed(3))
      .join(", ")} ]`;
    const btn = document.createElement("button");
    btn.textContent = "Delete";
    btn.onclick = async () => {
      await fetch(`/api/benchmarks/${b.id}`, { method: "DELETE" });
      loadBenchmarks();
      loadEvaluations();
    };
    li.appendChild(btn);
    benchmarkList.appendChild(li);
  });
}

function renderEvaluations(report) {
  evaluationTable.innerHTML = "";
  report.matches.forEach((m) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${m.title}</td>
      <td>${m.session_label || "-"}</td>
      <td>${m.criterion}</td>
      <td>${m.ks_similarity.toFixed(3)}</td>
      <td>${m.human_mean.toFixed(2)}</td>
      <td>${m.synthetic_mean.toFixed(2)}</td>
      <td>${m.sample_size}</td>`;
    evaluationTable.appendChild(row);
  });
  evaluationSummary.textContent = `Correlation attainment: ${report.correlation_attainment.toFixed(3)} / ceiling: ${report.ceiling.toFixed(3)} `;
}

function updateAggregateChart(summary) {
  const ctx = document.getElementById("aggregate-chart");
  const labels = summary.map((s) => `${s.gender}/${s.age} ${s.criterion}`);
  const values = summary.map((s) => s.average);
  if (aggregateChart) {
    aggregateChart.data.labels = labels;
    aggregateChart.data.datasets[0].data = values;
    aggregateChart.update();
  } else {
    aggregateChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Mean score (1-5)",
            data: values,
            backgroundColor: "rgba(75, 192, 192, 0.5)",
            borderColor: "rgb(75, 192, 192)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        scales: {
          y: { beginAtZero: true, max: 5 },
        },
      },
    });
  }
}

async function loadPersonas() {
  const personas = await fetchJSON("/api/personas");
  renderPersonas(personas);
}

async function loadCriteria() {
  const criteria = await fetchJSON("/api/criteria");
  renderCriteria(criteria);
}

async function loadTemplates() {
  const templates = await fetchJSON("/api/prompt-templates");
  renderTemplates(templates);
}

async function loadTasks() {
  const tasks = await fetchJSON("/api/tasks");
  renderTasks(tasks);
}

async function loadAggregates() {
  const data = await fetchJSON("/api/aggregates");
  updateAggregateChart(data);
}

async function loadSessions() {
  const files = await fetchJSON("/api/sessions");
  renderSessions(files);
}

async function loadBenchmarks() {
  const benchmarks = await fetchJSON("/api/benchmarks");
  renderBenchmarks(benchmarks);
}

async function loadEvaluations() {
  const report = await fetchJSON("/api/evaluate");
  renderEvaluations(report);
}

async function refreshAll() {
  try {
    await Promise.all([
      loadTasks(),
      loadAggregates(),
      loadSessions(),
      loadBenchmarks(),
      loadEvaluations(),
    ]);
    markRefreshed();
  } catch (err) {
    if (refreshClock) refreshClock.textContent = `Error: ${err.message}`;
  }
}

async function toBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function gatherSelections(container) {
  return Array.from(container.querySelectorAll("input[type='checkbox']:checked")).map((el) =>
    Number(el.value)
  );
}

function parseDistribution(text) {
  return text
    .split(/[,\s]+/)
    .map((v) => Number(v))
    .filter((v) => !Number.isNaN(v));
}

function markRefreshed() {
  if (!refreshClock) return;
  const now = new Date();
  const hh = now.getHours().toString().padStart(2, "0");
  const mm = now.getMinutes().toString().padStart(2, "0");
  const ss = now.getSeconds().toString().padStart(2, "0");
  refreshClock.textContent = `Updated ${hh}:${mm}:${ss}`;
}

personaForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(personaForm);
  const payload = {
    name: formData.get("name"),
    age: Number(formData.get("age")),
    gender: formData.get("gender"),
    notes: formData.get("notes"),
  };
  await fetchJSON("/api/personas", { method: "POST", body: JSON.stringify(payload) });
  personaForm.reset();
  loadPersonas();
});

criterionForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(criterionForm);
  const anchorsText = (formData.get("anchors") || "").toString();
  const anchors = anchorsText
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  const payload = {
    label: formData.get("label"),
    question: formData.get("question"),
    anchors: anchors.length ? anchors : undefined,
  };
  await fetchJSON("/api/criteria", { method: "POST", body: JSON.stringify(payload) });
  loadCriteria();
});

templateForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(templateForm);
  const payload = {
    name: formData.get("name"),
    description: formData.get("description"),
    content: formData.get("content"),
  };
  await fetchJSON("/api/prompt-templates", { method: "POST", body: JSON.stringify(payload) });
  templateForm.reset();
  loadTemplates();
});

benchmarkForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(benchmarkForm);
  const distribution = parseDistribution(formData.get("distribution") || "");
  const payload = {
    label: formData.get("label"),
    session_label: formData.get("session_label") || null,
    criterion_label: formData.get("criterion_label"),
    distribution,
    sample_size: Number(formData.get("sample_size") || 100),
  };
  await fetchJSON("/api/benchmarks", { method: "POST", body: JSON.stringify(payload) });
  benchmarkForm.reset();
  loadBenchmarks();
  loadEvaluations();
});

taskForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  taskStatus.textContent = "Submitting...";
  const formData = new FormData(taskForm);
  const personaIds = await gatherSelections(personaOptions);
  const criterionIds = await gatherSelections(criterionOptions);
  if (!personaIds.length || !criterionIds.length) {
    taskStatus.textContent = "Select at least one persona and criterion";
    return;
  }
  const file = formData.get("image");
  let imageData = null;
  let imageName = null;
  if (file && file.size > 0) {
    imageData = await toBase64(file);
    imageName = file.name;
  }
  const templateIdRaw = formData.get("prompt_template_id");
  const payload = {
    title: formData.get("title"),
    stimulus_text: formData.get("stimulus_text"),
    image_name: imageName,
    image_data: imageData,
    guidance: formData.get("guidance"),
    session_label: formData.get("session_label"),
    persona_ids: personaIds,
    criterion_ids: criterionIds,
    prompt_template_id: templateIdRaw ? Number(templateIdRaw) : null,
    similarity_method: formData.get("similarity_method") || "codex",
    run_seed: formData.get("run_seed") ? Number(formData.get("run_seed")) : null,
    operation_context: {
      game_title: formData.get("game_title"),
      genre: formData.get("genre"),
      target_metric: formData.get("target_metric"),
      liveops_cadence: formData.get("liveops_cadence"),
      monetization: formData.get("monetization"),
      seasonality: formData.get("seasonality"),
      notes: formData.get("notes"),
    },
  };
  const description = formData.get("image_description");
  if (description) {
    payload.stimulus_text = `${payload.stimulus_text || ""}\nImage note: ${description}`.trim();
  }
  try {
    await fetchJSON("/api/tasks", { method: "POST", body: JSON.stringify(payload) });
    taskStatus.textContent = "Queued successfully";
    taskForm.reset();
    loadTasks();
    loadAggregates();
    loadSessions();
  } catch (err) {
    taskStatus.textContent = `Error: ${err.message}`;
  }
});

bootstrapBtn.addEventListener("click", async () => {
  bootstrapStatus.textContent = "Seeding...";
  try {
    const res = await fetchJSON("/api/bootstrap", { method: "POST" });
    bootstrapStatus.textContent = JSON.stringify(res);
    loadPersonas();
    loadCriteria();
    loadTemplates();
  } catch (err) {
    bootstrapStatus.textContent = `Error: ${err.message}`;
  }
});

evaluateBtn.addEventListener("click", async () => {
  evaluationSummary.textContent = "Calculating...";
  try {
    const report = await fetchJSON("/api/evaluate");
    renderEvaluations(report);
  } catch (err) {
    evaluationSummary.textContent = `Error: ${err.message}`;
  }
});

document.querySelectorAll("[data-scroll]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = document.querySelector(btn.dataset.scroll);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

if (forceRefresh) {
  forceRefresh.addEventListener("click", () => {
    refreshAll();
  });
}

function startPolling() {
  refreshAll();
  setInterval(() => {
    refreshAll();
  }, 5000);
}

loadPersonas();
loadCriteria();
loadTemplates();
startPolling();
