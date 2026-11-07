"use strict";

const tokenField = document.querySelector("#operator-token");
const connectButton = document.querySelector("#connect-button");
const refreshButton = document.querySelector("#refresh-button");
const disconnectButton = document.querySelector("#disconnect-button");
const checkMcpButton = document.querySelector("#check-mcp-button");
const queueButton = document.querySelector("#queue-button");
const approveButton = document.querySelector("#approve-button");
const reviewConfirmed = document.querySelector("#review-confirmed");
const generateButton = document.querySelector("#generate-button");
const generateStudioButton = document.querySelector("#generate-studio-button");
const spendConfirmed = document.querySelector("#spend-confirmed");
const studioSpendConfirmed = document.querySelector("#studio-spend-confirmed");
const quoteButton = document.querySelector("#quote-button");
const studioQuoteButton = document.querySelector("#quote-studio-button");
const gamePlanBrief = document.querySelector("#game-plan-brief");
const gamePlanQuoteButton = document.querySelector("#game-plan-quote-button");
const gamePlanGenerateButton = document.querySelector("#game-plan-generate-button");
const gamePlanSpendConfirmed = document.querySelector("#game-plan-spend-confirmed");
const usePlanWorldBriefButton = document.querySelector("#use-plan-world-brief");
const downloadGamePlanButton = document.querySelector("#download-game-plan");
const codePreviewDescription = document.querySelector("#code-preview-description");
const codePreviewScope = document.querySelector("#code-preview-scope");
const codePreviewQuoteButton = document.querySelector("#code-preview-quote-button");
const codePreviewGenerateButton = document.querySelector("#code-preview-generate-button");
const codePreviewSpendConfirmed = document.querySelector("#code-preview-spend-confirmed");
const worldBrief = document.querySelector("#world-brief");
const actionField = document.querySelector("#action-json");
const workIdField = document.querySelector("#work-id");
const connectionState = document.querySelector("#connection-state");
const footerMessage = document.querySelector("#footer-message");
const queueResult = document.querySelector("#queue-result");
const approveResult = document.querySelector("#approve-result");
const worldResult = document.querySelector("#world-result");
const quoteResult = document.querySelector("#quote-result");
const studioQuoteResult = document.querySelector("#studio-quote-result");
const gamePlanQuoteResult = document.querySelector("#game-plan-quote-result");
const gamePlanResult = document.querySelector("#game-plan-result");
const codePreviewQuoteResult = document.querySelector("#code-preview-quote-result");
const codePreviewResult = document.querySelector("#code-preview-result");
const remoteBlenderReview = document.querySelector("#remote-blender-review");
const remoteBlenderApply = document.querySelector("#remote-blender-apply");
const remoteBlenderDownload = document.querySelector("#remote-blender-download");
const remoteRobloxAssetReview = document.querySelector("#remote-roblox-asset-review");
const remoteRobloxAssetUpload = document.querySelector("#remote-roblox-asset-upload");
const remoteRobloxAssetStatus = document.querySelector("#remote-roblox-asset-status");
const remoteRobloxImportReview = document.querySelector("#remote-roblox-import-review");
const remoteRobloxImportReviewRow = document.querySelector("#remote-roblox-import-review-row");
const remoteBlenderResult = document.querySelector("#remote-blender-result");
const remoteRobloxReview = document.querySelector("#remote-roblox-review");
const remoteRobloxGameMode = document.querySelector("#roblox-gameplay-mode");
const remoteRobloxValidate = document.querySelector("#remote-roblox-validate");
const remoteRobloxBuild = document.querySelector("#remote-roblox-build");
const remoteRobloxResult = document.querySelector("#remote-roblox-result");
const remoteRobloxPublishReview = document.querySelector("#remote-roblox-publish-review");
const remoteRobloxPublish = document.querySelector("#remote-roblox-publish");
const remoteRobloxPublishReviewRow = document.querySelector("#remote-roblox-publish-review-row");
const recipeStudioReview = document.querySelector("#recipe-studio-review");
const queueRecipeStudioButton = document.querySelector("#queue-recipe-studio");
const recipeStudioResult = document.querySelector("#recipe-studio-result");
let operatorToken = "";
let selectedWork = null;
let worldGenerationEnabled = false;
let worldQuoteEnabled = false;
let gamePlanEnabled = false;
let gamePlanQuoteEnabled = false;
let codePreviewEnabled = false;
let codePreviewQuoteEnabled = false;
let studioActionGenerationEnabled = false;
let studioActionQuoteEnabled = false;
let blenderMcpEnabled = false;
let robloxMcpEnabled = false;
let robloxAssetUploadEnabled = false;
let robloxPlacePublishEnabled = false;
let robloxPlacePublishHealth = null;
let blenderMcpHealth = null;
let robloxMcpHealth = null;
let mcpHealthPending = false;
let currentRecipe = null;
let currentArtifactId = null;
let currentAssetUploadRequestId = null;
let currentAssetUploadApprovalId = null;
let currentRobloxModelAssetId = null;
let currentBlenderRequestId = null;
let currentRobloxRequestId = null;
let currentRobloxBuild = null;
let currentStudioRecipeRequestId = null;
let recipeDownloadUrl = "";
let currentQuote = null;
let currentStudioQuote = null;
let currentGamePlanQuote = null;
let currentGamePlan = null;
let currentPlannedGameplayRules = null;
let applyingGamePlanMapBrief = false;
let currentCodePreviewQuote = null;
let quotePending = false;
let quoteRequestId = 0;
let studioQuotePending = false;
let studioQuoteRequestId = 0;
let gamePlanQuoteRequestId = 0;
let generationPending = false;
let gamePlanPending = false;
let gamePlanQuotePending = false;
let codePreviewPending = false;
let codePreviewQuotePending = false;
let codePreviewQuoteRequestId = 0;
let recipeStudioQueuePending = false;

function setNotice(element, message, kind = "") {
  element.textContent = message;
  element.className = `notice ${kind}`.trim();
}

