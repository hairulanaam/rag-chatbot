// Inject suggestion label before action buttons
// Uses MutationObserver to detect when Chainlit renders suggestion buttons
// Label is injected via DOM so it won't be included in the copy button's output
//
// DOM structure (from inspect):
// <div class="-ml-1.5 flex items-center flex-wrap">
//   <button data-state="closed">  <!-- copy button with SVG icon -->
//   <button id="uuid-here">       <!-- suggestion button(s) with text -->
// </div>

(function () {
  const LABEL_TEXT = "Mungkin anda ingin bertanya tentang:";
  const LABEL_CLASS = "suggestion-label";

  // Check if a button is a suggestion button (has UUID-like id and text content, no SVG)
  function isSuggestionButton(btn) {
    return (
      btn.tagName === "BUTTON" &&
      btn.id &&
      btn.id.match(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
      ) &&
      !btn.querySelector("svg")
    );
  }

  function injectLabels() {
    // Find all button containers (the flex-wrap div with action buttons)
    const containers = document.querySelectorAll(
      "div.-ml-1\\.5.flex.items-center.flex-wrap"
    );

    containers.forEach(function (container) {
      // Skip if already processed
      if (container.getAttribute("data-label-injected")) return;

      // Find suggestion buttons in this container
      var buttons = container.querySelectorAll("button");
      var firstSuggestion = null;

      for (var i = 0; i < buttons.length; i++) {
        if (isSuggestionButton(buttons[i])) {
          firstSuggestion = buttons[i];
          break;
        }
      }

      // Only inject if there are suggestion buttons
      if (!firstSuggestion) return;

      // Mark as processed
      container.setAttribute("data-label-injected", "true");

      // Create label element
      var label = document.createElement("div");
      label.className = LABEL_CLASS;
      label.textContent = LABEL_TEXT;

      // Insert label before the first suggestion button
      container.insertBefore(label, firstSuggestion);
    });
  }

  // Run on initial load
  injectLabels();

  // Watch for dynamically added elements
  var observer = new MutationObserver(function () {
    injectLabels();
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
  });
})();

// ============================================================
// Popup Himbauan Readme - muncul sekali setelah halaman diload
// ============================================================
(function () {
  console.log("[Readme Popup] Script loaded");

  // Hanya tampilkan sekali per sesi browser tab
  if (sessionStorage.getItem("readme-popup-shown")) {
    console.log("[Readme Popup] Already shown this session, skipping");
    return;
  }

  function showReadmePopup() {
    console.log("[Readme Popup] Showing popup...");

    // Cek ulang (guard terhadap race condition)
    if (document.getElementById("readme-popup-overlay")) return;

    // Overlay
    var overlay = document.createElement("div");
    overlay.id = "readme-popup-overlay";
    overlay.className = "readme-popup-overlay";

    // Klik di luar modal untuk menutup
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closePopup();
    });

    // Modal box
    var modal = document.createElement("div");
    modal.className = "readme-popup-modal";

    // Icon
    var icon = document.createElement("div");
    icon.className = "readme-popup-icon";
    icon.innerHTML = "📖";

    // Title
    var title = document.createElement("h2");
    title.className = "readme-popup-title";
    title.textContent = "Selamat Datang!";

    // Message
    var message = document.createElement("p");
    message.className = "readme-popup-message";
    message.textContent =
      "Sebelum mulai menggunakan chatbot, kami sarankan untuk membaca Panduan Penggunaan terlebih dahulu agar dapat menggunakan chatbot dengan lebih efektif.";

    // Button container
    var btnContainer = document.createElement("div");
    btnContainer.className = "readme-popup-buttons";

    // "Baca Panduan" button
    var readBtn = document.createElement("button");
    readBtn.className = "readme-popup-btn readme-popup-btn-primary";
    readBtn.textContent = "Baca Panduan";
    readBtn.addEventListener("click", function () {
      closePopup();
      // Klik menu Readme di Chainlit
      setTimeout(openReadmePage, 350);
    });

    // "Nanti Saja" button
    var laterBtn = document.createElement("button");
    laterBtn.className = "readme-popup-btn readme-popup-btn-secondary";
    laterBtn.textContent = "Nanti Saja";
    laterBtn.addEventListener("click", function () {
      closePopup();
    });

    btnContainer.appendChild(readBtn);
    btnContainer.appendChild(laterBtn);

    modal.appendChild(icon);
    modal.appendChild(title);
    modal.appendChild(message);
    modal.appendChild(btnContainer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Animate in (gunakan timeout kecil agar transisi CSS terpicu)
    setTimeout(function () {
      overlay.classList.add("readme-popup-visible");
    }, 50);

    // Tandai sudah ditampilkan
    sessionStorage.setItem("readme-popup-shown", "true");
    console.log("[Readme Popup] Popup injected into DOM");
  }

  function closePopup() {
    var overlay = document.getElementById("readme-popup-overlay");
    if (!overlay) return;
    overlay.classList.remove("readme-popup-visible");
    overlay.classList.add("readme-popup-hiding");
    setTimeout(function () {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }, 300);
  }

  function openReadmePage() {
    console.log("[Readme Popup] Trying to open Readme page...");

    // Strategi 1: Cari link dengan href mengandung "readme"
    var readmeLink = document.querySelector('a[href*="readme"]');
    if (readmeLink) {
      console.log("[Readme Popup] Found readme link, clicking");
      readmeLink.click();
      return;
    }

    // Strategi 2: Cari semua button dan link, cari yang mengandung ikon info / readme
    var allClickables = document.querySelectorAll("a, button");
    for (var i = 0; i < allClickables.length; i++) {
      var el = allClickables[i];
      var text = (el.textContent || "").toLowerCase().trim();
      var ariaLabel = (el.getAttribute("aria-label") || "").toLowerCase();
      var href = (el.getAttribute("href") || "").toLowerCase();
      if (
        text.includes("readme") ||
        ariaLabel.includes("readme") ||
        href.includes("readme")
      ) {
        console.log("[Readme Popup] Found readme element, clicking:", el);
        el.click();
        return;
      }
    }

    // Strategi 3: Navigasi langsung ke /readme
    console.log("[Readme Popup] Fallback: navigating to /readme");
    window.location.href = "/readme";
  }

  // Tampilkan popup segera setelah halaman diload
  console.log("[Readme Popup] Waiting for page to be ready...");
  setTimeout(showReadmePopup, 1000);
})();
