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
    var authModalTitle = document.getElementById("authModalTitle");
    var authModalContextNote = document.getElementById("authModalContextNote");
    var themeToggleButton = document.getElementById("themeToggle");
    var colorSchemeSelect = document.getElementById("colorSchemeSelect");
    var authQueryKeys = ["auth", "auth_reason", "auth_error", "auth_next"];
    var themeStorageKey = "tapne.theme";
    var paletteStorageKey = "tapne.palette";
    var supportedPalettes = ["coast", "ember", "forest"];
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

    function persistAppearanceToBackend(themePreference, colorScheme) {
        if (!shouldPersistAppearanceToBackend) {
            return Promise.resolve(null);
        }

        var csrfToken = readCookieValue("csrftoken");
        var payload = {
            theme_preference: sanitizeThemePreference(themePreference),
            color_scheme: sanitizePalette(colorScheme)
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
            var savedColorScheme = sanitizePalette(data.color_scheme);
            var resolvedTheme = resolveThemeFromPreference(savedThemePreference);
            applyTheme(resolvedTheme, savedThemePreference, true);
            applyPalette(savedColorScheme, true);

            vLog("Appearance persisted to backend.", {
                outcome: data.outcome || "unknown",
                themePreference: savedThemePreference,
                colorScheme: savedColorScheme
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

    function sanitizePalette(paletteValue) {
        var normalized = normalizeFlag(paletteValue);
        if (supportedPalettes.indexOf(normalized) >= 0) {
            return normalized;
        }
        return "coast";
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
        var buttonLabel = switchTarget === "dark" ? "Switch to dark" : "Switch to light";
        themeToggleButton.textContent = buttonLabel;
        themeToggleButton.setAttribute("aria-label", buttonLabel + " mode");
        themeToggleButton.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    }

    function updatePaletteSelectUI(paletteValue) {
        if (!colorSchemeSelect) {
            return;
        }
        colorSchemeSelect.value = sanitizePalette(paletteValue);
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

    function applyPalette(paletteValue, persistPalette) {
        var palette = sanitizePalette(paletteValue);
        html.setAttribute("data-color-scheme", palette);
        window.TAPNE_RUNTIME.colorScheme = palette;
        updatePaletteSelectUI(palette);

        if (persistPalette) {
            writeStorage(paletteStorageKey, palette);
        }
        return palette;
    }

    function initializeThemeControls() {
        var storedTheme = "";
        var storedPaletteRaw = "";
        if (!shouldPersistAppearanceToBackend) {
            storedTheme = sanitizeTheme(readStorage(themeStorageKey));
            storedPaletteRaw = readStorage(paletteStorageKey);
        }
        var storedPalette = storedPaletteRaw ? sanitizePalette(storedPaletteRaw) : "";
        var currentThemePreference = sanitizeThemePreference(html.getAttribute("data-theme-preference"));
        var currentTheme = sanitizeTheme(html.getAttribute("data-theme"));
        var currentPalette = sanitizePalette(html.getAttribute("data-color-scheme"));

        if (storedTheme) {
            currentTheme = storedTheme;
            currentThemePreference = storedTheme;
        } else if (!currentTheme) {
            currentTheme = resolveThemeFromPreference(currentThemePreference);
        }

        if (storedPalette) {
            currentPalette = storedPalette;
        }

        applyTheme(currentTheme, currentThemePreference, false);
        applyPalette(currentPalette, false);

        if (themeToggleButton) {
            themeToggleButton.addEventListener("click", function onThemeToggle() {
                var activeTheme = sanitizeTheme(html.getAttribute("data-theme")) || "light";
                var nextTheme = activeTheme === "dark" ? "light" : "dark";
                applyTheme(nextTheme, nextTheme, true);
                persistAppearanceToBackend(
                    nextTheme,
                    sanitizePalette(html.getAttribute("data-color-scheme"))
                );
                vLog("Theme toggled.", { previous: activeTheme, next: nextTheme });
            });
        }

        if (colorSchemeSelect) {
            colorSchemeSelect.addEventListener("change", function onPaletteChange() {
                var nextPalette = sanitizePalette(colorSchemeSelect.value);
                applyPalette(nextPalette, true);
                persistAppearanceToBackend(
                    sanitizeThemePreference(html.getAttribute("data-theme-preference")),
                    nextPalette
                );
                vLog("Color scheme changed.", nextPalette);
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

    initializeThemeControls();

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