function setConnected(connected) {
  connectionState.textContent = connected ? "Connected" : "Disconnected";
  connectionState.classList.toggle("connected", connected);
  disconnectButton.disabled = !connected;
  checkMcpButton.disabled =
    !connected || mcpHealthPending || (!blenderMcpEnabled && !robloxMcpEnabled);
  queueButton.disabled = !connected;
  updateApprovalGate();
  const quoteMatchesBrief = currentQuote?.brief === worldBrief.value.trim();
  const studioQuoteMatchesBrief = currentStudioQuote?.brief === worldBrief.value.trim();
  const planQuoteMatchesBrief = currentGamePlanQuote?.brief === gamePlanBrief.value.trim();
  const codeTask = getCodePreviewTask();
  const codeQuoteMatchesTask = currentCodePreviewQuote?.task === stableStringify(codeTask);
  quoteButton.disabled =
    !connected || !worldQuoteEnabled || quotePending || generationPending || gamePlanPending || !worldBrief.value.trim();
  spendConfirmed.disabled = !connected || !worldGenerationEnabled || !quoteMatchesBrief;
  studioQuoteButton.disabled =
    !connected || !studioActionQuoteEnabled || studioQuotePending || generationPending || gamePlanPending || !worldBrief.value.trim();
  studioSpendConfirmed.disabled =
    !connected || !studioActionQuoteEnabled || !studioQuoteMatchesBrief;
  generateButton.disabled =
    !connected || generationPending || gamePlanPending || !worldGenerationEnabled || !quoteMatchesBrief || !spendConfirmed.checked;
  generateStudioButton.disabled =
    !connected || generationPending || gamePlanPending || !studioActionGenerationEnabled || !studioQuoteMatchesBrief || !studioSpendConfirmed.checked;
  gamePlanQuoteButton.disabled =
    !connected || !gamePlanQuoteEnabled || gamePlanQuotePending || generationPending || gamePlanPending || !gamePlanBrief.value.trim();
  gamePlanSpendConfirmed.disabled = !connected || !gamePlanEnabled || !planQuoteMatchesBrief;
  gamePlanGenerateButton.disabled =
    !connected || !gamePlanEnabled || gamePlanPending || generationPending || !planQuoteMatchesBrief || !gamePlanSpendConfirmed.checked;
  codePreviewQuoteButton.disabled = !connected || !codePreviewQuoteEnabled || codePreviewQuotePending || codePreviewPending || !codeTask;
  codePreviewSpendConfirmed.disabled = !connected || !codePreviewEnabled || !codeQuoteMatchesTask;
  codePreviewGenerateButton.disabled = !connected || !codePreviewEnabled || codePreviewPending || !codeQuoteMatchesTask || !codePreviewSpendConfirmed.checked;
  usePlanWorldBriefButton.disabled = !connected || !currentGamePlan;
  downloadGamePlanButton.disabled = !currentGamePlan;
  remoteBlenderReview.disabled = !connected || !blenderMcpEnabled || !currentRecipe;
  remoteBlenderApply.disabled = !connected || !blenderMcpEnabled || !currentRecipe || !remoteBlenderReview.checked;
  remoteBlenderDownload.disabled = !connected || !currentArtifactId;
  remoteRobloxAssetReview.disabled =
    !connected || !robloxAssetUploadEnabled || !currentArtifactId;
  remoteRobloxAssetUpload.hidden = !robloxAssetUploadEnabled || !currentArtifactId;
  remoteRobloxAssetStatus.hidden = !robloxAssetUploadEnabled || !currentAssetUploadRequestId;
  remoteRobloxAssetStatus.disabled = !connected || remoteRobloxAssetStatus.hidden;
  remoteRobloxAssetUpload.disabled =
    !connected || !robloxAssetUploadEnabled || !currentArtifactId || !remoteRobloxAssetReview.checked;
  remoteRobloxImportReviewRow.hidden = !currentRobloxModelAssetId;
  remoteRobloxImportReview.disabled =
    !connected || !currentRobloxModelAssetId || remoteRobloxGameMode.value !== "blockout";
  remoteRobloxReview.disabled = !connected || !robloxMcpEnabled || !currentRecipe;
  remoteRobloxGameMode.disabled = !connected || !robloxMcpEnabled || !currentRecipe;
  remoteRobloxValidate.hidden = robloxMcpHealth?.validationAvailable === false;
  remoteRobloxValidate.disabled = remoteRobloxValidate.hidden || !connected || !robloxMcpEnabled || !currentRecipe || !remoteRobloxReview.checked;
  remoteRobloxBuild.disabled = !connected || !robloxMcpEnabled || !currentRecipe || !remoteRobloxReview.checked;
  const publishAvailable = robloxPlacePublishHealth?.state === "available";
  remoteRobloxPublishReviewRow.hidden = !robloxPlacePublishEnabled || !currentRobloxBuild;
  remoteRobloxPublishReview.disabled =
    !connected || !publishAvailable || !currentRobloxBuild;
  remoteRobloxPublish.hidden = !robloxPlacePublishEnabled || !currentRobloxBuild;
  remoteRobloxPublish.disabled =
    !connected || !publishAvailable || !currentRobloxBuild || !remoteRobloxPublishReview.checked;
  recipeStudioReview.disabled = !connected || !currentRecipe || recipeStudioQueuePending;
  queueRecipeStudioButton.disabled =
    !connected || !currentRecipe || !recipeStudioReview.checked || recipeStudioQueuePending;
  document.querySelector("#world-availability").textContent = !connected
    ? "Connect to check"
    : worldGenerationEnabled && worldQuoteEnabled
      ? "Provider ready · budget enforced"
      : worldGenerationEnabled
        ? "Cost quote unavailable"
        : "Generation disabled";
  document.querySelector("#world-availability").classList.toggle("muted", !worldGenerationEnabled);
  document.querySelector("#game-plan-availability").textContent = !connected
    ? "Connect to check"
    : gamePlanEnabled && gamePlanQuoteEnabled
      ? "Provider ready · budget enforced"
      : gamePlanEnabled
        ? "Cost quote unavailable"
        : "Planning disabled";
  document.querySelector("#game-plan-availability").classList.toggle("muted", !gamePlanEnabled);
  document.querySelector("#code-preview-availability").textContent = !connected
    ? "Connect to check"
    : codePreviewEnabled && codePreviewQuoteEnabled
      ? "Lute parser and static gate ready"
      : "Preview disabled · check provider and pinned Lute setup";
  document.querySelector("#code-preview-availability").classList.toggle("muted", !codePreviewEnabled);
  footerMessage.textContent = connected
    ? "Actions still require separate API and Studio approvals."
    : "Operator access is disabled until configured.";
}

function getCodePreviewTask() {
  const description = codePreviewDescription.value.trim();
  const scope = codePreviewScope.value.split(/\r?\n/).map((path) => path.trim()).filter(Boolean);
  return description && scope.length ? { description, scope } : null;
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function updateApprovalGate() {
  let matchesSelected = false;
  if (selectedWork && workIdField.value.trim() === selectedWork.work_id) {
    try {
      matchesSelected = stableStringify(JSON.parse(actionField.value)) === stableStringify(selectedWork.item);
    } catch {
      matchesSelected = false;
    }
  }
  reviewConfirmed.disabled = !operatorToken || !matchesSelected;
  if (!matchesSelected) reviewConfirmed.checked = false;
  approveButton.disabled = !operatorToken || !matchesSelected || !reviewConfirmed.checked;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${operatorToken}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
    cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.status !== "ok") {
    throw new Error(body.error?.message || `API request failed (${response.status})`);
  }
  return body;
}

async function refreshStatus() {
  if (!operatorToken) return;
  try {
    const [status, queue, events] = await Promise.all([
      request("/v1/operator/status"),
      request("/v1/operator/work"),
      request("/v1/operator/events"),
    ]);
    const { data } = status;
    worldGenerationEnabled = status.world_generation_enabled === true;
    worldQuoteEnabled = status.world_quote_enabled === true;
    gamePlanEnabled = status.game_plan_enabled === true;
    gamePlanQuoteEnabled = status.game_plan_quote_enabled === true;
    codePreviewEnabled = status.code_preview_enabled === true;
    codePreviewQuoteEnabled = status.code_preview_quote_enabled === true;
    studioActionGenerationEnabled = status.studio_action_generation_enabled === true;
    studioActionQuoteEnabled = status.studio_action_quote_enabled === true;
    blenderMcpEnabled = status.blender_mcp_enabled === true;
    robloxMcpEnabled = status.roblox_mcp_enabled === true;
    robloxAssetUploadEnabled = status.roblox_asset_upload_enabled === true;
    robloxPlacePublishEnabled = status.roblox_place_publish_enabled === true;
    if (!blenderMcpEnabled) blenderMcpHealth = null;
    if (!robloxMcpEnabled) robloxMcpHealth = null;
    renderMcpHealth();
    document.querySelector("#session-value").textContent = data.session || "No active Studio session";
    document.querySelector("#lock-value").textContent = data.locked ? `Locked · ${data.triggers.join(", ")}` : "Clear";
    document.querySelector("#snapshot-value").textContent = data.current_snapshot || "No snapshot";
    document.querySelector("#events-value").textContent = String(data.events);
    const spend = status.spend_budget;
    document.querySelector("#spend-value").textContent = spend
      ? `USD ${spend.spent_usd} spent · USD ${spend.remaining_usd} left / USD ${spend.limit_usd} cap${spend.reserved_usd === "0" ? "" : ` · USD ${spend.reserved_usd} reserved`}`
      : "No model budget configured";
    renderWork(queue.items);
    renderEvents(events.events, events.total, events.truncated);
    setConnected(true);
  } catch (error) {
    worldGenerationEnabled = false;
    worldQuoteEnabled = false;
    currentQuote = null;
    studioActionGenerationEnabled = false;
    studioActionQuoteEnabled = false;
    currentStudioQuote = null;
    codePreviewEnabled = false;
    codePreviewQuoteEnabled = false;
    currentCodePreviewQuote = null;
    codePreviewSpendConfirmed.checked = false;
    document.querySelector("#code-preview-output").hidden = true;
    blenderMcpEnabled = false;
    robloxMcpEnabled = false;
    robloxAssetUploadEnabled = false;
    blenderMcpHealth = null;
    robloxMcpHealth = null;
    setConnected(false);
    connectionState.textContent = "Connection failed";
    for (const selector of [
      "#session-value",
      "#lock-value",
      "#snapshot-value",
      "#events-value",
      "#spend-value",
      "#blender-connection-value",
      "#roblox-connection-value",
    ]) {
      document.querySelector(selector).textContent = "—";
    }
    document.querySelector("#work-list").replaceChildren();
    document.querySelector("#event-log").replaceChildren();
    setNotice(queueResult, error.message, "error");
  }
}

