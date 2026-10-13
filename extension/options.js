const computerContainer = document.getElementById("computers");
const status = document.getElementById("status");
let loaded = false;
let busy = false;
let editingId = null;
let saved = [];

function updateControls() {
  for (const id of ["save", "test", "endpoint", "pairing-code", "name", "cancel-edit"]) document.getElementById(id).disabled = !loaded || busy;
  document.querySelectorAll(".computer button").forEach(button => { button.disabled = busy; });
  document.getElementById("test").disabled = !loaded || busy || !saved.length;
  document.getElementById("save").textContent = busy ? "Connecting…" : editingId ? "Save connection" : "Connect";
}
function resetForm() {
  editingId = null;
  document.getElementById("endpoint").value = "http://127.0.0.1:3773";
  document.getElementById("pairing-code").value = "";
  document.getElementById("name").value = "";
  document.getElementById("cancel-edit").hidden = true;
  updateControls();
}
async function request(message) {
  const response = await chrome.runtime.sendMessage(message);
  if (!response?.ok) throw new Error(response?.error || "The connection could not be saved. Please try again.");
  return response;
}
function showConfig(config) {
  saved = config.connections || [];
  computerContainer.replaceChildren();
  if (!saved.length) computerContainer.append(T3Ui.element(document, "p", "hint", "No connections yet. Enter your endpoint URI and pairing code above."));
  for (const connection of saved) {
    const row = T3Ui.element(document, "article", "computer");
    row.append(T3Ui.element(document, "h3", "", connection.name));
    row.append(T3Ui.element(document, "p", "endpoint", connection.endpoint));
    if (connection.expiresAt) row.append(T3Ui.element(document, "p", "hint", `Pairing expires ${new Date(connection.expiresAt).toLocaleDateString()}`));
    const actions = T3Ui.element(document, "div", "actions");
    const edit = T3Ui.element(document, "button", "", "Edit / pair again");
    edit.type = "button";
    edit.addEventListener("click", () => {
      editingId = connection.id;
      document.getElementById("endpoint").value = connection.endpoint;
      document.getElementById("name").value = connection.name;
      document.getElementById("pairing-code").value = "";
      document.getElementById("cancel-edit").hidden = false;
      status.textContent = "Paste a fresh pairing code to renew access, or leave it blank to keep the existing pairing at this endpoint.";
      updateControls();
      document.getElementById("endpoint").focus();
    });
    const remove = T3Ui.element(document, "button", "", "Remove connection");
    remove.type = "button";
    remove.addEventListener("click", async () => {
      busy = true;
      updateControls();
      try {
        await request({ type: "removeConnection", id: connection.id });
        if (editingId === connection.id) resetForm();
        showConfig((await request({ type: "getConfig" })).config);
        status.textContent = "Connection removed from this extension. You can revoke its client in T3’s settings too.";
      } catch (error) { status.textContent = error.message; }
      finally { busy = false; updateControls(); }
    });
    actions.append(edit, remove);
    row.append(actions);
    computerContainer.append(row);
  }
}
async function loadConfig() {
  document.getElementById("reload-config").hidden = true;
  try {
    showConfig((await request({ type: "getConfig" })).config);
    loaded = true;
    status.textContent = saved.length ? "Choose a saved connection to edit, or connect another endpoint." : "Enter your endpoint URI and pairing code to get started.";
  } catch (error) { status.textContent = error.message; document.getElementById("reload-config").hidden = false; }
  updateControls();
}
document.getElementById("reload-config").addEventListener("click", () => void loadConfig());
document.getElementById("cancel-edit").addEventListener("click", resetForm);
document.getElementById("settings-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!loaded || busy) return;
  let endpoint;
  try { endpoint = T3Api.normalizeEndpoint(document.getElementById("endpoint").value); }
  catch (error) { status.textContent = error.message; return; }
  const pairingCode = document.getElementById("pairing-code").value.trim();
  if (!pairingCode && (!editingId || saved.find(connection => connection.id === editingId)?.endpoint !== endpoint)) {
    status.textContent = "Enter a pairing code from T3 Code’s Connections settings.";
    document.getElementById("pairing-code").focus();
    return;
  }
  busy = true;
  updateControls();
  status.textContent = "Connecting to T3 Code…";
  try {
    // Must happen in this user gesture; request only the chosen endpoint's site.
    const allowed = await chrome.permissions.request({ origins: [T3Api.permissionOrigin(endpoint)] });
    if (!allowed) throw new Error("Endpoint access was not granted. Click Connect to try again.");
    const response = await request({ type: "saveConfig", config: { id: editingId, endpoint, pairingCode, name: document.getElementById("name").value.trim() } });
    document.getElementById("pairing-code").value = "";
    showConfig((await request({ type: "getConfig" })).config);
    resetForm();
    document.getElementById("connections").replaceChildren();
    status.textContent = response.warning ? `Pairing saved. ${response.warning}` : "Connected. Refresh your GitHub tabs to find matching T3 threads.";
  } catch (error) { status.textContent = error.message; }
  finally { busy = false; updateControls(); }
});
document.getElementById("test").addEventListener("click", async () => {
  if (!loaded || busy) return;
  busy = true;
  updateControls();
  status.textContent = "Checking saved endpoints…";
  const container = document.getElementById("connections");
  container.replaceChildren();
  try {
    const response = await chrome.runtime.sendMessage({ type: "status" });
    status.textContent = response?.ok ? "Connection check finished." : response?.error || "The T3 endpoints could not be reached.";
    const list = T3Ui.element(document, "ul");
    for (const environment of response?.environments || []) list.append(T3Ui.element(document, "li", "", `${environment.name}: ${environment.ok ? "connected" : environment.error || "unavailable"}`));
    container.append(list);
  } catch { status.textContent = "The T3 endpoints could not be reached. Keep T3 running and check the saved URIs."; }
  finally { busy = false; updateControls(); }
});
void loadConfig();
