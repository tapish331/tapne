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

    function initializeNavbarSearchDocking() {
        var navbarSearchSlot = document.querySelector("[data-navbar-search-slot]");
        var dockSourceForm = document.querySelector("form[data-navbar-dock-source]");
        var siteHeader = document.querySelector(".site-header");
        if (
            !(navbarSearchSlot instanceof HTMLElement) ||
            !(dockSourceForm instanceof HTMLFormElement) ||
            !(siteHeader instanceof HTMLElement)
        ) {
            return;
        }

        var sourceParent = dockSourceForm.parentNode;
        if (!(sourceParent instanceof Element)) {
            return;
        }

        var sourceEndMarker = document.createElement("span");
        sourceEndMarker.className = "search-dock-marker";
        sourceEndMarker.setAttribute("aria-hidden", "true");
        sourceParent.insertBefore(sourceEndMarker, dockSourceForm.nextSibling);

        var sourcePlaceholder = document.createElement("div");
        sourcePlaceholder.className = "search-dock-placeholder";
        sourcePlaceholder.setAttribute("aria-hidden", "true");
        sourcePlaceholder.hidden = true;

        var isDocked = false;
        var hasScheduledUpdate = false;

        function setDockedState(shouldDock) {
            var docked = !!shouldDock;
            if (docked === isDocked) {
                return;
            }

            if (docked) {
                if (sourceEndMarker.parentNode && !sourcePlaceholder.parentNode) {
                    sourceEndMarker.parentNode.insertBefore(sourcePlaceholder, sourceEndMarker);
                }
                sourcePlaceholder.hidden = false;
                sourcePlaceholder.style.height = Math.max(dockSourceForm.offsetHeight, 1) + "px";
                navbarSearchSlot.appendChild(dockSourceForm);
                dockSourceForm.classList.add("is-navbar-docked");
                navbarSearchSlot.setAttribute("data-has-docked-search", "true");
                isDocked = true;
                return;
            }

            if (sourceEndMarker.parentNode) {
                sourceEndMarker.parentNode.insertBefore(dockSourceForm, sourceEndMarker);
            }
            dockSourceForm.classList.remove("is-navbar-docked");
            if (sourcePlaceholder.parentNode) {
                sourcePlaceholder.parentNode.removeChild(sourcePlaceholder);
            }
            sourcePlaceholder.hidden = true;
            sourcePlaceholder.style.height = "";
            navbarSearchSlot.removeAttribute("data-has-docked-search");
            isDocked = false;
        }

        function shouldDockSearch() {
            var headerHeight = siteHeader.getBoundingClientRect().height || 0;
            var markerBottom = sourceEndMarker.getBoundingClientRect().bottom;
            return markerBottom <= (headerHeight + 6);
        }

        function updateDocking() {
            setDockedState(shouldDockSearch());
        }

        function queueDockUpdate() {
            if (hasScheduledUpdate) {
                return;
            }
            hasScheduledUpdate = true;
            window.requestAnimationFrame(function flushDockUpdate() {
                hasScheduledUpdate = false;
                updateDocking();
            });
        }

        window.addEventListener("scroll", queueDockUpdate, { passive: true });
        window.addEventListener("resize", queueDockUpdate);
        queueDockUpdate();
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

    function pathFromUrl(urlValue) {
        try {
            var url = new URL(urlValue || "", window.location.origin);
            return url.pathname || "/";
        } catch (_error) {
            return "";
        }
    }

    function parseFollowActionFromForm(form) {
        if (!(form instanceof HTMLFormElement)) {
            return null;
        }

        var actionPath = pathFromUrl(form.getAttribute("action") || form.action || "");
        var match = actionPath.match(/^\/social\/(follow|unfollow)\/([^/]+)\/?$/i);
        if (!match) {
            return null;
        }

        var rawUsername = "";
        try {
            rawUsername = decodeURIComponent(match[2] || "");
        } catch (_error) {
            rawUsername = String(match[2] || "");
        }
        var normalizedUsername = normalizeFlag(rawUsername).replace(/^@+/, "");
        if (!normalizedUsername) {
            return null;
        }

        return {
            action: normalizeFlag(match[1]),
            username: normalizedUsername
        };
    }

    function parseBookmarkActionFromForm(form) {
        if (!(form instanceof HTMLFormElement)) {
            return null;
        }

        var actionPath = pathFromUrl(form.getAttribute("action") || form.action || "");
        var match = actionPath.match(/^\/social\/(bookmark|unbookmark)\/?$/i);
        if (!match) {
            return null;
        }
        return {
            action: normalizeFlag(match[1])
        };
    }

    function parseTripRequestActionFromForm(form) {
        if (!(form instanceof HTMLFormElement)) {
            return null;
        }

        var actionPath = pathFromUrl(form.getAttribute("action") || form.action || "");
        var match = actionPath.match(/^\/enroll\/trips\/(\d+)\/request\/?$/i);
        if (!match) {
            return null;
        }
        return {
            tripId: String(match[1] || "")
        };
    }

    function normalizeBookmarkType(typeValue) {
        var normalizedType = normalizeFlag(typeValue);
        if (normalizedType === "trip" || normalizedType === "user" || normalizedType === "blog") {
            return normalizedType;
        }
        return "";
    }

    function normalizeBookmarkKey(typeValue, keyValue) {
        var targetType = normalizeBookmarkType(typeValue);
        var rawKey = String(keyValue || "").trim();
        if (!targetType || !rawKey) {
            return "";
        }

        if (targetType === "trip") {
            if (!/^\d+$/.test(rawKey)) {
                return "";
            }
            return String(parseInt(rawKey, 10));
        }
        if (targetType === "user") {
            return normalizeFlag(rawKey.replace(/^@+/, ""));
        }
        return normalizeFlag(rawKey);
    }

    function readBookmarkIdentity(form) {
        if (!(form instanceof HTMLFormElement)) {
            return null;
        }

        var typeInput = form.querySelector("input[name='type']");
        var idInput = form.querySelector("input[name='id']");
        var rawType = "";
        var rawId = "";
        if (typeInput instanceof HTMLInputElement) {
            rawType = typeInput.value || "";
        }
        if (idInput instanceof HTMLInputElement) {
            rawId = idInput.value || "";
        }

        var normalizedType = normalizeBookmarkType(rawType);
        var normalizedKey = normalizeBookmarkKey(normalizedType, rawId);
        if (!normalizedType || !normalizedKey) {
            return null;
        }

        return {
            targetType: normalizedType,
            targetKey: normalizedKey,
            idInput: idInput instanceof HTMLInputElement ? idInput : null
        };
    }

    function firstSubmitControl(form) {
        if (!(form instanceof HTMLFormElement)) {
            return null;
        }
        var control = form.querySelector("button[type='submit'], input[type='submit']");
        if (control instanceof HTMLButtonElement || control instanceof HTMLInputElement) {
            return control;
        }
        return null;
    }

    function setSubmitControlLabel(control, labelValue) {
        var label = String(labelValue || "").trim();
        if (!label) {
            return;
        }
        if (control instanceof HTMLButtonElement) {
            control.textContent = label;
        } else if (control instanceof HTMLInputElement) {
            control.value = label;
        }
    }

    function shouldHandleAsAsyncActionForm(form) {
        if (!(form instanceof HTMLFormElement)) {
            return false;
        }

        var methodValue = normalizeFlag(form.getAttribute("method") || form.method || "get");
        if (methodValue !== "post") {
            return false;
        }

        return (
            parseFollowActionFromForm(form) !== null ||
            parseBookmarkActionFromForm(form) !== null ||
            parseTripRequestActionFromForm(form) !== null
        );
    }

    function setAsyncFormBusy(form, isBusy) {
        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        var controls = Array.prototype.slice.call(
            form.querySelectorAll("button[type='submit'], input[type='submit']")
        );
        if (isBusy) {
            form.setAttribute("data-async-pending", "1");
            controls.forEach(function disableControl(control) {
                if (!(control instanceof HTMLButtonElement || control instanceof HTMLInputElement)) {
                    return;
                }

                var wasDisabled = control.hasAttribute("disabled");
                control.setAttribute("data-async-was-disabled", wasDisabled ? "1" : "0");
                control.setAttribute("disabled", "disabled");
            });
            return;
        }

        form.removeAttribute("data-async-pending");
        controls.forEach(function restoreControl(control) {
            if (!(control instanceof HTMLButtonElement || control instanceof HTMLInputElement)) {
                return;
            }

            var shouldStayDisabled = control.getAttribute("data-async-was-disabled") === "1";
            var isForceDisabled = control.getAttribute("data-async-force-disabled") === "1";
            control.removeAttribute("data-async-was-disabled");
            if (shouldStayDisabled || isForceDisabled) {
                control.setAttribute("disabled", "disabled");
            } else {
                control.removeAttribute("disabled");
            }
        });
    }

    var asyncToastStack = null;

    function ensureAsyncToastStack() {
        if (asyncToastStack instanceof HTMLElement && document.body.contains(asyncToastStack)) {
            return asyncToastStack;
        }

        asyncToastStack = document.createElement("section");
        asyncToastStack.className = "flash-list flash-list-floating";
        asyncToastStack.setAttribute("aria-label", "Action notifications");
        asyncToastStack.setAttribute("aria-live", "polite");
        asyncToastStack.setAttribute("aria-atomic", "false");
        asyncToastStack.hidden = true;
        document.body.appendChild(asyncToastStack);
        return asyncToastStack;
    }

    function showAsyncToast(levelValue, messageValue) {
        var messageText = String(messageValue || "").trim();
        if (!messageText) {
            return;
        }

        var normalizedLevel = normalizeFlag(levelValue);
        if (["success", "info", "warning", "error"].indexOf(normalizedLevel) < 0) {
            normalizedLevel = "info";
        }

        var stack = ensureAsyncToastStack();
        var toast = document.createElement("div");
        toast.className = "flash flash-" + normalizedLevel + " flash-toast";
        toast.textContent = messageText;
        toast.setAttribute("role", normalizedLevel === "error" ? "alert" : "status");
        stack.hidden = false;
        stack.appendChild(toast);

        window.requestAnimationFrame(function showToast() {
            toast.classList.add("is-visible");
        });

        window.setTimeout(function hideToast() {
            toast.classList.add("is-exit");
            window.setTimeout(function removeToastNode() {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
                if (stack.childElementCount === 0) {
                    stack.hidden = true;
                }
            }, 220);
        }, 4200);
    }

    function updateFollowForms(payload) {
        var targetUsername = normalizeFlag(payload && payload.target_username).replace(/^@+/, "");
        if (!targetUsername) {
            return;
        }

        var isFollowing = !!(payload && payload.is_following);
        var fallbackAction = (
            (isFollowing ? "/social/unfollow/" : "/social/follow/") +
            encodeURIComponent(targetUsername) +
            "/"
        );
        var nextActionUrl = normalizePath(
            String((payload && payload.next_action_url) || ""),
            fallbackAction
        );

        Array.prototype.slice.call(document.querySelectorAll("form"))
            .forEach(function syncFollowForm(form) {
                if (!(form instanceof HTMLFormElement)) {
                    return;
                }
                var parsed = parseFollowActionFromForm(form);
                if (!parsed || parsed.username !== targetUsername) {
                    return;
                }

                form.setAttribute("action", nextActionUrl);
                var submitControl = firstSubmitControl(form);
                if (!submitControl) {
                    return;
                }
                var nextLabel = isFollowing ? "Unfollow" : "Follow";
                setSubmitControlLabel(submitControl, nextLabel);
                submitControl.setAttribute("aria-label", nextLabel);
                submitControl.setAttribute("title", nextLabel);
            });
    }

    function updateBookmarkForms(payload, sourceForm) {
        var targetType = normalizeBookmarkType(payload && payload.target_type);
        var targetKey = normalizeBookmarkKey(targetType, payload && payload.target_key);
        if (!targetType || !targetKey) {
            return;
        }

        var isBookmarked = !!(payload && payload.is_bookmarked);
        var fallbackAction = isBookmarked ? "/social/unbookmark/" : "/social/bookmark/";
        var nextActionUrl = normalizePath(
            String((payload && payload.next_action_url) || ""),
            fallbackAction
        );

        Array.prototype.slice.call(document.querySelectorAll("form"))
            .forEach(function syncBookmarkForm(form) {
                if (!(form instanceof HTMLFormElement)) {
                    return;
                }

                if (!parseBookmarkActionFromForm(form)) {
                    return;
                }

                var identity = readBookmarkIdentity(form);
                if (!identity) {
                    return;
                }
                if (identity.targetType !== targetType || identity.targetKey !== targetKey) {
                    return;
                }

                form.setAttribute("action", nextActionUrl);
                if (identity.idInput) {
                    identity.idInput.value = targetKey;
                }

                var submitControl = firstSubmitControl(form);
                if (!submitControl) {
                    return;
                }

                if (submitControl.classList.contains("trip-bookmark-icon-btn")) {
                    submitControl.classList.toggle("is-bookmarked", isBookmarked);
                    var iconLabel = isBookmarked ? "Remove bookmark" : "Bookmark this trip";
                    submitControl.setAttribute("aria-label", iconLabel);
                    submitControl.setAttribute("title", iconLabel);
                    return;
                }

                var currentLabel = "";
                if (submitControl instanceof HTMLButtonElement) {
                    currentLabel = submitControl.textContent || "";
                } else if (submitControl instanceof HTMLInputElement) {
                    currentLabel = submitControl.value || "";
                }

                var normalizedCurrentLabel = normalizeFlag(currentLabel);
                var nextLabel = isBookmarked ? "Remove bookmark" : "Bookmark";
                if (!isBookmarked && normalizedCurrentLabel.indexOf("profile") >= 0) {
                    nextLabel = "Bookmark profile";
                }
                setSubmitControlLabel(submitControl, nextLabel);
                submitControl.setAttribute("aria-label", nextLabel);
                submitControl.setAttribute("title", nextLabel);
            });

        if (
            payload &&
            payload.action === "unbookmark" &&
            payload.outcome === "removed" &&
            sourceForm instanceof HTMLFormElement &&
            window.location.pathname.indexOf("/social/bookmarks/") === 0
        ) {
            var listItem = sourceForm.closest(".card-grid > div");
            if (listItem instanceof HTMLElement) {
                listItem.remove();
            }
        }
    }

    function tripRequestUiForOutcome(outcomeValue) {
        var outcome = normalizeFlag(outcomeValue);
        if (outcome === "created-pending" || outcome === "already-pending" || outcome === "reopened-pending") {
            return { label: "Request sent", disable: true };
        }
        if (outcome === "already-approved") {
            return { label: "Already approved", disable: true };
        }
        if (outcome === "host-self-request-blocked") {
            return { label: "Unavailable", disable: true };
        }
        return null;
    }

    function updateTripRequestForms(payload) {
        var tripId = String((payload && payload.trip_id) || "").trim();
        if (!tripId) {
            return;
        }

        var ui = tripRequestUiForOutcome(payload && payload.outcome);
        if (!ui) {
            return;
        }

        Array.prototype.slice.call(document.querySelectorAll("form"))
            .forEach(function syncTripRequestForm(form) {
                if (!(form instanceof HTMLFormElement)) {
                    return;
                }

                var parsed = parseTripRequestActionFromForm(form);
                if (!parsed || parsed.tripId !== tripId) {
                    return;
                }

                var submitControl = firstSubmitControl(form);
                if (!submitControl) {
                    return;
                }
                setSubmitControlLabel(submitControl, ui.label);
                submitControl.setAttribute("aria-label", ui.label);
                submitControl.setAttribute("title", ui.label);
                if (ui.disable) {
                    submitControl.setAttribute("data-async-force-disabled", "1");
                    submitControl.setAttribute("disabled", "disabled");
                } else {
                    submitControl.removeAttribute("data-async-force-disabled");
                }
            });
    }

    function parseJsonResponse(response) {
        var contentType = String(response.headers.get("Content-Type") || "").toLowerCase();
        if (contentType.indexOf("application/json") < 0) {
            return Promise.resolve(null);
        }
        return response.json().catch(function onJsonParseError() {
            return null;
        });
    }

    function applyAsyncActionPayload(form, response, payload) {
        if (!payload || typeof payload !== "object") {
            if (response && response.url) {
                window.location.assign(response.url);
                return;
            }
            window.location.reload();
            return;
        }

        var level = normalizeFlag(payload.level);
        if (!level) {
            level = payload.ok === false ? "error" : "info";
        }

        if (payload.message) {
            showAsyncToast(level, payload.message);
        }

        if (payload.ok !== true) {
            return;
        }

        if (payload.action === "follow" || payload.action === "unfollow") {
            updateFollowForms(payload);
            return;
        }

        if (payload.action === "bookmark" || payload.action === "unbookmark") {
            updateBookmarkForms(payload, form);
            return;
        }

        if (payload.action === "trip-request") {
            updateTripRequestForms(payload);
        }
    }

    function submitAsyncActionForm(form) {
        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        if (form.getAttribute("data-async-pending") === "1") {
            return;
        }

        var actionUrl = form.getAttribute("action") || form.action || window.location.href;
        var csrfToken = readCookieValue("csrftoken");
        var requestHeaders = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        };
        if (csrfToken) {
            requestHeaders["X-CSRFToken"] = csrfToken;
        }

        setAsyncFormBusy(form, true);
        window.fetch(actionUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: requestHeaders,
            body: new window.FormData(form)
        }).then(function onFetchResponse(response) {
            return parseJsonResponse(response).then(function onParsedPayload(payload) {
                return {
                    response: response,
                    payload: payload
                };
            });
        }).then(function onFetchResolved(result) {
            applyAsyncActionPayload(form, result.response, result.payload);
        }).catch(function onFetchError(error) {
            vLog("Async action submission failed.", String(error));
            form.submit();
        }).finally(function onFetchSettled() {
            setAsyncFormBusy(form, false);
        });
    }

    function initializeAsyncStateForms() {
        document.addEventListener("submit", function onAsyncFormSubmit(event) {
            var submittedForm = event.target;
            if (!(submittedForm instanceof HTMLFormElement)) {
                return;
            }
            if (!shouldHandleAsAsyncActionForm(submittedForm)) {
                return;
            }

            event.preventDefault();
            submitAsyncActionForm(submittedForm);
        });
    }

    initializeThemeControls();
    initializeMemberMenu();
    initializeNavbarSearchDocking();
    initializeAsyncStateForms();

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
