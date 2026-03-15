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

    // Coba temukan tombol menggunakan ID resminya
    var readmeBtn = document.getElementById("readme-button");
    if (readmeBtn) {
      console.log("[Readme Popup] Found readme button by ID, clicking");
      readmeBtn.click();
      return;
    }

    // Strategi 1: Cari link dengan href mengandung "readme"
    var readmeLink = document.querySelector('a[href*="readme"]');
    if (readmeLink) {
      console.log("[Readme Popup] Found readme link, clicking");
      readmeLink.click();
      return;
    }

    // Strategi 2: Cari semua button dan link yang atribut aria/teksnya mirip
    var allClickables = document.querySelectorAll("a, button");
    for (var i = 0; i < allClickables.length; i++) {
      var el = allClickables[i];
      var text = (el.textContent || "").toLowerCase().trim();
      var ariaLabel = (el.getAttribute("aria-label") || "").toLowerCase();
      var href = (el.getAttribute("href") || "").toLowerCase();
      // tambahkan pencarian 'panduan' akibat dari modifikasi teks label button
      if (
        text.includes("readme") ||
        text.includes("panduan") ||
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
  setTimeout(showReadmePopup, 1500);
})();

// Menangkap event klik pada tombol Kembali di Readme Modal
(function() {
  document.addEventListener('click', function(e) {
    if (!e.target) return;
    
    // Cek apakah klik berasal dari teks/link/button "Kembali ke Halaman Utama"
    var textPContent = e.target.textContent || e.target.innerText || "";
    var isBackButtonText = textPContent.includes('Kembali ke Halaman Utama');
    var isBackButtonId = (e.target.id === 'btn-close-readme');
    
    // Cek juga parent (misal klik icon / span di dalam button)
    var closestInteractive = e.target.closest('a') || e.target.closest('button');
    var interactiveHasText = closestInteractive && (closestInteractive.textContent || "").includes('Kembali ke Halaman Utama');
    var interactiveHasId = closestInteractive && (closestInteractive.id === 'btn-close-readme');
    
    if (isBackButtonText || isBackButtonId || interactiveHasText || interactiveHasId) {
      e.preventDefault(); // cegah default navigasi form action / a href
      
      // Cari tombol close asli milik radix dialog (tombol ⨉ di pojok kanan atas dialog modal chainlit)
      var closeBtn = document.querySelector('[role="dialog"] button.absolute, button.absolute.right-4.top-4');
      
      if (closeBtn) {
        closeBtn.click();
      } else {
        // Fallback: tutup modal dengan mengirim event Escape ke dokumen radix
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true}));
      }
    }
  });
})();

// Mengubah teks label tombol "Readme" menjadi "Panduan"
(function() {
  function updateReadmeLabel() {
    // 1. Ubah label tombol di header
    var readmeBtn = document.getElementById('readme-button');
    if (readmeBtn) {
      var btnSpan = readmeBtn.querySelector('span');
      if (btnSpan && btnSpan.textContent === 'Readme') {
        btnSpan.textContent = 'Panduan';
      }
    }
    
    // 2. Ubah judul di dalam modal Readme itu sendiri (elemen <h2> dengan id radix-*)
    var dialogTitles = document.querySelectorAll('[role="dialog"] h2[id^="radix-"] span, [role="dialog"] h2[id^="radix-"]');
    for (var i = 0; i < dialogTitles.length; i++) {
        var el = dialogTitles[i];
        if (el.textContent === 'Readme') {
            el.textContent = 'Panduan';
        }
    }
  }

  // Jalankan fungsi awal untuk mengecek jika elemen sudah ada
  updateReadmeLabel();

  // Awasi DOM untuk perubahan (karena elemen di-render asinkron oleh Chainlit UI)
  var observer = new MutationObserver(function() {
    updateReadmeLabel();
  });
  
  observer.observe(document.body, {
    childList: true,
    subtree: true,
  });
})();
