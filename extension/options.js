const computerContainer = document.getElementById("computers");
const status = document.getElementById("status");
let loaded = false;
let busy = false;

function updateControls() {
  for (const id of ["add", "save", "test", "userdata"]) document.getElementById(id).disabled = !loaded || busy;
  document.querySelectorAll(".computer input, .computer button").forEach(input => { input.disabled = busy; });
  if (computerContainer.children.length >= 12) document.getElementById("add").disabled = true;
}

function addComputer(remote = {}) {
  if (computerContainer.children.length >= 12) return;
  const row = T3Ui.element(document, "fieldset", "computer");
  row.append(T3Ui.element(document, "legend", "", "Remote computer"));
  for (const [key, label, placeholder, initial] of [
    ["name", "Display name", "Mac Mini", remote.name || ""],
    ["host", "SSH alias or hostname", "mac-mini", remote.host || ""],
    ["userdata", "Remote T3 data directory", "~/.t3/userdata", remote.userdata || "~/.t3/userdata"],
  ]) {
    const input = T3Ui.element(document, "input");
    input.dataset.field = key;
    input.value = initial;
    input.placeholder = placeholder;
    input.maxLength = key === "userdata" ? 4096 : 200;
    input.required = true;
    const wrapper = T3Ui.element(document, "label", "", label);
    wrapper.append(input);
    row.append(wrapper);
  }
  const remove = T3Ui.element(document, "button", "", "Remove computer");
  remove.type = "button";
  remove.addEventListener("click", () => { row.remove(); updateControls(); document.getElementById("add").focus(); });
  row.append(remove);
  computerContainer.append(row);
  updateControls();
  return row;
}

function showConfig(config) {
  document.getElementById("userdata").value = config.userdata;
  computerContainer.replaceChildren();
  for (const remote of config.sshHosts || []) addComputer(remote);
}

async function request(message) {
  const response = await chrome.runtime.sendMessage(message);
  if (!response?.ok) throw new Error(response?.error || "The native helper is unavailable. Run the installer and try again.");
  return response;
}

async function loadConfig() {
  document.getElementById("reload-config").hidden = true;
  try {
    const response = await request({ type: "getConfig" });
    loaded = true;
    showConfig(response.config);
    status.textContent = "Changes take effect after you save.";
  } catch (error) { status.textContent = error.message; document.getElementById("reload-config").hidden = false; }
  updateControls();
}
document.getElementById("reload-config").addEventListener("click", () => void loadConfig());

document.getElementById("add").addEventListener("click", () => addComputer()?.querySelector("input").focus());
document.getElementById("settings-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!loaded || busy) return;
  const config = { userdata: document.getElementById("userdata").value.trim(), sshHosts: Array.from(computerContainer.children, row =>
    Object.fromEntries(Array.from(row.querySelectorAll("input"), input => [input.dataset.field, input.value.trim()]))) };
  busy = true;
  updateControls();
  try {
    const response = await request({ type: "saveConfig", config });
    showConfig(response.config);
    document.getElementById("connections").replaceChildren();
    status.textContent = "Saved. Refresh a GitHub page to check the updated computers.";
  } catch (error) { status.textContent = error.message; }
  finally { busy = false; updateControls(); }
});

document.getElementById("test").addEventListener("click", async () => {
  if (!loaded || busy) return;
  busy = true;
  updateControls();
  status.textContent = "Checking saved computers…";
  const container = document.getElementById("connections");
  container.replaceChildren();
  try {
    const response = await chrome.runtime.sendMessage({ type: "status" });
    status.textContent = response?.ok ? "Connection check finished." : response?.error || "The native helper is unavailable.";
    const list = T3Ui.element(document, "ul");
    for (const environment of response?.environments || [{ name: "This computer", ok: response?.ok, error: response?.error }]) {
      list.append(T3Ui.element(document, "li", "", `${environment.name}: ${environment.ok ? "connected" : environment.error || "unavailable"}`));
    }
    container.append(list);
  } catch { status.textContent = "The helper could not be reached. Run the installer and try again."; }
  finally { busy = false; updateControls(); }
});
void loadConfig();
