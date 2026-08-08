const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[char]));
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `请求失败: ${response.status}`);
  return payload;
}

function setTaskResult(title, body, error = false) {
  const node = $("#task-result");
  node.hidden = false;
  node.className = `result${error ? " error" : ""}`;
  node.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span>`;
}

function renderSnapshots(items) {
  const body = $("#snapshot-table");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5" class="muted">还没有可展示的研究快照</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const review = item.review_only || item.status === "REVIEW_REQUIRED";
    return `<tr>
      <td><strong>${escapeHtml(item.id)}</strong><br><span class="muted">${escapeHtml(item.directory)}</span></td>
      <td>${escapeHtml(item.schema_version)}</td>
      <td><span class="tag${review ? " review" : ""}">${escapeHtml(item.status)}</span></td>
      <td>${escapeHtml(item.as_of || "-")}</td>
      <td>${item.execution_enabled ? '<span class="tag review">需检查</span>' : '<span class="tag">执行关闭</span>'}</td>
    </tr>`;
  }).join("");
}

async function refreshConsole() {
  const [health, summary, snapshots] = await Promise.all([
    request("/api/health"), request("/api/summary"), request("/api/snapshots?limit=100")
  ]);
  $("#runtime-status").textContent = `${health.mode} · 执行已关闭`;
  $("#snapshot-count").textContent = summary.snapshot_count;
  $("#task-count").textContent = summary.schema_counts["research-task-resolution.v1"] || 0;
  $("#review-count").textContent = summary.status_counts.REVIEW_REQUIRED || 0;
  $("#execution-state").textContent = health.execution_enabled ? "开启" : "关闭";
  const status = Object.entries(summary.status_counts);
  $("#status-summary").innerHTML = status.length
    ? status.map(([key, value]) => `<div class="status-line"><span>${escapeHtml(key)}</span><span>${value}</span></div>`).join("")
    : '<p class="muted">暂无快照状态</p>';
  renderSnapshots(snapshots.snapshots);
}

$("#task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  if (!payload.research_as_of) delete payload.research_as_of;
  try {
    const response = await request("/api/resolve-task", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    const task = response.task;
    setTaskResult("任务已保存", `${task.task_type} / ${task.subject_type} / ${task.status}，ID: ${task.task_id}`);
    await refreshConsole();
  } catch (error) {
    setTaskResult("任务未保存", error.message, true);
  }
});

$("#refresh-button").addEventListener("click", () => refreshConsole().catch((error) => setTaskResult("读取失败", error.message, true)));
refreshConsole().catch((error) => {
  $("#runtime-status").textContent = "本地服务不可用";
  setTaskResult("控制台未就绪", error.message, true);
});
