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
    var authModal = document.getElementById("authModal");
    var authModalTitle = document.getElementById("authModalTitle");
    var authModalContextNote = document.getElementById("authModalContextNote");
    var authQueryKeys = ["auth", "auth_reason", "auth_error", "auth_next"];

    function normalizePath(pathValue, fallbackPath) {
        try {
            var normalizedUrl = new URL(pathValue || "", window.location.origin);
            if (normalizedUrl.origin !== window.location.origin) {
                return fallbackPath;
            }
            return (normalizedUrl.pathname || "/") + normalizedUrl.search + normalizedUrl.hash;
        } catch (_error) {
            return fallbackPath;
        }
    }

    function cleanOriginPath(pathValue) {
        var currentUrl = new URL(pathValue || window.location.href, window.location.origin);
        authQueryKeys.forEach(function removeAuthKey(key) {
            currentUrl.searchParams.delete(key);
        });

        var query = currentUrl.search ? currentUrl.search : "";
        var hash = currentUrl.hash ? currentUrl.hash : "";
        return (currentUrl.pathname || "/") + query + hash;
    }

    function readAuthStateFromUrl() {
        var params = new URLSearchParams(window.location.search);
        var mode = normalizeFlag(params.get("auth"));
        if (mode !== "login" && mode !== "signup") {
            mode = "";
        }

        var reason = normalizeFlag(params.get("auth_reason"));
        if (reason !== "continue") {
            reason = "";
        }

        var hasError = normalizeFlag(params.get("auth_error")) === "1";
        var nextPath = params.get("auth_next") || "";
        return { mode: mode, reason: reason, hasError: hasError, nextPath: nextPath };
    }

    function syncAuthHiddenInputs(nextPath, originPath, reason) {
        Array.prototype.slice.call(document.querySelectorAll("[data-auth-next-input]"))
            .forEach(function setNext(input) {
                input.value = nextPath;
            });

        Array.prototype.slice.call(document.querySelectorAll("[data-auth-origin-input]"))
            .forEach(function setOrigin(input) {
                input.value = originPath;
            });

        Array.prototype.slice.call(document.querySelectorAll("[data-auth-reason-input]"))
            .forEach(function setReason(input) {
                input.value = reason;
            });
    }

    function setAuthMode(mode) {
        var normalizedMode = mode === "signup" ? "signup" : "login";
        Array.prototype.slice.call(document.querySelectorAll("[data-auth-pane]"))
            .forEach(function togglePane(pane) {
                var paneMode = normalizeFlag(pane.getAttribute("data-auth-pane"));
                pane.hidden = paneMode !== normalizedMode;
            });

        if (authModalTitle) {
            authModalTitle.textContent = normalizedMode === "signup" ? "Create account" : "Log in";
        }

        if (authModal) {
            authModal.setAttribute("data-auth-mode", normalizedMode);
        }
    }

    function openAuthModal(config) {
        if (!authModal) {
            vLog("Auth modal element is missing.");
            return;
        }

        var mode = (config && config.mode) || "login";
        var reason = (config && config.reason) === "continue" ? "continue" : "";
        var originPath = cleanOriginPath((config && config.originPath) || window.location.href);
        var nextPath = normalizePath((config && config.nextPath) || originPath, originPath);
        syncAuthHiddenInputs(nextPath, originPath, reason);
        setAuthMode(mode);

        if (authModalContextNote) {
            if (reason === "continue") {
                authModalContextNote.hidden = false;
                authModalContextNote.textContent = "Please log in to continue.";
            } else {
                authModalContextNote.hidden = true;
                authModalContextNote.textContent = "Please log in to continue.";
            }
        }

        authModal.hidden = false;
        authModal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
        vLog("Opened auth modal.", {
            mode: mode,
            reason: reason,
            nextPath: nextPath,
            originPath: originPath
        });
    }

    function closeAuthModal() {
        if (!authModal) {
            return;
        }

        authModal.hidden = true;
        authModal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");

        // Remove transient auth modal query params on close/cancel.
        var cleanedPath = cleanOriginPath(window.location.href);
        var currentPath = window.location.pathname + window.location.search + window.location.hash;
        if (cleanedPath !== currentPath) {
            window.history.replaceState({}, "", cleanedPath);
        }

        vLog("Closed auth modal.");
    }

    if (authModal) {
        authModal.addEventListener("click", function onModalClick(event) {
            var closeTarget = event.target;
            if (!(closeTarget instanceof Element)) {
                return;
            }

            if (closeTarget.hasAttribute("data-modal-close")) {
                closeAuthModal();
            }
        });

        document.addEventListener("keydown", function onKeyDown(event) {
            if (event.key === "Escape" && !authModal.hidden) {
                closeAuthModal();
            }
        });

        Array.prototype.slice.call(document.querySelectorAll("[data-auth-switch]"))
            .forEach(function wireSwitch(button) {
                button.addEventListener("click", function onSwitchClick(event) {
                    event.preventDefault();
                    var requestedMode = normalizeFlag(button.getAttribute("data-auth-switch"));
                    setAuthMode(requestedMode === "signup" ? "signup" : "login");
                });
            });
    }

    var authOpenButtons = Array.prototype.slice.call(
        document.querySelectorAll("[data-modal-open='auth']")
    );
    authOpenButtons.forEach(function wireAuthOpen(button) {
        button.addEventListener("click", function onAuthOpenClick(event) {
            event.preventDefault();
            var buttonMode = normalizeFlag(button.getAttribute("data-auth-mode"));
            var buttonReason = normalizeFlag(button.getAttribute("data-auth-reason"));
            openAuthModal({
                mode: buttonMode === "signup" ? "signup" : "login",
                reason: buttonReason === "continue" ? "continue" : "",
                originPath: window.location.href,
                nextPath: window.location.href
            });
        });
    });

    var guestActionButtons = Array.prototype.slice.call(
        document.querySelectorAll(".js-guest-action")
    );

    if (userState === "guest" && guestActionButtons.length > 0) {
        guestActionButtons.forEach(function wireGuestAction(button) {
            button.addEventListener("click", function onGuestActionClick(event) {
                event.preventDefault();
                var actionLabel = button.getAttribute("data-action-label") || "this action";
                vLog("Blocking guest action and opening shared auth modal.", actionLabel);
                openAuthModal({
                    mode: "login",
                    reason: "continue",
                    originPath: window.location.href,
                    nextPath: window.location.href
                });
            });
        });
        vLog("Guest action handlers attached.", guestActionButtons.length);
    } else {
        vLog("Guest action handlers were not attached.", {
            userState: userState,
            buttonCount: guestActionButtons.length
        });
    }

    var initialAuthState = readAuthStateFromUrl();
    if (initialAuthState.mode) {
        var normalizedInitialOriginPath = cleanOriginPath(window.location.href);
        openAuthModal({
            mode: initialAuthState.mode,
            reason: initialAuthState.reason,
            originPath: normalizedInitialOriginPath,
            nextPath: initialAuthState.nextPath || normalizedInitialOriginPath
        });
        if (initialAuthState.hasError) {
            vLog("Auth modal opened from URL with auth_error flag.");
        }
    }
})();
