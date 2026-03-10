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
