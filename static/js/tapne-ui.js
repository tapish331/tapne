/* Shared frontend helpers for guest/member interaction behavior. */
(function bootstrapTapneUI() {
    "use strict";

    function normalizeFlag(value) {
        return String(value || "").trim().toLowerCase();
    }

    function isVerboseEnabled() {
        var fromRuntime = normalizeFlag(window.TAPNE_RUNTIME && window.TAPNE_RUNTIME.verbose);
        var fromQuery = normalizeFlag(new URLSearchParams(window.location.search).get("verbose"));
        return ["1", "true", "yes", "on"].indexOf(fromRuntime) >= 0 ||
            ["1", "true", "yes", "on"].indexOf(fromQuery) >= 0;
    }

    var verbose = isVerboseEnabled();

    function vLog(message, payload) {
        if (!verbose) {
            return;
        }

        if (typeof payload === "undefined") {
            console.info("[tapne-ui]", message);
            return;
        }
        console.info("[tapne-ui]", message, payload);
    }

    var html = document.documentElement;
    var runtimeState = normalizeFlag(window.TAPNE_RUNTIME && window.TAPNE_RUNTIME.userState);
    var userState = runtimeState || normalizeFlag(html.getAttribute("data-user-state")) || "guest";
    var modal = document.getElementById("loginPromptModal");

    function openLoginModal(actionLabel) {
        if (!modal) {
            vLog("Login prompt modal is missing; skipping action block.", actionLabel);
            return;
        }

        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
        vLog("Opened login prompt modal for guest action.", actionLabel || "unknown");
    }

    function closeLoginModal() {
        if (!modal) {
            return;
        }

        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
        vLog("Closed login prompt modal.");
    }

    if (modal) {
        modal.addEventListener("click", function onModalClick(event) {
            var closeTarget = event.target;
            if (!(closeTarget instanceof Element)) {
                return;
            }

            if (closeTarget.hasAttribute("data-modal-close")) {
                closeLoginModal();
            }
        });

        document.addEventListener("keydown", function onKeyDown(event) {
            if (event.key === "Escape" && !modal.hidden) {
                closeLoginModal();
            }
        });
    }

    var guestActionButtons = Array.prototype.slice.call(
        document.querySelectorAll(".js-guest-action")
    );

    if (userState === "guest" && guestActionButtons.length > 0) {
        guestActionButtons.forEach(function wireGuestAction(button) {
            button.addEventListener("click", function onGuestActionClick(event) {
                event.preventDefault();
                var actionLabel = button.getAttribute("data-action-label") || "this action";
                vLog("Blocking guest action and opening login prompt.", actionLabel);
                openLoginModal(actionLabel);
            });
        });
        vLog("Guest action handlers attached.", guestActionButtons.length);
    } else {
        vLog("Guest action handlers were not attached.", {
            userState: userState,
            buttonCount: guestActionButtons.length
        });
    }

    var manualOpenButtons = Array.prototype.slice.call(
        document.querySelectorAll("[data-modal-open='login-prompt']")
    );
    manualOpenButtons.forEach(function wireManualOpen(button) {
        button.addEventListener("click", function onManualOpen(event) {
            event.preventDefault();
            openLoginModal("manual trigger");
        });
    });
})();