function renderMcpHealth() {
  const describe = (configured, health) => {
    if (!configured) return "Not configured";
    if (!health) return "Configured · check not run";
    const checked = new Date(health.checkedAt).toLocaleTimeString();
    const label = health.state === "failed"
      ? "Check failed"
      : health.state === "available"
        ? "Available"
        : "Unavailable";
    return `${label} · checked ${checked}`;
  };
  document.querySelector("#blender-connection-value").textContent = describe(
    blenderMcpEnabled,
    blenderMcpHealth,
  );
  document.querySelector("#roblox-connection-value").textContent = describe(
    robloxMcpEnabled,
    robloxMcpHealth,
  );
}

checkMcpButton.addEventListener("click", async () => {
  if (!operatorToken || mcpHealthPending) return;
  const requestToken = operatorToken;
  mcpHealthPending = true;
  checkMcpButton.textContent = "Checking…";
  setConnected(connectionState.textContent === "Connected");
  try {
    const result = await request("/v1/operator/mcp-health", { method: "POST", body: "{}" });
    if (operatorToken !== requestToken) return;
    const checkedAt = Date.now();
    blenderMcpHealth = result.blender_mcp === "not_configured"
      ? null
      : { state: result.blender_mcp, checkedAt };
    robloxMcpHealth = result.roblox_mcp === "not_configured"
      ? null
      : { state: result.roblox_mcp, validationAvailable: result.roblox_map_validation_available, checkedAt };
    robloxPlacePublishHealth = result.roblox_place_publish === "not_configured"
      ? null
      : { state: result.roblox_place_publish, checkedAt };
    renderMcpHealth();
  } catch {
    if (operatorToken !== requestToken) return;
    const checkedAt = Date.now();
    blenderMcpHealth = blenderMcpEnabled ? { state: "failed", checkedAt } : null;
    robloxMcpHealth = robloxMcpEnabled ? { state: "failed", checkedAt } : null;
    robloxPlacePublishHealth = robloxPlacePublishEnabled
      ? { state: "failed", checkedAt }
      : null;
    renderMcpHealth();
  } finally {
    mcpHealthPending = false;
    checkMcpButton.textContent = "Check remote MCPs";
    setConnected(connectionState.textContent === "Connected");
  }
});

function renderEvents(events, total, truncated) {
  const log = document.querySelector("#event-log");
  log.replaceChildren();
  if (!events.length) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = "No API lifecycle events yet.";
    log.append(empty);
    return;
  }
  if (truncated) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = `Showing the latest ${events.length} of ${total} recorded events.`;
    log.append(note);
  }
  const workflows = new Map();
  const entries = [];
  for (const event of events) {
    const workflowId = event.workflow_id || event.request_id || event.run_id;
    if (workflowId) {
      if (!workflows.has(workflowId)) {
        const workflow = { id: workflowId, events: [] };
        workflows.set(workflowId, workflow);
        entries.push(workflow);
      }
      workflows.get(workflowId).events.push(event);
    } else {
      entries.push({ events: [event] });
    }
  }
  entries.sort((left, right) => latestEventTime(right) - latestEventTime(left));
  for (const entry of entries) {
    if (entry.id) {
      const group = document.createElement("section");
      group.className = "workflow-group";
      const heading = document.createElement("h3");
      heading.className = "workflow-heading";
      heading.textContent = `${workflowLabel(entry.events)} · ${entry.id}`;
      group.append(heading);
      for (const event of [...entry.events].reverse()) group.append(renderEventRow(event));
      log.append(group);
    } else {
      log.append(renderEventRow(entry.events[0]));
    }
  }
}

function latestEventTime(entry) {
  return Math.max(...entry.events.map((event) => Number(event.at) || 0));
}

function workflowLabel(events) {
  const operation = events.find((event) => typeof event.operation === "string")?.operation;
  const labels = {
    blender_scene_recipe: "Scene workflow",
    studio_blockout: "Studio blockout workflow",
    game_plan: "Game plan run",
    luau_source_preview: "Code preview run",
  };
  return labels[operation] || "Workflow";
}

function renderEventRow(event) {
  const row = document.createElement("div");
  row.className = "event-row";
  const meta = document.createElement("div");
  meta.className = "event-meta";
  const kind = document.createElement("strong");
  kind.textContent = eventLabel(event.kind);
  const time = document.createElement("time");
  time.textContent = Number.isFinite(event.at) && event.at >= 1_000_000_000
    ? new Date(event.at * 1000).toLocaleString()
    : "time unavailable";
  meta.append(kind, time);
  const detail = document.createElement("div");
  detail.className = "event-detail";
  const fields = Object.fromEntries(Object.entries(event).filter(([key]) => !["at", "kind"].includes(key)));
  const modelTrace = fields.model_trace;
  delete fields.model_trace;
  if (Object.keys(fields).length) {
    const list = document.createElement("dl");
    list.className = "event-fields";
    for (const [key, value] of Object.entries(fields)) {
      const term = document.createElement("dt");
      term.textContent = eventFieldLabel(key);
      const description = document.createElement("dd");
      description.textContent = typeof value === "string" ? value : JSON.stringify(value);
      list.append(term, description);
    }
    detail.append(list);
  }
  if (modelTrace && Array.isArray(modelTrace.attempts)) {
    const trace = document.createElement("details");
    trace.className = "model-trace";
    const heading = document.createElement("summary");
    heading.textContent = `Model call trace (${modelTrace.attempts.length})`;
    const calls = document.createElement("ol");
    for (const call of modelTrace.attempts) {
      const item = document.createElement("li");
      item.textContent = `Call ${call.attempt}: ${call.provider} / ${call.model} · input ${call.input_tokens} · output ${call.output_tokens} · USD ${call.cost_usd}`;
      calls.append(item);
    }
    trace.append(heading, calls);
    detail.append(trace);
  }
  if (!detail.childNodes.length) {
    detail.textContent = "No additional details.";
  }
  row.append(meta, detail);
  return row;
}

function eventLabel(kind) {
  const labels = {
    model_generation_succeeded: "Generation completed",
    model_generation_failed: "Generation failed",
    queued: "Action queued for review",
    approved: "Action approved",
    delivered: "Action delivered to Studio",
    result_received: "Studio result received",
    blender_artifact_built: "Blender artifact built",
    roblox_map_validation_completed: "Roblox map validation completed",
    session_opened: "Studio session connected",
    session_ended: "Studio session ended",
    work_blocked_by_policy: "Action blocked by policy",
    lock_engaged: "Workspace safety lock engaged",
    lock_released: "Workspace safety lock released",
  };
  return labels[kind] || String(kind || "Unknown event").replaceAll("_", " ");
}

function eventFieldLabel(key) {
  const labels = {
    run_id: "Run ID",
    workflow_id: "Workflow ID",
    request_id: "Workflow ID",
    work_id: "Action ID",
    operation: "Operation",
    duration_ms: "Duration (ms)",
    failure_stage: "Failed at",
    object_count: "Scene objects",
    light_count: "Lights",
    character_count: "Characters",
    output_bytes: "Output size (bytes)",
    action_id: "Action ID",
    operation_count: "Operations",
    artifact_id: "Artifact ID",
    remote_host: "Remote service",
    validation_status: "Validation status",
    navigation_status: "Navigation status",
    navigation_connected: "Route connected",
    navigation_waypoint_count: "Navigation waypoints",
    path_feature_count: "Path features",
    place_version: "Place version",
    task_id: "Validation task ID",
    recipe_name: "Recipe",
    warnings: "Warnings",
    errors: "Errors",
    session: "Session ID",
    cost_usd: "Model cost (USD)",
    input_tokens: "Input tokens",
    output_tokens: "Output tokens",
    iterations: "Iterations",
    model_trace: "Model call trace",
  };
  return labels[key] || String(key || "Detail").replaceAll("_", " ");
}

