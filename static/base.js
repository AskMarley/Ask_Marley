function setupMobileNav() {
  const nav = document.getElementById("portalNav");
  const toggle = document.querySelector(".mobile-nav-toggle");

  if (!nav || !toggle) {
    return;
  }

  toggle.addEventListener("click", () => {
    const isOpen = nav.classList.toggle("open");
    toggle.classList.toggle("active", isOpen);
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });

  const closeNav = () => {
    nav.classList.remove("open");
    toggle.classList.remove("active");
    toggle.setAttribute("aria-expanded", "false");
  };

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeNav);
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) {
      closeNav();
    }
  });
}

function setupFlashDismiss() {
  const flashes = document.querySelectorAll(".flash");

  flashes.forEach((flash) => {
    const closeBtn = flash.querySelector(".flash-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        flash.remove();
      });
    }

    setTimeout(() => {
      flash.style.opacity = "0";
      flash.style.transform = "translateY(-10px)";
      setTimeout(() => flash.remove(), 400);
    }, 6000);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupMobileNav();
  setupFlashDismiss();
});
