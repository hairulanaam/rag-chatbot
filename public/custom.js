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