function renderWork(items) {
  const list = document.querySelector("#work-list");
  list.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = "No actions in the queue.";
    list.append(empty);
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "work-item";
    const id = document.createElement("span");
    id.className = "work-id";
    id.textContent = item.work_id;
    const state = document.createElement("span");
    state.className = "work-state";
    state.textContent = item.state;
    const knowledge = document.createElement("span");
    knowledge.className = "work-knowledge";
    knowledge.textContent = `${item.knowledge} · ${item.deliveries} deliveries${item.stale_base ? " · stale base" : ""}`;
    const select = document.createElement("button");
    select.className = "button quiet";
    select.type = "button";
    select.textContent = "Review";
    select.disabled = item.state !== "queued";
    select.addEventListener("click", () => {
      actionField.value = JSON.stringify(item.item, null, 2);
      workIdField.value = item.work_id;
      selectedWork = { work_id: item.work_id, item: item.item };
      reviewConfirmed.checked = false;
      updateApprovalGate();
      setNotice(approveResult, "Review the full JSON above, confirm the ID, then check the approval box.");
      document.querySelector("#proposal-title").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    row.append(id, state, knowledge, select);
    list.append(row);
  }
}

connectButton.addEventListener("click", async () => {
  const candidate = tokenField.value;
  if (candidate.length < 32 || candidate.length > 512) {
    setNotice(queueResult, "Enter the configured operator token (32–512 characters).", "error");
    return;
  }
  operatorToken = candidate;
  await refreshStatus();
  if (connectionState.textContent === "Connected") tokenField.value = "";
  else operatorToken = "";
});

refreshButton.addEventListener("click", refreshStatus);

disconnectButton.addEventListener("click", () => {
  operatorToken = "";
  tokenField.value = "";
  selectedWork = null;
  worldGenerationEnabled = false;
  worldQuoteEnabled = false;
  gamePlanEnabled = false;
  gamePlanQuoteEnabled = false;
  codePreviewEnabled = false;
  codePreviewQuoteEnabled = false;
  studioActionGenerationEnabled = false;
  studioActionQuoteEnabled = false;
  blenderMcpEnabled = false;
  robloxMcpEnabled = false;
  robloxAssetUploadEnabled = false;
  robloxPlacePublishEnabled = false;
  blenderMcpHealth = null;
  robloxMcpHealth = null;
  robloxPlacePublishHealth = null;
  currentRecipe = null;
  currentArtifactId = null;
  currentAssetUploadRequestId = null;
  currentAssetUploadApprovalId = null;
  currentRobloxModelAssetId = null;
  currentBlenderRequestId = null;
  currentRobloxRequestId = null;
  currentRobloxBuild = null;
  remoteRobloxPublishReview.checked = false;
  currentStudioRecipeRequestId = null;
  currentQuote = null;
  currentStudioQuote = null;
  currentGamePlanQuote = null;
  currentGamePlan = null;
  currentCodePreviewQuote = null;
  quotePending = false;
  studioQuotePending = false;
  gamePlanQuotePending = false;
  codePreviewPending = false;
  codePreviewQuotePending = false;
  codePreviewQuoteRequestId += 1;
  generationPending = false;
  gamePlanPending = false;
  gamePlanQuoteRequestId += 1;
  setNotice(quoteResult, "");
  setNotice(studioQuoteResult, "");
  setNotice(gamePlanQuoteResult, "");
  setNotice(gamePlanResult, "");
  setNotice(codePreviewQuoteResult, "");
  setNotice(codePreviewResult, "");
  document.querySelector("#code-preview-output").hidden = true;
  document.querySelector("#game-plan-output").hidden = true;
  gamePlanSpendConfirmed.checked = false;
  codePreviewSpendConfirmed.checked = false;
  remoteBlenderDownload.hidden = true;
  remoteRobloxAssetReview.checked = false;
  remoteRobloxImportReview.checked = false;
  remoteRobloxAssetUpload.hidden = true;
  remoteBlenderReview.checked = false;
  recipeStudioReview.checked = false;
  document.querySelector("#recipe-output").hidden = true;
  reviewConfirmed.checked = false;
  spendConfirmed.checked = false;
  studioSpendConfirmed.checked = false;
  updateApprovalGate();
  for (const selector of [
    "#session-value",
    "#lock-value",
    "#snapshot-value",
    "#events-value",
    "#spend-value",
    "#blender-connection-value",
    "#roblox-connection-value",
  ]) {
    document.querySelector(selector).textContent = "—";
  }
  document.querySelector("#work-list").replaceChildren();
  setConnected(false);
  connectionState.textContent = "Disconnected";
});

reviewConfirmed.addEventListener("change", () => {
  updateApprovalGate();
});

spendConfirmed.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

studioSpendConfirmed.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

gamePlanSpendConfirmed.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

codePreviewSpendConfirmed.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

function clearCodePreviewQuote(message) {
  codePreviewQuoteRequestId += 1;
  codePreviewQuotePending = false;
  currentCodePreviewQuote = null;
  codePreviewSpendConfirmed.checked = false;
  document.querySelector("#code-preview-output").hidden = true;
  setNotice(codePreviewQuoteResult, message);
  setNotice(codePreviewResult, "");
  setConnected(connectionState.textContent === "Connected");
}

codePreviewDescription.addEventListener("input", () => {
  clearCodePreviewQuote("Request a fresh cost estimate after changing the task.");
});

codePreviewScope.addEventListener("input", () => {
  clearCodePreviewQuote("Request a fresh cost estimate after changing the allowed scope.");
});

codePreviewQuoteButton.addEventListener("click", async () => {
  const task = getCodePreviewTask();
  if (!codePreviewQuoteEnabled || !task) return;
  const requestId = ++codePreviewQuoteRequestId;
  codePreviewQuotePending = true;
  currentCodePreviewQuote = null;
  codePreviewSpendConfirmed.checked = false;
  codePreviewQuoteButton.textContent = "Estimating…";
  setConnected(connectionState.textContent === "Connected");
  setNotice(codePreviewQuoteResult, "Requesting the maximum cost for this scoped code preview…");
  try {
    const quote = await request("/v1/operator/code-preview-quote", {
      method: "POST",
      body: JSON.stringify(task),
    });
    if (requestId !== codePreviewQuoteRequestId) return;
    currentCodePreviewQuote = { task: stableStringify(task), ...quote };
    setNotice(
      codePreviewQuoteResult,
      `First call maximum: USD ${quote.first_call_max_usd} · ${quote.provider}/${quote.model}. Session cap: USD ${quote.session_limit_usd}; remaining: USD ${quote.session_remaining_usd}. Every retry is also capped.`,
      "success",
    );
  } catch (error) {
    if (requestId === codePreviewQuoteRequestId) setNotice(codePreviewQuoteResult, error.message, "error");
  } finally {
    if (requestId === codePreviewQuoteRequestId) {
      codePreviewQuotePending = false;
      codePreviewQuoteButton.textContent = "Estimate code cost";
    }
    setConnected(connectionState.textContent === "Connected");
  }
});

codePreviewGenerateButton.addEventListener("click", async () => {
  const task = getCodePreviewTask();
  if (!task || !codePreviewEnabled || !codePreviewSpendConfirmed.checked || currentCodePreviewQuote?.task !== stableStringify(task)) return;
  const requestId = codePreviewQuoteRequestId;
  codePreviewPending = true;
  codePreviewSpendConfirmed.checked = false;
  codePreviewGenerateButton.textContent = "Validating…";
  document.querySelector("#code-preview-output").hidden = true;
  setConnected(connectionState.textContent === "Connected");
  setNotice(codePreviewResult, "Generating a scoped Luau candidate and checking it against the static policy.");
  try {
    const result = await request("/v1/operator/code-preview", {
      method: "POST",
      body: JSON.stringify({ ...task, quote_id: currentCodePreviewQuote.quote_id }),
    });
    if (requestId !== codePreviewQuoteRequestId || result.validation !== "passed") return;
    document.querySelector("#code-preview-source").textContent = result.source;
    document.querySelector("#code-preview-output").hidden = false;
    setNotice(codePreviewResult, `Policy passed · ${result.iterations} attempt(s) · run ${result.run_id}. Execution and Studio delivery are disabled.`, "success");
  } catch (error) {
    if (requestId === codePreviewQuoteRequestId) setNotice(codePreviewResult, error.message, "error");
  } finally {
    if (requestId === codePreviewQuoteRequestId) {
      codePreviewPending = false;
      currentCodePreviewQuote = null;
      setNotice(codePreviewQuoteResult, "Quote cleared after the preview attempt. Request a fresh estimate before another call.");
      codePreviewGenerateButton.textContent = "Generate validated preview";
    }
    setConnected(connectionState.textContent === "Connected");
    await refreshStatus();
  }
});

gamePlanBrief.addEventListener("input", () => {
  gamePlanQuoteRequestId += 1;
  gamePlanQuotePending = false;
  currentGamePlanQuote = null;
  currentGamePlan = null;
  gamePlanSpendConfirmed.checked = false;
  document.querySelector("#game-plan-output").hidden = true;
  setNotice(gamePlanQuoteResult, "Game idea changed. Request a fresh plan cost estimate before generation.");
  setNotice(gamePlanResult, "");
  setConnected(connectionState.textContent === "Connected");
});

gamePlanQuoteButton.addEventListener("click", async () => {
  const brief = gamePlanBrief.value.trim();
  if (!gamePlanQuoteEnabled || !brief) return;
  const requestId = ++gamePlanQuoteRequestId;
  gamePlanQuotePending = true;
  currentGamePlanQuote = null;
  gamePlanSpendConfirmed.checked = false;
  gamePlanQuoteButton.textContent = "Estimating…";
  setConnected(connectionState.textContent === "Connected");
  setNotice(gamePlanQuoteResult, "Requesting the provider’s maximum cost for the first planning call…");
  try {
    const quote = await request("/v1/operator/game-plan-quote", {
      method: "POST",
      body: JSON.stringify({ brief }),
    });
    if (requestId !== gamePlanQuoteRequestId) return;
    currentGamePlanQuote = { brief, ...quote };
    setNotice(
      gamePlanQuoteResult,
      `First planning call maximum: USD ${quote.first_call_max_usd} · ${quote.provider}/${quote.model}. Session limit: USD ${quote.session_limit_usd}; remaining before generation: USD ${quote.session_remaining_usd}. Retries receive their own quote and must also fit the session limit.`,
      "success",
    );
  } catch (error) {
    if (requestId === gamePlanQuoteRequestId) setNotice(gamePlanQuoteResult, error.message, "error");
  } finally {
    if (requestId === gamePlanQuoteRequestId) {
      gamePlanQuotePending = false;
      gamePlanQuoteButton.textContent = "Estimate plan cost";
    }
    setConnected(connectionState.textContent === "Connected");
  }
});

gamePlanGenerateButton.addEventListener("click", async () => {
  const brief = gamePlanBrief.value.trim();
  if (!gamePlanEnabled || !gamePlanSpendConfirmed.checked || currentGamePlanQuote?.brief !== brief) return;
  gamePlanPending = true;
  gamePlanGenerateButton.textContent = "Planning…";
  gamePlanSpendConfirmed.checked = false;
  document.querySelector("#game-plan-output").hidden = true;
  setConnected(connectionState.textContent === "Connected");
  setNotice(gamePlanResult, "Creating a structured plan under the configured session budget.");
  try {
    const response = await fetch("/v1/operator/game-plan", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${operatorToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ brief }),
      cache: "no-store",
    });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body || body.status === "error") {
      throw new Error(body?.error?.message || `Game planning failed (${response.status})`);
    }
    currentGamePlan = body;
    currentPlannedGameplayRules = null;
    document.querySelector("#game-plan-json").textContent = JSON.stringify(body, null, 2);
    document.querySelector("#game-plan-output").hidden = false;
    const runId = response.headers.get("X-RGA-Run-ID");
    const slice = body.playable_slice;
    const sliceSummary = slice
      ? ` Initial map mode: ${slice.gameplay_mode}; included systems: ${slice.included_systems.join(", ") || "none"}; deferred: ${slice.deferred_systems.join(", ") || "none"}.`
      : " This legacy plan has no playable-slice recommendation.";
    setNotice(
      gamePlanResult,
      `Plan ${runId || "recorded"} generated and validated.${sliceSummary} Review its limitations, then set up the map build when ready.`,
      "success",
    );
  } catch (error) {
    setNotice(gamePlanResult, error.message, "error");
  } finally {
    gamePlanQuoteRequestId += 1;
    gamePlanQuotePending = false;
    gamePlanPending = false;
    currentGamePlanQuote = null;
    gamePlanSpendConfirmed.checked = false;
    setNotice(gamePlanQuoteResult, "Quote cleared after the planning attempt. Request a fresh plan cost estimate before another call.");
    gamePlanGenerateButton.textContent = "Generate game plan";
    setConnected(connectionState.textContent === "Connected");
    await refreshStatus();
  }
});

