const loginForm = document.getElementById("loginForm");
const loginSubmitButton = document.getElementById("loginSubmitButton");
const recaptchaStatus = document.getElementById("recaptchaStatus");
const recaptchaWidget = document.querySelector(".g-recaptcha");

function setRecaptchaState(verified) {
  if (!loginSubmitButton || !recaptchaWidget) return;

  loginSubmitButton.disabled = !verified;
  loginSubmitButton.setAttribute("aria-disabled", verified ? "false" : "true");

  if (recaptchaStatus) {
    recaptchaStatus.textContent = verified
      ? "Verification complete. You can now sign in."
      : "Complete the reCAPTCHA before signing in.";
  }
}

window.onRecaptchaSuccess = function onRecaptchaSuccess() {
  setRecaptchaState(true);
};

window.onRecaptchaExpired = function onRecaptchaExpired() {
  setRecaptchaState(false);
};

if (loginForm && loginSubmitButton && recaptchaWidget) {
  setRecaptchaState(false);

  loginForm.addEventListener("submit", (event) => {
    if (loginSubmitButton.disabled) {
      event.preventDefault();
      setRecaptchaState(false);
    }
  });
}
