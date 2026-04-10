(function () {
  const loginShell = document.querySelector(".auth-shell--login");
  if (!loginShell) {
    return;
  }

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const cursorGlow = document.getElementById("cursorGlow");
  const featureCards = loginShell.querySelectorAll(".feature-grid article, .auth-trust-card");
  const inputs = loginShell.querySelectorAll("input");

  if (!reduceMotion && cursorGlow) {
    window.addEventListener("pointermove", (event) => {
      cursorGlow.style.left = `${event.clientX}px`;
      cursorGlow.style.top = `${event.clientY}px`;
      cursorGlow.style.opacity = "1";
    });

    window.addEventListener("pointerleave", () => {
      cursorGlow.style.opacity = "0";
    });
  }

  if (!reduceMotion) {
    featureCards.forEach((card, index) => {
      card.style.opacity = "0";
      card.style.transform = "translateY(18px)";
      card.style.transition = `opacity 500ms ease ${index * 70}ms, transform 500ms ease ${index * 70}ms`;

      window.requestAnimationFrame(() => {
        card.style.opacity = "1";
        card.style.transform = "translateY(0)";
      });
    });
  }

  inputs.forEach((input) => {
    input.addEventListener("focus", () => {
      input.closest(".field-group")?.classList.add("is-active");
    });

    input.addEventListener("blur", () => {
      input.closest(".field-group")?.classList.remove("is-active");
    });
  });
})();
