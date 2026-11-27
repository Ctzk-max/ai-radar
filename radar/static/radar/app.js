if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {
    // The feed and settings still work when installation is unavailable.
  });
}

const modelPicker = document.querySelector(".model-options");
if (modelPicker) {
  const options = [...modelPicker.querySelectorAll("input")];
  function updateChoices() {
    const count = options.filter(option => option.checked).length;
    options.forEach(option => { option.disabled = !option.checked && count >= 4; });
  }
  modelPicker.addEventListener("change", updateChoices);
  updateChoices();
}