usePlanWorldBriefButton.addEventListener("click", () => {
  if (!currentGamePlan || typeof currentGamePlan.world_brief !== "string") return;
  const plannedMode = currentGamePlan.playable_slice?.gameplay_mode;
  const plannedRules = currentGamePlan.playable_slice?.gameplay_rules;
  currentPlannedGameplayRules = plannedMode === "rule_game" && Array.isArray(plannedRules)
    ? plannedRules.map((rule) => ({ ...rule }))
    : null;
  const buildRequirements = plannedMode === "obby"
    ? "Playable-slice recipe requirement: include at least two ordered, connected traversal segments with the Scene Recipe role `path`."
    : plannedMode === "treasure_hunt"
      ? "Playable-slice recipe requirement: include a connected route with 1 to 100 route-adjacent objects using the Scene Recipe role `collectible`."
      : plannedMode === "rule_game"
        ? `Playable-slice recipe requirement: include a connected path and every trigger role in these data-only rules: ${JSON.stringify(currentPlannedGameplayRules || [])}. The fixed server interpreter will apply these exact rules; include matching collectible, hazard, prop, or landmark objects along the route as appropriate.`
      : "Playable-slice recipe requirement: create a script-free scene blockout; gameplay code is not generated.";
  applyingGamePlanMapBrief = true;
  worldBrief.value = `${currentGamePlan.world_brief.trim()}\n\n${buildRequirements}`;
  worldBrief.dispatchEvent(new Event("input", { bubbles: true }));
  applyingGamePlanMapBrief = false;
  if (["blockout", "obby", "treasure_hunt", "rule_game"].includes(plannedMode)) {
    remoteRobloxGameMode.value = plannedMode;
    remoteRobloxGameMode.dispatchEvent(new Event("change", { bubbles: true }));
  }
  document.querySelector("#world-title").scrollIntoView({ behavior: "smooth", block: "center" });
  setNotice(
    worldResult,
    `Map brief copied from the plan. Build mode set to ${plannedMode || "blockout"}; review the brief and generated recipe before building.`,
    "success",
  );
});

downloadGamePlanButton.addEventListener("click", () => {
  if (!currentGamePlan) return;
  const json = `${JSON.stringify(currentGamePlan, null, 2)}\n`;
  const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
  const anchor = document.createElement("a");
  const stem = String(currentGamePlan.title || "game-plan")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 48) || "game-plan";
  anchor.href = url;
  anchor.download = `${stem}-plan.json`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
});

worldBrief.addEventListener("input", () => {
  if (!applyingGamePlanMapBrief) currentPlannedGameplayRules = null;
  quoteRequestId += 1;
  studioQuoteRequestId += 1;
  quotePending = false;
  studioQuotePending = false;
  quoteButton.textContent = "Estimate recipe cost";
  studioQuoteButton.textContent = "Estimate Studio blockout cost";
  currentQuote = null;
  currentStudioQuote = null;
  spendConfirmed.checked = false;
  studioSpendConfirmed.checked = false;
  setNotice(quoteResult, "Brief changed. Request a fresh recipe cost estimate before generation.");
  setNotice(studioQuoteResult, "Brief changed. Request a fresh Studio blockout cost estimate before generation.");
  setConnected(connectionState.textContent === "Connected");
});

quoteButton.addEventListener("click", async () => {
  const brief = worldBrief.value.trim();
  if (!worldQuoteEnabled || !brief) return;
  const requestId = ++quoteRequestId;
  quotePending = true;
  quoteButton.disabled = true;
  quoteButton.textContent = "Estimating…";
  currentQuote = null;
  spendConfirmed.checked = false;
  setConnected(connectionState.textContent === "Connected");
  setNotice(quoteResult, "Requesting the provider’s maximum cost for the first generation call…");
  try {
    const quote = await request("/v1/operator/world-quote", {
      method: "POST",
      body: JSON.stringify({ brief }),
    });
    if (requestId !== quoteRequestId) return;
    currentQuote = { brief, ...quote };
    setNotice(
      quoteResult,
      `First generation call maximum: USD ${quote.first_call_max_usd} · ${quote.provider}/${quote.model}. Session limit: USD ${quote.session_limit_usd}; remaining before generation: USD ${quote.session_remaining_usd}. Retries receive their own quote and must also fit the session limit.`,
      "success",
    );
  } catch (error) {
    if (requestId === quoteRequestId) setNotice(quoteResult, error.message, "error");
  } finally {
    if (requestId === quoteRequestId) {
      quotePending = false;
      quoteButton.textContent = "Estimate recipe cost";
    }
    setConnected(connectionState.textContent === "Connected");
  }
});

