/* Shared frontend helpers for theme controls and guest/member interaction behavior. */
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
    var authModalPanel = authModal ? authModal.querySelector(".auth-modal-panel") : null;
    var authModalTitle = document.getElementById("authModalTitle");
    var authModalContextNote = document.getElementById("authModalContextNote");
    var authFocusableSelector = [
        "a[href]",
        "area[href]",
        "input:not([disabled]):not([type='hidden'])",
        "select:not([disabled])",
        "textarea:not([disabled])",
        "button:not([disabled])",
        "[tabindex]:not([tabindex='-1'])",
        "[contenteditable='true']"
    ].join(", ");
    var authModalBackgroundState = [];
    var authModalFocusRestoreTarget = null;
    var themeToggleButton = document.getElementById("themeToggle");
    var memberMenuRoot = document.querySelector("[data-member-menu]");
    var memberMenuToggle = memberMenuRoot ? memberMenuRoot.querySelector("[data-member-menu-toggle]") : null;
    var memberMenuPanel = memberMenuRoot ? memberMenuRoot.querySelector("[data-member-menu-panel]") : null;
    var authQueryKeys = ["auth", "auth_reason", "auth_error", "auth_next"];
    var themeStorageKey = "tapne.theme";
    var appearanceSource = normalizeFlag(window.TAPNE_RUNTIME && window.TAPNE_RUNTIME.appearanceSource) || "local-storage";
    var appearanceSaveUrl = String((window.TAPNE_RUNTIME && window.TAPNE_RUNTIME.appearanceSaveUrl) || "").trim();
    var shouldPersistAppearanceToBackend = (
        userState === "member" &&
        appearanceSource === "member-settings" &&
        appearanceSaveUrl.length > 0
    );

    if (!window.TAPNE_RUNTIME) {
        window.TAPNE_RUNTIME = {};
    }

    if (authModalPanel && !authModalPanel.hasAttribute("tabindex")) {
        authModalPanel.setAttribute("tabindex", "-1");
    }

    function readStorage(key) {
        try {
            return window.localStorage.getItem(key) || "";
        } catch (_error) {
            return "";
        }
    }

    function writeStorage(key, value) {
        try {
            window.localStorage.setItem(key, value);
        } catch (_error) {
            vLog("Unable to write to localStorage for key.", key);
        }
    }

    function removeStorage(key) {
        try {
            window.localStorage.removeItem(key);
        } catch (_error) {
            vLog("Unable to remove localStorage key.", key);
        }
    }

    function readCookieValue(name) {
        var cookieName = String(name || "").trim();
        if (!cookieName || typeof document.cookie !== "string") {
            return "";
        }

        var encodedPrefix = encodeURIComponent(cookieName) + "=";
        var cookies = document.cookie.split(";");
        for (var index = 0; index < cookies.length; index += 1) {
            var candidate = String(cookies[index] || "").trim();
            if (candidate.indexOf(encodedPrefix) !== 0) {
                continue;
            }

            return decodeURIComponent(candidate.slice(encodedPrefix.length));
        }
        return "";
    }

    function persistAppearanceToBackend(themePreference) {
        if (!shouldPersistAppearanceToBackend) {
            return Promise.resolve(null);
        }

        var csrfToken = readCookieValue("csrftoken");
        var payload = {
            theme_preference: sanitizeThemePreference(themePreference)
        };
        var headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        };
        if (csrfToken) {
            headers["X-CSRFToken"] = csrfToken;
        }

        return window.fetch(appearanceSaveUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: headers,
            body: JSON.stringify(payload)
        }).then(function parseResponse(response) {
            if (!response.ok) {
                throw new Error("Appearance save failed with status " + response.status);
            }
            return response.json();
        }).then(function applyNormalizedResponse(data) {
            if (!data || data.ok !== true) {
                throw new Error("Appearance save response was not ok.");
            }

            var savedThemePreference = sanitizeThemePreference(data.theme_preference);
            var resolvedTheme = resolveThemeFromPreference(savedThemePreference);
            applyTheme(resolvedTheme, savedThemePreference, true);

            vLog("Appearance persisted to backend.", {
                outcome: data.outcome || "unknown",
                themePreference: savedThemePreference
            });
            return data;
        }).catch(function onAppearancePersistError(error) {
            vLog("Failed to persist appearance to backend.", String(error));
            return null;
        });
    }

    function prefersDarkTheme() {
        try {
            return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
        } catch (_error) {
            return false;
        }
    }

    function sanitizeTheme(themeValue) {
        var normalized = normalizeFlag(themeValue);
        if (normalized === "light" || normalized === "dark") {
            return normalized;
        }
        return "";
    }

    function sanitizeThemePreference(preferenceValue) {
        var normalized = normalizeFlag(preferenceValue);
        if (normalized === "light" || normalized === "dark" || normalized === "system") {
            return normalized;
        }
        return "system";
    }

    function resolveThemeFromPreference(preferenceValue) {
        var preference = sanitizeThemePreference(preferenceValue);
        if (preference === "light" || preference === "dark") {
            return preference;
        }
        return prefersDarkTheme() ? "dark" : "light";
    }

    function updateThemeToggleUI(themeValue) {
        if (!themeToggleButton) {
            return;
        }

        var theme = sanitizeTheme(themeValue) || "light";
        var switchTarget = theme === "dark" ? "light" : "dark";
        var buttonLabel = switchTarget === "dark" ? "Switch to dark mode" : "Switch to light mode";
        var buttonSymbol = switchTarget === "dark" ? "\uD83C\uDF19" : "\uD83C\uDF1E";
        themeToggleButton.textContent = buttonSymbol;
        themeToggleButton.setAttribute("aria-label", buttonLabel);
        themeToggleButton.setAttribute("title", buttonLabel);
        themeToggleButton.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    }

    function applyTheme(themeValue, preferenceValue, persistPreference) {
        var preference = sanitizeThemePreference(preferenceValue);
        var theme = sanitizeTheme(themeValue) || resolveThemeFromPreference(preference);
        html.setAttribute("data-theme", theme);
        html.setAttribute("data-theme-preference", preference);
        window.TAPNE_RUNTIME.theme = theme;
        window.TAPNE_RUNTIME.themePreference = preference;
        updateThemeToggleUI(theme);

        if (persistPreference) {
            if (preference === "system") {
                removeStorage(themeStorageKey);
            } else {
                writeStorage(themeStorageKey, theme);
            }
        }

        return theme;
    }

    function initializeThemeControls() {
        var storedTheme = "";
        if (!shouldPersistAppearanceToBackend) {
            storedTheme = sanitizeTheme(readStorage(themeStorageKey));
        }
        var currentThemePreference = sanitizeThemePreference(html.getAttribute("data-theme-preference"));
        var currentTheme = sanitizeTheme(html.getAttribute("data-theme"));

        if (storedTheme) {
            currentTheme = storedTheme;
            currentThemePreference = storedTheme;
        } else if (!currentTheme) {
            currentTheme = resolveThemeFromPreference(currentThemePreference);
        }

        applyTheme(currentTheme, currentThemePreference, false);

        if (themeToggleButton) {
            themeToggleButton.addEventListener("click", function onThemeToggle() {
                var activeTheme = sanitizeTheme(html.getAttribute("data-theme")) || "light";
                var nextTheme = activeTheme === "dark" ? "light" : "dark";
                applyTheme(nextTheme, nextTheme, true);
                persistAppearanceToBackend(nextTheme);
                vLog("Theme toggled.", { previous: activeTheme, next: nextTheme });
            });
        }

        if (window.matchMedia) {
            var darkModeQuery = window.matchMedia("(prefers-color-scheme: dark)");
            var onSystemThemeChange = function onSystemThemeChange() {
                var preference = sanitizeThemePreference(html.getAttribute("data-theme-preference"));
                if (preference !== "system") {
                    return;
                }
                applyTheme(resolveThemeFromPreference("system"), "system", false);
                vLog("Applied system theme change.");
            };

            if (typeof darkModeQuery.addEventListener === "function") {
                darkModeQuery.addEventListener("change", onSystemThemeChange);
            } else if (typeof darkModeQuery.addListener === "function") {
                darkModeQuery.addListener(onSystemThemeChange);
            }
        }
    }

    function isMemberMenuOpen() {
        return !!(memberMenuPanel && !memberMenuPanel.hidden);
    }

    function setMemberMenuOpen(shouldOpen) {
        if (!memberMenuRoot || !memberMenuToggle || !memberMenuPanel) {
            return;
        }

        var isOpen = !!shouldOpen;
        memberMenuPanel.hidden = !isOpen;
        memberMenuToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");

        if (isOpen) {
            memberMenuRoot.setAttribute("data-open", "true");
        } else {
            memberMenuRoot.removeAttribute("data-open");
        }
    }

    function closeMemberMenu() {
        if (!isMemberMenuOpen()) {
            return;
        }
        setMemberMenuOpen(false);
    }

    function initializeMemberMenu() {
        if (!memberMenuRoot || !memberMenuToggle || !memberMenuPanel) {
            return;
        }

        setMemberMenuOpen(false);

        memberMenuToggle.addEventListener("click", function onMemberMenuToggle(event) {
            event.preventDefault();
            setMemberMenuOpen(!isMemberMenuOpen());
        });

        document.addEventListener("click", function onDocumentClick(event) {
            if (!isMemberMenuOpen()) {
                return;
            }

            var clickTarget = event.target;
            if (!(clickTarget instanceof Node)) {
                return;
            }
            if (memberMenuRoot.contains(clickTarget)) {
                return;
            }
            closeMemberMenu();
        });

        document.addEventListener("keydown", function onDocumentKeyDown(event) {
            if (event.key !== "Escape" || !isMemberMenuOpen()) {
                return;
            }
            closeMemberMenu();
            if (typeof memberMenuToggle.focus === "function") {
                memberMenuToggle.focus();
            }
        });

        memberMenuPanel.addEventListener("click", function onPanelClick(event) {
            var clickTarget = event.target;
            if (!(clickTarget instanceof Element)) {
                return;
            }
            if (clickTarget.closest("a[href]")) {
                closeMemberMenu();
            }
        });
    }

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

    function isVisibleForFocus(element) {
        if (!(element instanceof HTMLElement)) {
            return false;
        }
        if (element.hidden || element.getAttribute("aria-hidden") === "true") {
            return false;
        }
        if (typeof element.closest === "function") {
            if (element.closest("[hidden]")) {
                return false;
            }
            if (element.closest("[aria-hidden='true']")) {
                return false;
            }
        }
        return element.getClientRects().length > 0;
    }

    function modalFocusableElements() {
        if (!authModal) {
            return [];
        }

        return Array.prototype.slice.call(authModal.querySelectorAll(authFocusableSelector))
            .filter(function keepFocusable(element) {
                if (!(element instanceof HTMLElement)) {
                    return false;
                }
                if (element.hasAttribute("disabled")) {
                    return false;
                }
                return isVisibleForFocus(element);
            });
    }

    function rememberModalFocusRestoreTarget(triggerElement) {
        if (triggerElement instanceof HTMLElement) {
            authModalFocusRestoreTarget = triggerElement;
            return;
        }

        var activeElement = document.activeElement;
        if (activeElement instanceof HTMLElement && (!authModal || !authModal.contains(activeElement))) {
            authModalFocusRestoreTarget = activeElement;
        }
    }

    function restoreModalFocus() {
        var focusTarget = authModalFocusRestoreTarget;
        authModalFocusRestoreTarget = null;
        if (!(focusTarget instanceof HTMLElement) || typeof focusTarget.focus !== "function") {
            return;
        }

        window.setTimeout(function focusAfterClose() {
            try {
                focusTarget.focus();
            } catch (_error) {
                // No-op: target may no longer exist or be focusable.
            }
        }, 0);
    }

    function setAuthBackgroundInert(shouldInert) {
        if (!authModal) {
            return;
        }

        if (shouldInert) {
            if (authModalBackgroundState.length > 0) {
                return;
            }

            Array.prototype.slice.call(document.body.children)
                .forEach(function captureAndInert(node) {
                    if (!(node instanceof HTMLElement)) {
                        return;
                    }
                    if (node === authModal) {
                        return;
                    }

                    authModalBackgroundState.push({
                        element: node,
                        hadInert: node.hasAttribute("inert"),
                        hadAriaHidden: node.hasAttribute("aria-hidden"),
                        ariaHiddenValue: node.getAttribute("aria-hidden")
                    });

                    node.setAttribute("inert", "");
                    node.setAttribute("aria-hidden", "true");
                });
            return;
        }

        if (authModalBackgroundState.length === 0) {
            return;
        }

        authModalBackgroundState.forEach(function restoreNode(state) {
            var node = state.element;
            if (!(node instanceof HTMLElement)) {
                return;
            }

            if (!state.hadInert) {
                node.removeAttribute("inert");
            }

            if (state.hadAriaHidden) {
                if (state.ariaHiddenValue === null) {
                    node.setAttribute("aria-hidden", "true");
                } else {
                    node.setAttribute("aria-hidden", state.ariaHiddenValue);
                }
            } else {
                node.removeAttribute("aria-hidden");
            }
        });
        authModalBackgroundState = [];
    }

    function focusFirstElementInAuthModal() {
        if (!authModal || authModal.hidden) {
            return;
        }

        var activePane = null;
        Array.prototype.slice.call(authModal.querySelectorAll("[data-auth-pane]"))
            .forEach(function findVisiblePane(pane) {
                if (activePane || pane.hidden) {
                    return;
                }
                activePane = pane;
            });

        var preferredField = null;
        if (activePane) {
            preferredField = activePane.querySelector(
                "input:not([type='hidden']):not([disabled]), " +
                "select:not([disabled]), textarea:not([disabled]), " +
                "button:not([disabled]), a[href]"
            );
            if (!isVisibleForFocus(preferredField)) {
                preferredField = null;
            }
        }

        var focusTargets = modalFocusableElements();
        var focusTarget = preferredField || focusTargets[0] || authModalPanel;
        if (focusTarget && typeof focusTarget.focus === "function") {
            focusTarget.focus();
        }
    }

    function enforceModalFocusContainment() {
        if (!authModal || authModal.hidden) {
            return;
        }

        var activeElement = document.activeElement;
        if (activeElement instanceof Element && authModal.contains(activeElement)) {
            return;
        }

        var focusTargets = modalFocusableElements();
        var focusTarget = focusTargets[0] || authModalPanel;
        if (focusTarget && typeof focusTarget.focus === "function") {
            focusTarget.focus();
        }
    }

    function trapModalTabNavigation(event) {
        if (!authModal || authModal.hidden || event.key !== "Tab") {
            return;
        }

        var focusTargets = modalFocusableElements();
        if (focusTargets.length === 0) {
            event.preventDefault();
            if (authModalPanel && typeof authModalPanel.focus === "function") {
                authModalPanel.focus();
            }
            return;
        }

        var firstTarget = focusTargets[0];
        var lastTarget = focusTargets[focusTargets.length - 1];
        var activeElement = document.activeElement;
        var activeInsideModal = activeElement instanceof Element && authModal.contains(activeElement);

        if (event.shiftKey) {
            if (!activeInsideModal || activeElement === firstTarget) {
                event.preventDefault();
                lastTarget.focus();
            }
            return;
        }

        if (!activeInsideModal || activeElement === lastTarget) {
            event.preventDefault();
            firstTarget.focus();
        }
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

        rememberModalFocusRestoreTarget(config && config.triggerElement);
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
        setAuthBackgroundInert(true);
        focusFirstElementInAuthModal();
        vLog("Opened auth modal.", {
            mode: mode,
            reason: reason,
            nextPath: nextPath,
            originPath: originPath
        });
    }

    function closeAuthModal(options) {
        if (!authModal) {
            return;
        }

        var shouldRestoreFocus = !options || options.restoreFocus !== false;
        authModal.hidden = true;
        authModal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
        setAuthBackgroundInert(false);

        // Remove transient auth modal query params on close/cancel.
        var cleanedPath = cleanOriginPath(window.location.href);
        var currentPath = window.location.pathname + window.location.search + window.location.hash;
        if (cleanedPath !== currentPath) {
            window.history.replaceState({}, "", cleanedPath);
        }

        if (shouldRestoreFocus) {
            restoreModalFocus();
        } else {
            authModalFocusRestoreTarget = null;
        }

        vLog("Closed auth modal.");
    }

    initializeThemeControls();
    initializeMemberMenu();

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
            if (authModal.hidden) {
                return;
            }

            if (event.key === "Escape") {
                event.preventDefault();
                closeAuthModal();
                return;
            }

            trapModalTabNavigation(event);
        });

        document.addEventListener("focusin", function onFocusIn(event) {
            if (authModal.hidden) {
                return;
            }

            var focusedNode = event.target;
            if (focusedNode instanceof Element && authModal.contains(focusedNode)) {
                return;
            }

            enforceModalFocusContainment();
        });

        Array.prototype.slice.call(document.querySelectorAll("[data-auth-switch]"))
            .forEach(function wireSwitch(button) {
                button.addEventListener("click", function onSwitchClick(event) {
                    event.preventDefault();
                    var requestedMode = normalizeFlag(button.getAttribute("data-auth-switch"));
                    setAuthMode(requestedMode === "signup" ? "signup" : "login");
                    focusFirstElementInAuthModal();
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
                nextPath: window.location.href,
                triggerElement: button
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
                    nextPath: window.location.href,
                    triggerElement: button
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
