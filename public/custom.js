(function () {
  const LABEL_TEXT = "Mungkin anda ingin bertanya tentang:";
  const LABEL_CLASS = "suggestion-label";

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
    const containers = document.querySelectorAll(
      "div.-ml-1\\.5.flex.items-center.flex-wrap"
    );

    containers.forEach(function (container) {
      if (container.getAttribute("data-label-injected")) return;

      var buttons = container.querySelectorAll("button");
      var firstSuggestion = null;

      for (var i = 0; i < buttons.length; i++) {
        if (isSuggestionButton(buttons[i])) {
          firstSuggestion = buttons[i];
          break;
        }
      }

      if (!firstSuggestion) return;

      container.setAttribute("data-label-injected", "true");

      var label = document.createElement("div");
      label.className = LABEL_CLASS;
      label.textContent = LABEL_TEXT;

      container.insertBefore(label, firstSuggestion);
    });
  }

  injectLabels();

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

  if (sessionStorage.getItem("readme-popup-shown")) {
    console.log("[Readme Popup] Already shown this session, skipping");
    return;
  }

  function showReadmePopup() {
    console.log("[Readme Popup] Showing popup...");

    if (document.getElementById("readme-popup-overlay")) return;

    var overlay = document.createElement("div");
    overlay.id = "readme-popup-overlay";
    overlay.className = "readme-popup-overlay";

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closePopup();
    });

    var modal = document.createElement("div");
    modal.className = "readme-popup-modal";

    var icon = document.createElement("div");
    icon.className = "readme-popup-icon";
    icon.innerHTML = "📖";

    var title = document.createElement("h2");
    title.className = "readme-popup-title";
    title.textContent = "Selamat Datang!";

    var message = document.createElement("p");
    message.className = "readme-popup-message";
    message.textContent =
      "Sebelum mulai menggunakan chatbot, kami sarankan untuk membaca Panduan Penggunaan terlebih dahulu agar dapat menggunakan chatbot dengan lebih efektif.";

    var btnContainer = document.createElement("div");
    btnContainer.className = "readme-popup-buttons";

    var readBtn = document.createElement("button");
    readBtn.className = "readme-popup-btn readme-popup-btn-primary";
    readBtn.textContent = "Baca Panduan";
    readBtn.addEventListener("click", function () {
      closePopup();
      setTimeout(openReadmePage, 350);
    });

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

    setTimeout(function () {
      overlay.classList.add("readme-popup-visible");
    }, 50);

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

    var readmeBtn = document.getElementById("readme-button");
    if (readmeBtn) {
      console.log("[Readme Popup] Found readme button by ID, clicking");
      readmeBtn.click();
      return;
    }

    var readmeLink = document.querySelector('a[href*="readme"]');
    if (readmeLink) {
      console.log("[Readme Popup] Found readme link, clicking");
      readmeLink.click();
      return;
    }

    var allClickables = document.querySelectorAll("a, button");
    for (var i = 0; i < allClickables.length; i++) {
      var el = allClickables[i];
      var text = (el.textContent || "").toLowerCase().trim();
      var ariaLabel = (el.getAttribute("aria-label") || "").toLowerCase();
      var href = (el.getAttribute("href") || "").toLowerCase();
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

    console.log("[Readme Popup] Fallback: navigating to /readme");
    window.location.href = "/readme";
  }

  console.log("[Readme Popup] Waiting for page to be ready...");
  setTimeout(showReadmePopup, 1500);
})();

(function () {
  document.addEventListener('click', function (e) {
    if (!e.target) return;

    var textPContent = e.target.textContent || e.target.innerText || "";
    var isBackButtonText = textPContent.includes('Kembali ke Halaman Utama');
    var isBackButtonId = (e.target.id === 'btn-close-readme');

    var closestInteractive = e.target.closest('a') || e.target.closest('button');
    var interactiveHasText = closestInteractive && (closestInteractive.textContent || "").includes('Kembali ke Halaman Utama');
    var interactiveHasId = closestInteractive && (closestInteractive.id === 'btn-close-readme');

    if (isBackButtonText || isBackButtonId || interactiveHasText || interactiveHasId) {
      e.preventDefault(); 

      var closeBtn = document.querySelector('[role="dialog"] button.absolute, button.absolute.right-4.top-4');

      if (closeBtn) {
        closeBtn.click();
      } else {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true }));
      }
    }
  });
})();

(function () {
  function updateReadmeLabel() {
    var readmeBtn = document.getElementById('readme-button');
    if (readmeBtn) {
      var btnSpan = readmeBtn.querySelector('span');
      if (btnSpan && btnSpan.textContent === 'Readme') {
        btnSpan.textContent = 'Panduan';
      }
    }

    var dialogTitles = document.querySelectorAll('[role="dialog"] h2[id^="radix-"] span, [role="dialog"] h2[id^="radix-"]');
    for (var i = 0; i < dialogTitles.length; i++) {
      var el = dialogTitles[i];
      if (el.textContent === 'Readme') {
        el.textContent = 'Panduan';
      }
    }
  }

  updateReadmeLabel();

  var observer = new MutationObserver(function () {
    updateReadmeLabel();
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
  });
})();


// ============================================================
// Voice Transcript
// ============================================================
(function () {
  function getComposerInput() {
    return (
      document.querySelector("textarea#chat-input") ||
      document.querySelector("textarea[data-testid='chat-input']") ||
      document.querySelector("[data-testid='composer'] textarea") ||
      document.querySelector("textarea")
    );
  }

  function setReactInputValue(el, value) {
    if (!el) return;
    var nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value"
    );
    if (nativeSetter && nativeSetter.set) {
      nativeSetter.set.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function syncBridgeToTextarea() {
    var bridge = document.getElementById("voice-interim-bridge");

    if (bridge && bridge.getAttribute("data-recording") === "true") {
      var text = bridge.getAttribute("data-text") || "";
      var el = getComposerInput();
      if (el && el.value !== text) {
        setReactInputValue(el, text);
      }
    }
  }

  function handleBridgeRemoved() {
    var el = getComposerInput();
    if (el && el.value) {
      setReactInputValue(el, "");
    }
  }

  var prevBridgePresent = false;

  var bridgeObserver = new MutationObserver(function () {
    var bridge = document.getElementById("voice-interim-bridge");
    var nowPresent = !!bridge;

    if (nowPresent) {
      syncBridgeToTextarea();
    } else if (prevBridgePresent && !nowPresent) {
      handleBridgeRemoved();
    }

    prevBridgePresent = nowPresent;
  });

  bridgeObserver.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["data-text", "data-recording"],
  });
})();