studioQuoteButton.addEventListener("click", async () => {
  const brief = worldBrief.value.trim();
  if (!studioActionQuoteEnabled || !brief) return;
  const requestId = ++studioQuoteRequestId;
  studioQuotePending = true;
  studioQuoteButton.disabled = true;
  studioQuoteButton.textContent = "Estimating…";
  currentStudioQuote = null;
  studioSpendConfirmed.checked = false;
  setConnected(connectionState.textContent === "Connected");
  setNotice(studioQuoteResult, "Requesting the provider’s maximum cost for the first Studio blockout call…");
  try {
    const quote = await request("/v1/operator/studio-quote", {
      method: "POST",
      body: JSON.stringify({ brief }),
    });
    if (requestId !== studioQuoteRequestId) return;
    currentStudioQuote = { brief, ...quote };
    setNotice(
      studioQuoteResult,
      `First Studio blockout call maximum: USD ${quote.first_call_max_usd} · ${quote.provider}/${quote.model}. Session limit: USD ${quote.session_limit_usd}; remaining before generation: USD ${quote.session_remaining_usd}. Retries receive their own quote and must also fit the session limit.`,
      "success",
    );
  } catch (error) {
    if (requestId === studioQuoteRequestId) setNotice(studioQuoteResult, error.message, "error");
  } finally {
    if (requestId === studioQuoteRequestId) {
      studioQuotePending = false;
      studioQuoteButton.textContent = "Estimate Studio blockout cost";
    }
    setConnected(connectionState.textContent === "Connected");
  }
});

generateButton.addEventListener("click", async () => {
  if (!worldGenerationEnabled || !spendConfirmed.checked || currentQuote?.brief !== worldBrief.value.trim()) return;
  generateButton.disabled = true;
  generationPending = true;
  setConnected(connectionState.textContent === "Connected");
  generateButton.textContent = "Generating…";
  setNotice(worldResult, "The request is running under the configured session budget.");
  try {
    const response = await fetch("/v1/operator/world-recipe", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${operatorToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ brief: worldBrief.value.trim() }),
      cache: "no-store",
    });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body || body.status === "error") {
      throw new Error(body?.error?.message || `World generation failed (${response.status})`);
    }
    const runId = response.headers.get("X-RGA-Run-ID");
    const recipe = JSON.stringify(body, null, 2);
    currentRecipe = body;
    currentArtifactId = null;
    currentAssetUploadRequestId = null;
    currentAssetUploadApprovalId = null;
    currentRobloxModelAssetId = null;
    currentRobloxBuild = null;
    remoteRobloxPublishReview.checked = false;
    // Correlate each downstream service result with the scene generation run.
    const workflowId = runId || crypto.randomUUID();
    currentBlenderRequestId = workflowId;
    currentRobloxRequestId = workflowId;
    currentStudioRecipeRequestId = workflowId;
    remoteBlenderDownload.hidden = true;
    remoteRobloxAssetReview.checked = false;
    remoteRobloxImportReview.checked = false;
    remoteRobloxAssetUpload.hidden = true;
    document.querySelector("#recipe-json").textContent = recipe;
    document.querySelector("#recipe-output").hidden = false;
    document.querySelector("#remote-blender-controls").hidden = !blenderMcpEnabled;
    document.querySelector("#remote-roblox-controls").hidden = !robloxMcpEnabled;
    remoteBlenderReview.checked = false;
    remoteRobloxReview.checked = false;
    recipeStudioReview.checked = false;
    setNotice(
      recipeStudioResult,
      "Review the recipe, then create a bounded Studio proxy blockout that preserves object rotation. It will queue unapproved and does not use another model call.",
    );
    setNotice(
      remoteBlenderResult,
      blenderMcpEnabled
        ? "Review the complete recipe above before building its GLB on the remote Blender service."
        : "Remote Blender MCP is not configured; download this recipe to import it locally.",
    );
    setNotice(
      remoteRobloxResult,
      robloxMcpEnabled
        ? "This fixed harness checks the recipe in a pinned disposable Roblox place; it does not run generated game scripts."
        : "Remote Roblox validation MCP is not configured.",
    );
    if (recipeDownloadUrl) URL.revokeObjectURL(recipeDownloadUrl);
    recipeDownloadUrl = URL.createObjectURL(new Blob([`${recipe}\n`], { type: "application/json" }));
    setNotice(worldResult, `Run ${runId || "recorded"} completed. Review the validated recipe before building through remote Blender MCP, or download it for optional local authoring.`, "success");
  } catch (error) {
    setNotice(worldResult, error.message, "error");
  } finally {
    quoteRequestId += 1;
    studioQuoteRequestId += 1;
    quotePending = false;
    studioQuotePending = false;
    generationPending = false;
    currentQuote = null;
    currentStudioQuote = null;
    spendConfirmed.checked = false;
    studioSpendConfirmed.checked = false;
    setNotice(quoteResult, "Quote cleared after the generation attempt. Request an updated quote before another call.");
    setNotice(studioQuoteResult, "The session budget may have changed. Request a fresh Studio blockout quote before generation.");
    generateButton.textContent = "Generate scene recipe";
    setConnected(connectionState.textContent === "Connected");
    await refreshStatus();
  }
});

generateStudioButton.addEventListener("click", async () => {
  if (
    !studioActionGenerationEnabled ||
    !studioSpendConfirmed.checked ||
    currentStudioQuote?.brief !== worldBrief.value.trim()
  ) return;
  generateStudioButton.disabled = true;
  generationPending = true;
  setConnected(connectionState.textContent === "Connected");
  generateStudioButton.textContent = "Generating…";
  setNotice(queueResult, "Generating and validating a script-free blockout…");
  try {
    const result = await request("/v1/operator/studio-action", {
      method: "POST",
      body: JSON.stringify({ brief: worldBrief.value.trim() }),
    });
    actionField.value = JSON.stringify(result.item, null, 2);
    workIdField.value = result.work_id;
    selectedWork = { work_id: result.work_id, item: result.item };
    reviewConfirmed.checked = false;
    updateApprovalGate();
    setNotice(queueResult, `Run ${result.run_id} generated and queued as ${result.work_id}. Review the action before the separate approval step.`, "success");
    setNotice(approveResult, "Review the exact generated blockout and ID above before approval.");
    document.querySelector("#proposal-title").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    setNotice(queueResult, error.message, "error");
  } finally {
    quoteRequestId += 1;
    studioQuoteRequestId += 1;
    quotePending = false;
    studioQuotePending = false;
    generationPending = false;
    currentQuote = null;
    currentStudioQuote = null;
    spendConfirmed.checked = false;
    studioSpendConfirmed.checked = false;
    setNotice(quoteResult, "The session budget may have changed. Request a fresh recipe quote before generation.");
    setNotice(studioQuoteResult, "Quote cleared after the generation attempt. Request an updated quote before another call.");
    generateStudioButton.textContent = "Generate Studio blockout";
    setConnected(connectionState.textContent === "Connected");
    await refreshStatus();
  }
});

document.querySelector("#download-recipe").addEventListener("click", () => {
  if (!recipeDownloadUrl) return;
  const link = document.createElement("a");
  link.href = recipeDownloadUrl;
  link.download = "roblox-world-scene-recipe.json";
  document.body.append(link);
  link.click();
  link.remove();
});

recipeStudioReview.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

queueRecipeStudioButton.addEventListener("click", async () => {
  if (
    !operatorToken || !currentRecipe || !currentStudioRecipeRequestId ||
    !recipeStudioReview.checked || recipeStudioQueuePending
  ) return;
  if (!window.confirm("Queue an unapproved, script-free Studio proxy blockout from this reviewed recipe?")) return;
  recipeStudioQueuePending = true;
  setConnected(connectionState.textContent === "Connected");
  setNotice(recipeStudioResult, "Converting the reviewed recipe into bounded Studio proxy parts…");
  try {
    const result = await request("/v1/operator/studio-recipe-action", {
      method: "POST",
      body: JSON.stringify({ recipe: currentRecipe, request_id: currentStudioRecipeRequestId }),
    });
    actionField.value = JSON.stringify(result.item, null, 2);
    workIdField.value = result.work_id;
    selectedWork = result.work_state === "queued"
      ? { work_id: result.work_id, item: result.item }
      : null;
    reviewConfirmed.checked = false;
    updateApprovalGate();
    recipeStudioReview.checked = false;
    setNotice(
      recipeStudioResult,
      `${result.replayed ? `Recovered the existing ${result.work_state} action` : "Queued a new unapproved action"} with ${result.proxy_part_count} proxy parts as ${result.work_id}. ${result.omitted_object_count} of ${result.source_object_count} recipe objects were skipped by proxy bounds or the 14-part cap; paths, entries, landmarks, and building forms are prioritized when the cap applies. ${result.omitted_light_count} lights and ${result.omitted_character_count} characters are not included. Inspect the complete JSON${result.work_state === "queued" ? " before approval" : ""}.`,
      "success",
    );
    setNotice(queueResult, "Recipe-derived Studio action is ready for review.", "success");
    document.querySelector("#proposal-title").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    setNotice(recipeStudioResult, error.message, "error");
  } finally {
    recipeStudioQueuePending = false;
    setConnected(connectionState.textContent === "Connected");
    await refreshStatus();
  }
});

remoteBlenderReview.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

remoteRobloxReview.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

remoteRobloxGameMode.addEventListener("change", () => {
  remoteRobloxReview.checked = false;
  remoteRobloxImportReview.checked = false;
  setConnected(connectionState.textContent === "Connected");
});

remoteRobloxImportReview.addEventListener("change", () => {
  remoteRobloxReview.checked = false;
  setConnected(connectionState.textContent === "Connected");
});

remoteRobloxValidate.addEventListener("click", async () => {
  if (!robloxMcpEnabled || !currentRecipe || !currentRobloxRequestId || !remoteRobloxReview.checked) return;
  if (!window.confirm("Validate this reviewed recipe in the configured disposable Roblox test place?")) return;
  remoteRobloxValidate.disabled = true;
  setNotice(remoteRobloxResult, "Submitting the fixed map harness to the pinned Roblox test place…");
  try {
    const result = await request("/v1/operator/roblox-validate", {
      method: "POST",
      body: JSON.stringify({ recipe: currentRecipe, request_id: currentRobloxRequestId }),
    });
    const receipt = result.validation;
    setNotice(
      remoteRobloxResult,
      `Validation ${receipt.validation_status} · ${receipt.object_count} objects · ${receipt.path_feature_count} path features · ${receipt.navigation_waypoint_count} waypoints · place version ${receipt.place_version} · task ${receipt.task_id}.`,
      receipt.validation_status === "navigation_failed" ? "error" : "success",
    );
    remoteRobloxReview.checked = false;
  } catch (error) {
    setNotice(remoteRobloxResult, `${error.message} Retry with this recipe to recover the same task result.`, "error");
  } finally {
    setConnected(connectionState.textContent === "Connected");
  }
});

remoteRobloxBuild.addEventListener("click", async () => {
  if (!robloxMcpEnabled || !currentRecipe || !currentRobloxRequestId || !remoteRobloxReview.checked) return;
  const gameplayMode = remoteRobloxGameMode.value;
  const derivedGameplayRules = gameplayMode === "rule_game"
    ? [
        ...(currentRecipe.objects.some((item) => item.role === "collectible")
          ? [{ trigger_role: "collectible", action: "award_points", amount: 1 }]
          : []),
        ...(currentRecipe.objects.some((item) => item.role === "hazard")
          ? [{ trigger_role: "hazard", action: "eliminate" }]
          : []),
        ...(currentRecipe.objects.some((item) => item.role === "collectible")
          && currentRecipe.objects.some((item) => item.role === "landmark")
          ? [{
              trigger_role: "landmark",
              action: "award_win",
              minimum_points: Math.min(1000, currentRecipe.objects.filter((item) => item.role === "collectible").length),
            }]
          : []),
      ]
    : undefined;
  const gameplayRules = gameplayMode === "rule_game"
    ? (currentPlannedGameplayRules?.length ? currentPlannedGameplayRules : derivedGameplayRules)
    : undefined;
  if (gameplayMode === "rule_game" && gameplayRules.length === 0) {
    setNotice(remoteRobloxResult, "Data-driven mode needs at least one gameplay rule whose trigger role exists in the reviewed recipe.", "error");
    return;
  }
  const modeLabel = gameplayMode === "treasure_hunt"
    ? "the fixed Treasure Hunt gameplay template"
    : gameplayMode === "obby"
      ? "the fixed Obby checkpoint course template"
      : gameplayMode === "rule_game"
        ? "the fixed server interpreter with data-driven role rules"
        : "a script-free map blockout";
  const includeModel = remoteRobloxImportReview.checked && currentRobloxModelAssetId;
  if (remoteRobloxImportReview.checked && !includeModel) {
    setNotice(remoteRobloxResult, "The reviewed Roblox Model asset is unavailable.", "error");
    return;
  }
  const modelLabel = includeModel ? " and include the approved Blender Model geometry" : "";
  if (!window.confirm(`Build a Roblox place artifact with ${modeLabel}${modelLabel} on the remote service? It will not be published.`)) return;
  remoteRobloxBuild.disabled = true;
  setNotice(remoteRobloxResult, "Building a downloadable .rbxlx place on the remote Rojo service…");
  try {
    const result = await request("/v1/operator/roblox-build", {
      method: "POST",
      body: JSON.stringify({
        recipe: currentRecipe,
        request_id: currentRobloxRequestId,
        gameplay_mode: gameplayMode,
        ...(gameplayRules ? { gameplay_rules: gameplayRules } : {}),
        ...(includeModel ? { model_asset_id: currentRobloxModelAssetId } : {}),
      }),
    });
    const raw = atob(result.place_file_base64);
    const bytes = Uint8Array.from(raw, (character) => character.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/xml" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = result.filename || "rga-place.rbxlx";
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    currentRobloxBuild = {
      request_id: currentRobloxRequestId,
      approval_id: crypto.randomUUID(),
      sha256: result.sha256,
    };
    remoteRobloxPublishReview.checked = false;
    const modeDescription = result.gameplay_mode === "treasure_hunt"
      ? "with the fixed Treasure Hunt server script"
      : result.gameplay_mode === "obby"
        ? "with the fixed Obby checkpoint server script"
        : result.gameplay_mode === "rule_game"
          ? "with the fixed data-driven gameplay rule server script"
        : "with no scripts";
    const importedDescription = result.imported_meshpart_count
      ? ` Included ${result.imported_meshpart_count} validated MeshParts from the approved Roblox Model.`
      : ` ${result.approximated_object_count} custom shapes use bounds approximations.`;
    setNotice(remoteRobloxResult, `Built and downloaded the place ${modeDescription} (${result.sha256.slice(0, 16)}…).${importedDescription} The file was not published.`, "success");
    remoteRobloxReview.checked = false;
  } catch (error) {
    setNotice(remoteRobloxResult, `${error.message} Retry with this recipe to recover the same deterministic build.`, "error");
  } finally {
    setConnected(connectionState.textContent === "Connected");
  }
});

remoteRobloxPublishReview.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

remoteRobloxPublish.addEventListener("click", async () => {
  if (
    !currentRobloxBuild ||
    robloxPlacePublishHealth?.state !== "available" ||
    !remoteRobloxPublishReview.checked
  ) return;
  const confirmed = window.confirm(
    `Publish the reviewed artifact ${currentRobloxBuild.sha256.slice(0, 16)}… to the pinned disposable Roblox test place? This replaces its published version.`,
  );
  if (!confirmed) return;
  remoteRobloxPublish.disabled = true;
  setNotice(remoteRobloxResult, "Publishing the exact reviewed place to the pinned test experience…");
  try {
    const result = await request("/v1/operator/roblox-publish", {
      method: "POST",
      body: JSON.stringify({
        request_id: currentRobloxBuild.request_id,
        approval_id: currentRobloxBuild.approval_id,
        sha256: currentRobloxBuild.sha256,
        reviewed_in_studio: true,
      }),
    });
    const receipt = result.publication;
    setNotice(
      remoteRobloxResult,
      `Published reviewed artifact ${receipt.artifact_sha256.slice(0, 16)}… as test place version ${receipt.version_number}.`,
      "success",
    );
    remoteRobloxPublishReview.checked = false;
  } catch (error) {
    setNotice(
      remoteRobloxResult,
      `${error.message} Retrying the same IDs can recover a confirmed receipt; uncertain writes are never resubmitted. Check the test place's version history before manual recovery.`,
      "error",
    );
  } finally {
    setConnected(connectionState.textContent === "Connected");
  }
});

remoteBlenderApply.addEventListener("click", async () => {
  if (!blenderMcpEnabled || !currentRecipe || !remoteBlenderReview.checked) return;
  if (!window.confirm("Build this reviewed scene as a GLB on the configured remote Blender service?")) return;
  remoteBlenderApply.disabled = true;
  currentArtifactId = null;
  currentAssetUploadRequestId = null;
  currentAssetUploadApprovalId = null;
  currentRobloxModelAssetId = null;
  currentRobloxBuild = null;
  remoteRobloxPublishReview.checked = false;
  remoteBlenderDownload.hidden = true;
  remoteRobloxAssetReview.checked = false;
  remoteRobloxImportReview.checked = false;
  remoteRobloxAssetUpload.hidden = true;
  setNotice(remoteBlenderResult, "Building the reviewed scene with the remote Blender service…");
  try {
    const result = await request("/v1/operator/blender-apply", {
      method: "POST",
      body: JSON.stringify({ recipe: currentRecipe, request_id: currentBlenderRequestId }),
    });
    setNotice(
      remoteBlenderResult,
      `Built a GLB with ${result.object_count} scene objects for “${result.recipe_name}”. The approved Roblox Model can be added directly to a remote place build.`,
      "success",
    );
    currentArtifactId = result.artifact_id;
    // The artifact UUID is the durable upload request ID: a retry or page
    // recovery cannot accidentally create a second Roblox asset for this GLB.
    currentAssetUploadRequestId = result.artifact_id;
    currentAssetUploadApprovalId = result.artifact_id;
    remoteBlenderDownload.hidden = false;
    remoteRobloxAssetUpload.hidden = !robloxAssetUploadEnabled;
    remoteBlenderReview.checked = false;
    remoteRobloxAssetReview.checked = false;
    setConnected(connectionState.textContent === "Connected");
  } catch (error) {
    setNotice(
      remoteBlenderResult,
      `${error.message} Retry this recipe in this tab to recover the same remote build.`,
      "error",
    );
  } finally {
    setConnected(connectionState.textContent === "Connected");
  }
});

remoteBlenderDownload.addEventListener("click", async () => {
  if (!currentArtifactId || !operatorToken) return;
  remoteBlenderDownload.disabled = true;
  setNotice(remoteBlenderResult, "Downloading the Blender GLB artifact…");
  try {
    const response = await fetch(`/v1/operator/blender-artifact/${encodeURIComponent(currentArtifactId)}`, {
      headers: { Authorization: `Bearer ${operatorToken}` },
      cache: "no-store",
    });
    if (!response.ok || response.headers.get("Content-Type")?.split(";", 1)[0] !== "model/gltf-binary") {
      throw new Error(`Artifact download failed (${response.status}).`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rga-${currentArtifactId}.glb`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(remoteBlenderResult, "GLB downloaded. Remote Roblox Model upload is available above when configured.", "success");
  } catch (error) {
    setNotice(remoteBlenderResult, error.message, "error");
  } finally {
    setConnected(connectionState.textContent === "Connected");
  }
});

remoteRobloxAssetReview.addEventListener("change", () => {
  setConnected(connectionState.textContent === "Connected");
});

remoteRobloxAssetStatus.addEventListener("click", async () => {
  const requestId = currentAssetUploadRequestId;
  if (!requestId || !operatorToken) return;
  remoteRobloxAssetStatus.disabled = true;
  setNotice(remoteBlenderResult, "Checking Roblox model moderation…");
  try {
    const result = await request("/v1/operator/roblox-model-status", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId }),
    });
    if (currentAssetUploadRequestId !== requestId) return;
    const asset = result.asset;
    currentRobloxModelAssetId = asset.status === "approved" ? asset.asset_id : null;
    remoteRobloxImportReview.checked = false;
    setNotice(remoteBlenderResult,
      `Roblox Model asset ${asset.asset_id}: ${asset.status} (${asset.moderation_state}).`,
      asset.status === "rejected" ? "error" : "success");
  } catch (error) {
    if (currentAssetUploadRequestId === requestId) {
      setNotice(remoteBlenderResult, error.message, "error");
    }
  } finally {
    setConnected(connectionState.textContent === "Connected");
  }
});

remoteRobloxAssetUpload.addEventListener("click", async () => {
  if (
    !currentArtifactId || !currentAssetUploadRequestId || !currentAssetUploadApprovalId ||
    !robloxAssetUploadEnabled || !remoteRobloxAssetReview.checked
  ) return;
  const confirmed = window.confirm(
    "Upload this exact Blender GLB as a new persistent Roblox Model asset? Roblox moderation applies. This does not publish or modify a place.",
  );
  if (!confirmed) return;
  remoteRobloxAssetUpload.disabled = true;
  setNotice(remoteBlenderResult, "Sending the reviewed GLB directly from the Blender server to Roblox Open Cloud…");
  try {
    const result = await request("/v1/operator/roblox-model-upload", {
      method: "POST",
      body: JSON.stringify({
        artifact_id: currentArtifactId,
        request_id: currentAssetUploadRequestId,
        approval_id: currentAssetUploadApprovalId,
        display_name: `RGA ${currentRecipe?.name || "Generated Model"}`.slice(0, 80),
        description: "Reviewed Roblox Game Architect model generated from a validated scene recipe.",
      }),
    });
    const asset = result.asset;
    currentRobloxModelAssetId = asset.status === "approved" ? asset.asset_id : null;
    setNotice(
      remoteBlenderResult,
      `Roblox Model asset ${asset.asset_id}: ${asset.status} (${asset.moderation_state}). Request ${asset.request_id}.${currentRobloxModelAssetId ? " You can now include this static model geometry in a remote place build." : " Model import becomes available after Roblox approves the asset."}`,
      asset.status === "rejected" ? "error" : "success",
    );
    remoteRobloxAssetReview.checked = false;
    remoteRobloxImportReview.checked = false;
  } catch (error) {
    setNotice(remoteBlenderResult, `${error.message} Retry only with the same request ID.`, "error");
  } finally {
    setConnected(connectionState.textContent === "Connected");
  }
});

actionField.addEventListener("input", () => {
  updateApprovalGate();
});

workIdField.addEventListener("input", () => {
  updateApprovalGate();
});

queueButton.addEventListener("click", async () => {
  setNotice(queueResult, "Validating and queueing…");
  try {
    const item = JSON.parse(actionField.value);
    if (!item || Array.isArray(item) || typeof item !== "object") throw new Error("Proposal must be a JSON object.");
    const result = await request("/v1/operator/work", {
      method: "POST",
      body: JSON.stringify({ item }),
    });
    workIdField.value = result.work_id;
    selectedWork = { work_id: result.work_id, item };
    reviewConfirmed.checked = false;
    updateApprovalGate();
    setNotice(queueResult, `Queued as ${result.work_id}. It is not approved and will not be delivered yet.`, "success");
    setNotice(approveResult, "Review the exact action and ID above, then approve only if they match.");
    await refreshStatus();
  } catch (error) {
    setNotice(queueResult, error.message, "error");
  }
});

approveButton.addEventListener("click", async () => {
  const workId = workIdField.value.trim();
  if (!workId) {
    setNotice(approveResult, "Enter the queued action ID first.", "error");
    return;
  }
  if (!window.confirm(`Approve ${workId} for delivery to the Studio plugin? Studio will still ask for a local Apply click.`)) return;
  setNotice(approveResult, "Approving…");
  try {
    const result = await request("/v1/operator/approve", {
      method: "POST",
      body: JSON.stringify({ work_id: workId }),
    });
    setNotice(approveResult, `${result.work_id} approved for delivery.`, "success");
    selectedWork = null;
    reviewConfirmed.checked = false;
    updateApprovalGate();
    await refreshStatus();
  } catch (error) {
    setNotice(approveResult, error.message, "error");
  }
});

window.addEventListener("pagehide", () => {
  operatorToken = "";
  tokenField.value = "";
  selectedWork = null;
  worldGenerationEnabled = false;
  worldQuoteEnabled = false;
  gamePlanEnabled = false;
  gamePlanQuoteEnabled = false;
  studioActionGenerationEnabled = false;
  blenderMcpEnabled = false;
  currentRecipe = null;
  currentArtifactId = null;
  currentBlenderRequestId = null;
  currentStudioRecipeRequestId = null;
  currentQuote = null;
  currentStudioQuote = null;
  currentGamePlanQuote = null;
  currentGamePlan = null;
  studioActionQuoteEnabled = false;
  gamePlanQuotePending = false;
  gamePlanPending = false;
  gamePlanSpendConfirmed.checked = false;
  remoteBlenderDownload.hidden = true;
  reviewConfirmed.checked = false;
  spendConfirmed.checked = false;
  studioSpendConfirmed.checked = false;
  if (recipeDownloadUrl) URL.revokeObjectURL(recipeDownloadUrl);
});
