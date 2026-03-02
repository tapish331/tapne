/* Dynamic builders for structured trip creation sections. */
(function bootstrapTripFormBuilders() {
    "use strict";

    function parseJson(rawValue, fallbackValue) {
        var text = String(rawValue || "").trim();
        if (!text) {
            return fallbackValue;
        }
        try {
            return JSON.parse(text);
        } catch (_error) {
            return fallbackValue;
        }
    }

    function rowButton(label, onClick) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-ghost";
        button.textContent = label;
        button.addEventListener("click", onClick);
        return button;
    }

    function requestProgressRefresh(root) {
        if (!root || typeof root.closest !== "function") {
            return;
        }
        var parentForm = root.closest("form");
        if (!parentForm) {
            return;
        }
        parentForm.dispatchEvent(new Event("trip-progress-refresh"));
    }

    function syncListBuilder(root) {
        var inputId = root.getAttribute("data-target-input-id");
        var hiddenInput = inputId ? document.getElementById(inputId) : null;
        if (!hiddenInput) {
            return;
        }

        var values = Array.prototype.slice.call(root.querySelectorAll("[data-list-row]"))
            .map(function mapRow(row) {
                var input = row.querySelector("[data-list-value]");
                return input ? String(input.value || "").trim() : "";
            })
            .filter(function nonEmpty(value) {
                return value.length > 0;
            });
        hiddenInput.value = JSON.stringify(values);
        requestProgressRefresh(root);
    }

    function createListRow(root, value) {
        var row = document.createElement("div");
        row.className = "dynamic-list-row";
        row.setAttribute("data-list-row", "1");

        var input = document.createElement("input");
        input.type = "text";
        input.className = "form-input";
        input.setAttribute("data-list-value", "1");
        input.placeholder = root.getAttribute("data-item-example") || root.getAttribute("data-item-label") || "Item";
        input.value = String(value || "");
        input.addEventListener("input", function onInput() {
            syncListBuilder(root);
        });

        var remove = rowButton("Remove", function onRemove() {
            row.remove();
            syncListBuilder(root);
        });

        row.appendChild(input);
        row.appendChild(remove);
        return row;
    }

    function initListBuilder(root) {
        var inputId = root.getAttribute("data-target-input-id");
        var hiddenInput = inputId ? document.getElementById(inputId) : null;
        var itemsHost = root.querySelector("[data-list-items]");
        var addButton = root.querySelector("[data-list-add]");
        if (!hiddenInput || !itemsHost || !addButton) {
            return;
        }

        var initialItems = parseJson(hiddenInput.value, []);
        if (!Array.isArray(initialItems) || initialItems.length === 0) {
            itemsHost.appendChild(createListRow(root, ""));
        } else {
            initialItems.forEach(function eachItem(item) {
                itemsHost.appendChild(createListRow(root, item));
            });
        }

        addButton.addEventListener("click", function onAdd() {
            itemsHost.appendChild(createListRow(root, ""));
            syncListBuilder(root);
        });

        syncListBuilder(root);
    }

    function syncDayBuilder(root) {
        var inputId = root.getAttribute("data-target-input-id");
        var hiddenInput = inputId ? document.getElementById(inputId) : null;
        if (!hiddenInput) {
            return;
        }

        var days = Array.prototype.slice.call(root.querySelectorAll("[data-day-row]"))
            .map(function mapRow(row) {
                return {
                    is_flexible: !!(row.querySelector("[data-day-flexible]") || {}).checked,
                    title: String(((row.querySelector("[data-day-title]") || {}).value || "")).trim(),
                    description: String(((row.querySelector("[data-day-description]") || {}).value || "")).trim(),
                    stay: String(((row.querySelector("[data-day-stay]") || {}).value || "")).trim(),
                    meals: String(((row.querySelector("[data-day-meals]") || {}).value || "")).trim()
                };
            })
            .filter(function nonEmpty(day) {
                return day.title || day.description || day.stay || day.meals;
            });

        hiddenInput.value = JSON.stringify(days);
        requestProgressRefresh(root);
    }

    function createDayRow(root, value) {
        var dayValue = value && typeof value === "object" ? value : {};
        var row = document.createElement("div");
        row.className = "dynamic-day-row";
        row.setAttribute("data-day-row", "1");

        row.innerHTML = "" +
            "<div class=\"trip-form-grid trip-form-grid-2\">" +
            "  <label class=\"inline-checkbox-label\"><input type=\"checkbox\" data-day-flexible> flexible?</label>" +
            "</div>" +
            "<div class=\"form-field\"><label>Day Title</label><input class=\"form-input\" type=\"text\" maxlength=\"180\" data-day-title placeholder=\"e.g. Arrival + old town walk\"></div>" +
            "<div class=\"form-field\"><label>What happens on this day ...</label><textarea class=\"form-input\" rows=\"4\" maxlength=\"2000\" data-day-description placeholder=\"e.g. Check-in, local lunch, sunset viewpoint, and welcome dinner.\"></textarea></div>" +
            "<div class=\"trip-form-grid trip-form-grid-2\">" +
            "  <div class=\"form-field\"><label>Stay</label><input class=\"form-input\" type=\"text\" maxlength=\"180\" data-day-stay placeholder=\"e.g. Lakeside resort\"></div>" +
            "  <div class=\"form-field\"><label>Meals</label><input class=\"form-input\" type=\"text\" maxlength=\"180\" data-day-meals placeholder=\"e.g. Breakfast, Dinner\"></div>" +
            "</div>";

        var flexible = row.querySelector("[data-day-flexible]");
        if (flexible) {
            flexible.checked = !!dayValue.is_flexible;
            flexible.addEventListener("change", function onChange() {
                syncDayBuilder(root);
            });
        }

        [
            ["[data-day-title]", "title"],
            ["[data-day-description]", "description"],
            ["[data-day-stay]", "stay"],
            ["[data-day-meals]", "meals"]
        ].forEach(function bindField(pair) {
            var field = row.querySelector(pair[0]);
            if (!field) {
                return;
            }
            field.value = String(dayValue[pair[1]] || "");
            field.addEventListener("input", function onInput() {
                syncDayBuilder(root);
            });
        });

        row.appendChild(
            rowButton("Remove Day", function onRemove() {
                row.remove();
                syncDayBuilder(root);
            })
        );
        return row;
    }

    function initDayBuilder(root) {
        var inputId = root.getAttribute("data-target-input-id");
        var hiddenInput = inputId ? document.getElementById(inputId) : null;
        var itemsHost = root.querySelector("[data-day-items]");
        var addButton = root.querySelector("[data-day-add]");
        if (!hiddenInput || !itemsHost || !addButton) {
            return;
        }

        var initialDays = parseJson(hiddenInput.value, []);
        if (!Array.isArray(initialDays) || initialDays.length === 0) {
            itemsHost.appendChild(createDayRow(root, {}));
        } else {
            initialDays.forEach(function eachDay(day) {
                itemsHost.appendChild(createDayRow(root, day));
            });
        }

        addButton.addEventListener("click", function onAddDay() {
            itemsHost.appendChild(createDayRow(root, {}));
            syncDayBuilder(root);
        });

        syncDayBuilder(root);
    }

    function syncFaqBuilder(root) {
        var inputId = root.getAttribute("data-target-input-id");
        var hiddenInput = inputId ? document.getElementById(inputId) : null;
        if (!hiddenInput) {
            return;
        }

        var faqs = Array.prototype.slice.call(root.querySelectorAll("[data-faq-row]"))
            .map(function mapRow(row) {
                return {
                    question: String(((row.querySelector("[data-faq-question]") || {}).value || "")).trim(),
                    answer: String(((row.querySelector("[data-faq-answer]") || {}).value || "")).trim()
                };
            })
            .filter(function nonEmpty(faq) {
                return faq.question || faq.answer;
            });

        hiddenInput.value = JSON.stringify(faqs);
        requestProgressRefresh(root);
    }

    function createFaqRow(root, value) {
        var faqValue = value && typeof value === "object" ? value : {};
        var row = document.createElement("div");
        row.className = "dynamic-faq-row";
        row.setAttribute("data-faq-row", "1");
        row.innerHTML = "" +
            "<div class=\"form-field\"><label>Question</label><input class=\"form-input\" type=\"text\" maxlength=\"280\" data-faq-question placeholder=\"e.g. Is airport pickup included?\"></div>" +
            "<div class=\"form-field\"><label>Answer</label><textarea class=\"form-input\" rows=\"3\" maxlength=\"2000\" data-faq-answer placeholder=\"e.g. Pickup is optional and can be arranged at extra cost.\"></textarea></div>";

        var question = row.querySelector("[data-faq-question]");
        var answer = row.querySelector("[data-faq-answer]");
        if (question) {
            question.value = String(faqValue.question || "");
            question.addEventListener("input", function onInput() {
                syncFaqBuilder(root);
            });
        }
        if (answer) {
            answer.value = String(faqValue.answer || "");
            answer.addEventListener("input", function onInput() {
                syncFaqBuilder(root);
            });
        }

        row.appendChild(
            rowButton("Remove FAQ", function onRemove() {
                row.remove();
                syncFaqBuilder(root);
            })
        );
        return row;
    }

    function initFaqBuilder(root) {
        var inputId = root.getAttribute("data-target-input-id");
        var hiddenInput = inputId ? document.getElementById(inputId) : null;
        var itemsHost = root.querySelector("[data-faq-items]");
        var addButton = root.querySelector("[data-faq-add]");
        if (!hiddenInput || !itemsHost || !addButton) {
            return;
        }

        var initialFaqs = parseJson(hiddenInput.value, []);
        if (!Array.isArray(initialFaqs) || initialFaqs.length === 0) {
            itemsHost.appendChild(createFaqRow(root, {}));
        } else {
            initialFaqs.forEach(function eachFaq(faq) {
                itemsHost.appendChild(createFaqRow(root, faq));
            });
        }

        addButton.addEventListener("click", function onAddFaq() {
            itemsHost.appendChild(createFaqRow(root, {}));
            syncFaqBuilder(root);
        });

        syncFaqBuilder(root);
    }

    function syncPillBuilder(root) {
        var inputId = root.getAttribute("data-target-input-id");
        var hiddenInput = inputId ? document.getElementById(inputId) : null;
        if (!hiddenInput) {
            return;
        }

        var values = Array.prototype.slice.call(root.querySelectorAll("[data-pill-item]"))
            .map(function mapPill(item) {
                return String(item.getAttribute("data-pill-value") || "").trim();
            })
            .filter(function nonEmpty(value) {
                return value.length > 0;
            });

        hiddenInput.value = JSON.stringify(values);

        var proxyInput = root.querySelector("[data-pill-progress-proxy]");
        if (proxyInput) {
            proxyInput.value = values.join(", ");
        }
        requestProgressRefresh(root);
    }

    function createPillItem(root, value) {
        var normalized = String(value || "").trim();
        if (!normalized) {
            return null;
        }

        var pill = document.createElement("span");
        pill.className = "pill-item";
        pill.setAttribute("data-pill-item", "1");
        pill.setAttribute("data-pill-value", normalized);

        var label = document.createElement("span");
        label.className = "pill-item-label";
        label.textContent = normalized;

        var removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "pill-item-remove";
        removeButton.setAttribute("aria-label", "Remove " + normalized);
        removeButton.textContent = "×";
        removeButton.addEventListener("click", function onRemove() {
            pill.remove();
            syncPillBuilder(root);
        });

        pill.appendChild(label);
        pill.appendChild(removeButton);
        return pill;
    }

    function initPillBuilder(root) {
        var inputId = root.getAttribute("data-target-input-id");
        var hiddenInput = inputId ? document.getElementById(inputId) : null;
        var itemsHost = root.querySelector("[data-pill-items]");
        var textInput = root.querySelector("[data-pill-input]");
        var frame = root.querySelector("[data-pill-frame]");
        if (!hiddenInput || !itemsHost || !textInput) {
            return;
        }

        var initialItems = parseJson(hiddenInput.value, []);
        if (Array.isArray(initialItems)) {
            initialItems.forEach(function eachItem(item) {
                var pill = createPillItem(root, item);
                if (pill) {
                    itemsHost.appendChild(pill);
                }
            });
        }

        function normalizedValue(rawValue) {
            var value = String(rawValue || "")
                .replace(/\s+/g, " ")
                .trim();
            return value.slice(0, 280);
        }

        function existingValuesLower() {
            return Array.prototype.slice.call(itemsHost.querySelectorAll("[data-pill-item]")).map(function mapItem(item) {
                return String(item.getAttribute("data-pill-value") || "").trim().toLowerCase();
            });
        }

        function addPill(rawValue) {
            var value = normalizedValue(rawValue);
            if (!value) {
                return false;
            }
            if (existingValuesLower().indexOf(value.toLowerCase()) >= 0) {
                return false;
            }
            var pill = createPillItem(root, value);
            if (!pill) {
                return false;
            }
            itemsHost.appendChild(pill);
            syncPillBuilder(root);
            return true;
        }

        function flushInputToPill() {
            var didAdd = addPill(textInput.value);
            textInput.value = "";
            requestProgressRefresh(root);
            return didAdd;
        }

        textInput.addEventListener("keydown", function onPillInputKeydown(event) {
            if (event.key === "Enter" || event.key === ",") {
                event.preventDefault();
                flushInputToPill();
                return;
            }
            if (event.key === "Backspace" && !String(textInput.value || "").trim()) {
                var pills = itemsHost.querySelectorAll("[data-pill-item]");
                var lastPill = pills.length ? pills[pills.length - 1] : null;
                if (lastPill) {
                    lastPill.remove();
                    syncPillBuilder(root);
                }
            }
        });

        textInput.addEventListener("blur", function onPillInputBlur() {
            if (String(textInput.value || "").trim()) {
                flushInputToPill();
            }
        });

        textInput.addEventListener("paste", function onPillInputPaste(event) {
            var clipboardText = String(((event.clipboardData || {}).getData && event.clipboardData.getData("text")) || "");
            if (!clipboardText || (clipboardText.indexOf(",") < 0 && clipboardText.indexOf("\n") < 0)) {
                return;
            }
            event.preventDefault();
            clipboardText.split(/[\n,]+/).forEach(function eachChunk(chunk) {
                addPill(chunk);
            });
            textInput.value = "";
            syncPillBuilder(root);
        });

        textInput.addEventListener("input", function onPillInput() {
            requestProgressRefresh(root);
        });

        if (frame) {
            frame.addEventListener("click", function onFrameClick(event) {
                var target = event.target;
                if (target && target.closest && target.closest(".pill-item-remove")) {
                    return;
                }
                textInput.focus();
            });
        }

        syncPillBuilder(root);
    }

    function initChoiceLimitGroups(form) {
        Array.prototype.slice.call(form.querySelectorAll("[data-choice-limit-group]")).forEach(function eachGroup(group) {
            var limit = Number(group.getAttribute("data-choice-limit") || "0");
            if (!limit || limit < 1) {
                return;
            }

            var checkboxes = Array.prototype.slice.call(group.querySelectorAll("input[type='checkbox']"));
            if (checkboxes.length === 0) {
                return;
            }

            function checkedCount() {
                return checkboxes.filter(function isChecked(input) {
                    return !!input.checked;
                }).length;
            }

            function syncDisabledState() {
                var atLimit = checkedCount() >= limit;
                checkboxes.forEach(function eachCheckbox(input) {
                    if (!input.checked) {
                        input.disabled = atLimit;
                    } else {
                        input.disabled = false;
                    }
                });
                group.classList.toggle("is-at-limit", atLimit);
            }

            checkboxes.forEach(function bindCheckbox(input) {
                input.addEventListener("change", function onCheckboxChange() {
                    syncDisabledState();
                    requestProgressRefresh(group);
                });
            });

            syncDisabledState();
        });
    }

    function initAgePreferenceSliders(form) {
        Array.prototype.slice.call(form.querySelectorAll("[data-age-pref-slider]")).forEach(function eachSlider(root) {
            var inputId = root.getAttribute("data-target-input-id");
            var hiddenInput = inputId ? document.getElementById(inputId) : null;
            var parentSection = root.closest ? root.closest(".trip-form-section") : null;
            var shell = root.querySelector("[data-age-pref-shell]");
            var track = root.querySelector("[data-age-pref-track]");
            var fill = root.querySelector("[data-age-pref-fill]");
            var minThumb = root.querySelector("[data-age-pref-thumb='min']");
            var maxThumb = root.querySelector("[data-age-pref-thumb='max']");
            var label = root.querySelector("[data-age-pref-label]");
            var minValueText = root.querySelector("[data-age-pref-min-value]");
            var maxValueText = root.querySelector("[data-age-pref-max-value]");
            if (!hiddenInput || !shell || !track || !fill || !minThumb || !maxThumb) {
                return;
            }

            var minBound = Number(root.getAttribute("data-age-min") || "18");
            var maxBound = Number(root.getAttribute("data-age-max") || "70");
            if (!isFinite(minBound) || !isFinite(maxBound) || maxBound <= minBound) {
                minBound = 18;
                maxBound = 70;
            }

            var state = {
                minAge: minBound,
                maxAge: maxBound,
                dragKind: null
            };
            var pendingLayoutRaf = 0;

            function clampAge(value) {
                return Math.max(minBound, Math.min(maxBound, Math.round(value)));
            }

            function percentForAge(age) {
                var span = Math.max(1, maxBound - minBound);
                return ((age - minBound) / span) * 100;
            }

            function parseInitialRange() {
                var raw = String(hiddenInput.value || "").trim();
                var serverRenderedRaw = String(hiddenInput.defaultValue || "").trim();
                var matches = raw.match(/(\d{1,3})\D+(\d{1,3})/);
                var serverMatches = serverRenderedRaw.match(/(\d{1,3})\D+(\d{1,3})/);
                if (!matches) {
                    if (serverMatches) {
                        var fallbackServerMin = clampAge(Number(serverMatches[1] || minBound));
                        var fallbackServerMax = clampAge(Number(serverMatches[2] || maxBound));
                        state.minAge = Math.min(fallbackServerMin, fallbackServerMax);
                        state.maxAge = Math.max(fallbackServerMin, fallbackServerMax);
                    }
                    return;
                }
                var parsedMin = clampAge(Number(matches[1] || minBound));
                var parsedMax = clampAge(Number(matches[2] || maxBound));
                if (serverMatches) {
                    var serverMin = clampAge(Number(serverMatches[1] || minBound));
                    var serverMax = clampAge(Number(serverMatches[2] || maxBound));
                    if (
                        parsedMin === minBound &&
                        parsedMax === minBound &&
                        !(serverMin === minBound && serverMax === minBound)
                    ) {
                        state.minAge = Math.min(serverMin, serverMax);
                        state.maxAge = Math.max(serverMin, serverMax);
                        return;
                    }
                } else if (parsedMin === minBound && parsedMax === minBound) {
                    state.minAge = minBound;
                    state.maxAge = maxBound;
                    return;
                }
                state.minAge = Math.min(parsedMin, parsedMax);
                state.maxAge = Math.max(parsedMin, parsedMax);
            }

            function setActiveThumb(kind) {
                root.classList.toggle("is-min-active", kind === "min");
                root.classList.toggle("is-max-active", kind === "max");
            }

            function setDragging(isDragging) {
                root.classList.toggle("is-dragging", !!isDragging);
            }

            function getTrackMetrics() {
                var shellRect = shell.getBoundingClientRect();
                var trackRect = track.getBoundingClientRect();
                return {
                    startPx: trackRect.left - shellRect.left,
                    widthPx: trackRect.width
                };
            }

            function syncOutput() {
                hiddenInput.value = String(state.minAge) + "-" + String(state.maxAge);
                if (label) {
                    label.textContent = String(state.minAge) + "-" + String(state.maxAge);
                }
                if (minValueText) {
                    minValueText.textContent = String(state.minAge);
                }
                if (maxValueText) {
                    maxValueText.textContent = String(state.maxAge);
                }
                minThumb.setAttribute("aria-valuemin", String(minBound));
                minThumb.setAttribute("aria-valuemax", String(state.maxAge));
                minThumb.setAttribute("aria-valuenow", String(state.minAge));
                maxThumb.setAttribute("aria-valuemin", String(state.minAge));
                maxThumb.setAttribute("aria-valuemax", String(maxBound));
                maxThumb.setAttribute("aria-valuenow", String(state.maxAge));
            }

            function render() {
                state.minAge = clampAge(state.minAge);
                state.maxAge = clampAge(state.maxAge);
                if (state.minAge > state.maxAge) {
                    state.minAge = state.maxAge;
                }
                if (state.maxAge < state.minAge) {
                    state.maxAge = state.minAge;
                }

                var minPercent = percentForAge(state.minAge);
                var maxPercent = percentForAge(state.maxAge);
                fill.style.left = String(minPercent) + "%";
                fill.style.width = String(Math.max(0, maxPercent - minPercent)) + "%";

                var metrics = getTrackMetrics();
                if (metrics.widthPx <= 1) {
                    syncOutput();
                    requestProgressRefresh(root);
                    return;
                }

                var usableWidth = metrics.widthPx;
                var minLeftPx = metrics.startPx + (usableWidth * minPercent) / 100;
                var maxLeftPx = metrics.startPx + (usableWidth * maxPercent) / 100;
                minThumb.style.left = String(minLeftPx) + "px";
                maxThumb.style.left = String(maxLeftPx) + "px";

                syncOutput();
                requestProgressRefresh(root);
            }

            function cancelPendingLayoutRender() {
                if (!pendingLayoutRaf) {
                    return;
                }
                window.cancelAnimationFrame(pendingLayoutRaf);
                pendingLayoutRaf = 0;
            }

            function renderWhenLaidOut(maxAttempts) {
                var attemptsLeft = typeof maxAttempts === "number" ? maxAttempts : 12;
                cancelPendingLayoutRender();

                function tryRender() {
                    pendingLayoutRaf = 0;
                    var width = track.getBoundingClientRect().width;
                    if (width > 1) {
                        render();
                        return;
                    }
                    if (attemptsLeft <= 0) {
                        render();
                        return;
                    }
                    attemptsLeft -= 1;
                    pendingLayoutRaf = window.requestAnimationFrame(tryRender);
                }

                pendingLayoutRaf = window.requestAnimationFrame(tryRender);
            }

            function ageFromClientX(clientX) {
                var rect = track.getBoundingClientRect();
                if (!rect.width) {
                    return null;
                }
                var boundedX = Math.max(rect.left, Math.min(rect.right, clientX));
                var ratio = (boundedX - rect.left) / rect.width;
                var raw = minBound + ratio * (maxBound - minBound);
                return clampAge(raw);
            }

            function chooseClosestThumb(clientX) {
                var targetAge = ageFromClientX(clientX);
                if (targetAge === null) {
                    return "min";
                }
                return Math.abs(targetAge - state.minAge) <= Math.abs(targetAge - state.maxAge) ? "min" : "max";
            }

            function updateFromPointer(clientX) {
                var nextAge = ageFromClientX(clientX);
                if (nextAge === null) {
                    return;
                }
                if (state.dragKind === "min") {
                    state.minAge = Math.min(nextAge, state.maxAge);
                } else if (state.dragKind === "max") {
                    state.maxAge = Math.max(nextAge, state.minAge);
                }
                render();
            }

            function onPointerMove(event) {
                if (!state.dragKind) {
                    return;
                }
                updateFromPointer(event.clientX);
            }

            function stopDrag() {
                if (!state.dragKind) {
                    return;
                }
                state.dragKind = null;
                setDragging(false);
                window.removeEventListener("pointermove", onPointerMove);
                window.removeEventListener("pointerup", onPointerUp);
                window.removeEventListener("pointercancel", onPointerUp);
            }

            function onPointerUp() {
                stopDrag();
            }

            function startDrag(kind, event, jumpToPointer) {
                event.preventDefault();
                state.dragKind = kind;
                setActiveThumb(kind);
                setDragging(true);
                renderWhenLaidOut(4);
                if (jumpToPointer) {
                    updateFromPointer(event.clientX);
                }
                window.addEventListener("pointermove", onPointerMove);
                window.addEventListener("pointerup", onPointerUp);
                window.addEventListener("pointercancel", onPointerUp);
            }

            shell.addEventListener("pointerdown", function onShellPointerDown(event) {
                if (event.target === minThumb || event.target === maxThumb) {
                    return;
                }
                renderWhenLaidOut(4);
                startDrag(chooseClosestThumb(event.clientX), event, true);
            });

            minThumb.addEventListener("pointerdown", function onMinPointerDown(event) {
                event.stopPropagation();
                startDrag("min", event, false);
            });

            maxThumb.addEventListener("pointerdown", function onMaxPointerDown(event) {
                event.stopPropagation();
                startDrag("max", event, false);
            });

            minThumb.addEventListener("focus", function onMinFocus() {
                setActiveThumb("min");
            });

            maxThumb.addEventListener("focus", function onMaxFocus() {
                setActiveThumb("max");
            });

            function handleKeyboard(kind, event) {
                var delta = 0;
                if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
                    delta = -1;
                } else if (event.key === "ArrowRight" || event.key === "ArrowUp") {
                    delta = 1;
                } else if (event.key === "PageDown") {
                    delta = -5;
                } else if (event.key === "PageUp") {
                    delta = 5;
                } else if (event.key === "Home") {
                    event.preventDefault();
                    setActiveThumb(kind);
                    if (kind === "min") {
                        state.minAge = minBound;
                    } else {
                        state.maxAge = state.minAge;
                    }
                    render();
                    return;
                } else if (event.key === "End") {
                    event.preventDefault();
                    setActiveThumb(kind);
                    if (kind === "max") {
                        state.maxAge = maxBound;
                    } else {
                        state.minAge = state.maxAge;
                    }
                    render();
                    return;
                } else {
                    return;
                }

                event.preventDefault();
                setActiveThumb(kind);
                if (kind === "min") {
                    state.minAge = Math.min(state.maxAge, state.minAge + delta);
                } else {
                    state.maxAge = Math.max(state.minAge, state.maxAge + delta);
                }
                render();
            }

            minThumb.addEventListener("keydown", function onMinKeydown(event) {
                handleKeyboard("min", event);
            });

            maxThumb.addEventListener("keydown", function onMaxKeydown(event) {
                handleKeyboard("max", event);
            });

            window.addEventListener("resize", function onAgeSliderResize() {
                renderWhenLaidOut(8);
            });

            if (parentSection) {
                parentSection.addEventListener("trip-section-visibility-changed", function onSectionVisibilityChanged(event) {
                    var detail = event && event.detail ? event.detail : null;
                    if (detail && detail.collapsed) {
                        return;
                    }
                    renderWhenLaidOut(18);
                });
            }

            parseInitialRange();
            renderWhenLaidOut(18);
        });
    }

    function initDestinationPicker(form) {
        var picker = form.querySelector("[data-destination-picker]");
        if (!picker) {
            return;
        }

        var targetInputId = String(picker.getAttribute("data-target-input-id") || "").trim();
        var destinationInput = targetInputId ? document.getElementById(targetInputId) : null;
        if (!destinationInput) {
            destinationInput = picker.querySelector("[data-destination-input]");
        }
        if (!destinationInput) {
            return;
        }

        var autocompleteUrl = String(picker.getAttribute("data-autocomplete-url") || "").trim();
        var detailsUrl = String(picker.getAttribute("data-details-url") || "").trim();
        var statusNode = picker.querySelector("[data-destination-status]");
        var suggestionsHost = picker.querySelector("[data-destination-suggestions]");
        var mapToggle = picker.querySelector("[data-destination-map-toggle]");
        var mapShell = picker.querySelector("[data-destination-map-shell]");
        var mapFrame = picker.querySelector("[data-destination-map]");
        var placeIdInput = picker.querySelector("[data-destination-place-id]");
        var latitudeInput = picker.querySelector("[data-destination-latitude]");
        var longitudeInput = picker.querySelector("[data-destination-longitude]");

        var selectedPlaceId = "";
        var selectedLabel = "";
        var selectedLatitude = null;
        var selectedLongitude = null;
        var selectedViewport = null;
        var pendingAutocompleteTimer = 0;
        var latestAutocompleteRequestId = 0;
        var currentPredictions = [];
        var activeSuggestionIndex = -1;
        var sessionToken = "";
        var blurTimer = 0;
        var isProgrammaticDestinationUpdate = false;

        function createSessionToken() {
            if (window.crypto && typeof window.crypto.randomUUID === "function") {
                return window.crypto.randomUUID();
            }
            return "sess-" + String(Date.now()) + "-" + Math.random().toString(36).slice(2, 12);
        }

        function parseFiniteNumber(rawValue) {
            var parsed = Number(rawValue);
            if (!isFinite(parsed)) {
                return null;
            }
            return parsed;
        }

        function setStatus(text, tone) {
            if (!statusNode) {
                return;
            }
            statusNode.textContent = String(text || "");
            statusNode.classList.remove("is-muted", "is-success", "is-error");
            if (tone === "success") {
                statusNode.classList.add("is-success");
                return;
            }
            if (tone === "error") {
                statusNode.classList.add("is-error");
                return;
            }
            statusNode.classList.add("is-muted");
        }

        function setMapToggleState(isEnabled, titleText) {
            if (!mapToggle) {
                return;
            }
            mapToggle.disabled = !isEnabled;
            mapToggle.setAttribute("aria-disabled", mapToggle.disabled ? "true" : "false");
            if (titleText) {
                mapToggle.title = titleText;
                return;
            }
            mapToggle.removeAttribute("title");
        }

        function hideMapPreview() {
            if (mapShell) {
                mapShell.hidden = true;
            }
            if (mapFrame) {
                mapFrame.removeAttribute("src");
            }
            if (mapToggle) {
                mapToggle.textContent = "Load map preview";
            }
        }

        function hideSuggestions() {
            if (!suggestionsHost) {
                return;
            }
            suggestionsHost.hidden = true;
            suggestionsHost.innerHTML = "";
            currentPredictions = [];
            activeSuggestionIndex = -1;
        }

        function formatCoordinate(value) {
            var numeric = parseFiniteNumber(value);
            if (numeric === null) {
                return "";
            }
            return String(numeric.toFixed(6));
        }

        function applyHiddenCoordinates(latitude, longitude) {
            if (latitudeInput) {
                latitudeInput.value = formatCoordinate(latitude);
            }
            if (longitudeInput) {
                longitudeInput.value = formatCoordinate(longitude);
            }
        }

        function syncPlaceId(placeId) {
            if (!placeIdInput) {
                return;
            }
            placeIdInput.value = String(placeId || "").trim();
        }

        function clearPlaceMetadata() {
            selectedPlaceId = "";
            selectedLabel = "";
            selectedLatitude = null;
            selectedLongitude = null;
            selectedViewport = null;
            syncPlaceId("");
            applyHiddenCoordinates("", "");
            setMapToggleState(false, "");
            hideMapPreview();
            requestProgressRefresh(picker);
        }

        function debounceAutocomplete(callback, delayMs) {
            if (pendingAutocompleteTimer) {
                window.clearTimeout(pendingAutocompleteTimer);
            }
            pendingAutocompleteTimer = window.setTimeout(callback, delayMs);
        }

        function updateSuggestionActiveState() {
            if (!suggestionsHost) {
                return;
            }
            Array.prototype.slice.call(suggestionsHost.querySelectorAll("[data-destination-prediction]")).forEach(function eachItem(item, index) {
                item.classList.toggle("is-active", index === activeSuggestionIndex);
            });
        }

        function applyPlaceDetails(place) {
            selectedPlaceId = String(place.place_id || selectedPlaceId || "").trim();
            selectedLabel = String(place.label || selectedLabel || destinationInput.value || "").trim();
            selectedLatitude = parseFiniteNumber(place.latitude);
            selectedLongitude = parseFiniteNumber(place.longitude);
            selectedViewport = place.viewport && typeof place.viewport === "object" ? place.viewport : null;

            syncPlaceId(selectedPlaceId);
            applyHiddenCoordinates(selectedLatitude, selectedLongitude);

            if (selectedLabel && destinationInput.value !== selectedLabel) {
                isProgrammaticDestinationUpdate = true;
                destinationInput.value = selectedLabel;
                destinationInput.dispatchEvent(new Event("input", { bubbles: true }));
                destinationInput.dispatchEvent(new Event("change", { bubbles: true }));
                isProgrammaticDestinationUpdate = false;
            }

            if (selectedLatitude === null || selectedLongitude === null) {
                setMapToggleState(false, "Coordinates are unavailable for this destination.");
                setStatus("Destination locked, but map preview is unavailable for this place.", "muted");
                requestProgressRefresh(picker);
                return;
            }

            setMapToggleState(true, "");
            setStatus("Destination locked. Map preview is ready on demand.", "success");
            requestProgressRefresh(picker);
        }

        function selectPrediction(prediction) {
            if (!prediction || typeof prediction !== "object") {
                return;
            }
            selectedPlaceId = String(prediction.place_id || "").trim();
            selectedLabel = String(prediction.label || "").trim();
            if (!selectedPlaceId || !selectedLabel) {
                return;
            }

            isProgrammaticDestinationUpdate = true;
            destinationInput.value = selectedLabel;
            destinationInput.dispatchEvent(new Event("input", { bubbles: true }));
            destinationInput.dispatchEvent(new Event("change", { bubbles: true }));
            isProgrammaticDestinationUpdate = false;

            syncPlaceId(selectedPlaceId);
            applyHiddenCoordinates("", "");
            selectedLatitude = null;
            selectedLongitude = null;
            selectedViewport = null;
            hideMapPreview();
            setMapToggleState(false, "Fetching coordinates for this destination.");
            hideSuggestions();
            setStatus("Fetching exact coordinates...", "muted");
            requestProgressRefresh(picker);

            fetch(
                detailsUrl + "?" + new URLSearchParams({
                    place_id: selectedPlaceId,
                    session_token: sessionToken
                }).toString(),
                {
                    method: "GET",
                    credentials: "same-origin",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json"
                    }
                }
            ).then(function onDetailsResponse(response) {
                if (response.status === 429) {
                    throw new Error("rate-limited");
                }
                if (!response.ok) {
                    throw new Error("details-unavailable");
                }
                return response.json();
            }).then(function onDetailsPayload(payload) {
                var place = payload && payload.place && typeof payload.place === "object" ? payload.place : null;
                if (!place) {
                    throw new Error("details-empty");
                }
                applyPlaceDetails(place);
            }).catch(function onDetailsError(error) {
                clearPlaceMetadata();
                if (error && error.message === "rate-limited") {
                    setStatus("Rate limit reached for destination lookups. Try again in a minute.", "error");
                    return;
                }
                setStatus("Could not fetch destination coordinates. You can still submit manually.", "error");
            });
        }

        function renderSuggestions(predictions) {
            if (!suggestionsHost) {
                return;
            }
            var items = Array.isArray(predictions) ? predictions : [];
            currentPredictions = items;
            activeSuggestionIndex = items.length > 0 ? 0 : -1;
            suggestionsHost.innerHTML = "";
            if (items.length === 0) {
                suggestionsHost.hidden = true;
                return;
            }

            var list = document.createElement("div");
            list.className = "trip-destination-suggestion-list";
            items.forEach(function eachPrediction(item) {
                var button = document.createElement("button");
                button.type = "button";
                button.className = "trip-destination-prediction";
                button.setAttribute("data-destination-prediction", "1");
                button.setAttribute("aria-label", String(item.label || ""));
                button.addEventListener("mousedown", function onPredictionMouseDown(event) {
                    event.preventDefault();
                });
                button.addEventListener("click", function onPredictionClick() {
                    selectPrediction(item);
                });

                var main = document.createElement("span");
                main.className = "trip-destination-prediction-main";
                main.textContent = String(item.main_text || item.label || "");
                button.appendChild(main);

                var secondaryLabel = String(item.secondary_text || "").trim();
                if (secondaryLabel) {
                    var secondary = document.createElement("span");
                    secondary.className = "trip-destination-prediction-secondary";
                    secondary.textContent = secondaryLabel;
                    button.appendChild(secondary);
                }

                list.appendChild(button);
            });
            suggestionsHost.appendChild(list);
            suggestionsHost.hidden = false;
            updateSuggestionActiveState();
        }

        function requestPredictions(query) {
            latestAutocompleteRequestId += 1;
            var requestId = latestAutocompleteRequestId;
            fetch(
                autocompleteUrl + "?" + new URLSearchParams({
                    q: query,
                    session_token: sessionToken
                }).toString(),
                {
                    method: "GET",
                    credentials: "same-origin",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json"
                    }
                }
            ).then(function onAutocompleteResponse(response) {
                if (response.status === 429) {
                    throw new Error("rate-limited");
                }
                if (!response.ok) {
                    throw new Error("autocomplete-unavailable");
                }
                return response.json();
            }).then(function onAutocompletePayload(payload) {
                if (requestId !== latestAutocompleteRequestId) {
                    return;
                }
                var predictions = payload && Array.isArray(payload.predictions) ? payload.predictions : [];
                renderSuggestions(predictions);
                if (predictions.length > 0) {
                    setStatus("Choose the matching destination suggestion.", "muted");
                } else {
                    setStatus("No suggestions found. Continue with manual destination if needed.", "muted");
                }
            }).catch(function onAutocompleteError(error) {
                if (requestId !== latestAutocompleteRequestId) {
                    return;
                }
                hideSuggestions();
                if (error && error.message === "rate-limited") {
                    setStatus("Rate limit reached for destination suggestions. Retry in a minute.", "error");
                    return;
                }
                setStatus("Destination suggestions are unavailable. You can still type manually.", "error");
            });
        }

        function buildMapEmbedUrl(latitude, longitude, viewport) {
            var lat = parseFiniteNumber(latitude);
            var lng = parseFiniteNumber(longitude);
            if (lat === null || lng === null) {
                return "";
            }

            var south = lat - 0.18;
            var north = lat + 0.18;
            var west = lng - 0.18;
            var east = lng + 0.18;

            if (viewport && typeof viewport === "object") {
                var parsedSouth = parseFiniteNumber(viewport.south);
                var parsedWest = parseFiniteNumber(viewport.west);
                var parsedNorth = parseFiniteNumber(viewport.north);
                var parsedEast = parseFiniteNumber(viewport.east);
                if (parsedSouth !== null && parsedWest !== null && parsedNorth !== null && parsedEast !== null) {
                    south = parsedSouth;
                    west = parsedWest;
                    north = parsedNorth;
                    east = parsedEast;
                }
            }

            var params = new URLSearchParams();
            params.set("bbox", [west, south, east, north].join(","));
            params.set("layer", "mapnik");
            params.set("marker", [lat, lng].join(","));
            return "https://www.openstreetmap.org/export/embed.html?" + params.toString();
        }

        function showMapPreview() {
            if (selectedLatitude === null || selectedLongitude === null || !mapFrame) {
                return false;
            }
            var mapUrl = buildMapEmbedUrl(selectedLatitude, selectedLongitude, selectedViewport);
            if (!mapUrl) {
                return false;
            }
            mapFrame.src = mapUrl;
            if (mapShell) {
                mapShell.hidden = false;
            }
            if (mapToggle) {
                mapToggle.textContent = "Hide map preview";
            }
            setStatus("Map preview loaded on demand.", "success");
            return true;
        }

        sessionToken = createSessionToken();

        destinationInput.addEventListener("input", function onDestinationInput() {
            if (isProgrammaticDestinationUpdate) {
                return;
            }
            if (blurTimer) {
                window.clearTimeout(blurTimer);
                blurTimer = 0;
            }

            var currentValue = String(destinationInput.value || "").trim();
            if (!currentValue) {
                clearPlaceMetadata();
                hideSuggestions();
                setStatus("Start typing and choose a destination suggestion.", "muted");
                return;
            }

            if (selectedLabel && currentValue !== selectedLabel) {
                clearPlaceMetadata();
            }

            if (currentValue.length < 2) {
                hideSuggestions();
                setStatus("Type at least 2 characters for destination suggestions.", "muted");
                return;
            }

            if (!autocompleteUrl || !detailsUrl) {
                hideSuggestions();
                setStatus("Destination suggestion service is not configured. Enter destination manually.", "muted");
                return;
            }

            debounceAutocomplete(function runAutocompleteRequest() {
                var liveValue = String(destinationInput.value || "").trim();
                if (liveValue.length < 2) {
                    hideSuggestions();
                    return;
                }
                requestPredictions(liveValue);
            }, 220);
        });

        destinationInput.addEventListener("focus", function onDestinationFocus() {
            var currentValue = String(destinationInput.value || "").trim();
            if (currentValue.length >= 2 && currentPredictions.length > 0 && suggestionsHost) {
                suggestionsHost.hidden = false;
            }
        });

        destinationInput.addEventListener("blur", function onDestinationBlur() {
            blurTimer = window.setTimeout(function hideSuggestionListAfterBlur() {
                hideSuggestions();
            }, 120);
        });

        destinationInput.addEventListener("keydown", function onDestinationKeydown(event) {
            if (currentPredictions.length === 0) {
                return;
            }
            if (event.key === "ArrowDown") {
                event.preventDefault();
                activeSuggestionIndex = Math.min(currentPredictions.length - 1, activeSuggestionIndex + 1);
                updateSuggestionActiveState();
                return;
            }
            if (event.key === "ArrowUp") {
                event.preventDefault();
                activeSuggestionIndex = Math.max(0, activeSuggestionIndex - 1);
                updateSuggestionActiveState();
                return;
            }
            if (event.key === "Escape") {
                hideSuggestions();
                return;
            }
            if (event.key === "Enter") {
                if (activeSuggestionIndex < 0 || activeSuggestionIndex >= currentPredictions.length) {
                    return;
                }
                event.preventDefault();
                selectPrediction(currentPredictions[activeSuggestionIndex]);
            }
        });

        if (mapToggle) {
            mapToggle.addEventListener("click", function onMapToggleClick() {
                if (mapShell && !mapShell.hidden) {
                    hideMapPreview();
                    setStatus("Map preview hidden. It can be re-opened anytime.", "muted");
                    return;
                }

                if (selectedLatitude === null || selectedLongitude === null) {
                    setStatus("Pick a destination suggestion first, then load map preview.", "muted");
                    destinationInput.focus();
                    return;
                }
                if (!showMapPreview()) {
                    setStatus("Map preview failed to load. Destination text is still saved.", "error");
                }
            });
        }

        picker.addEventListener("click", function onPickerClick(event) {
            var target = event.target;
            if (!target || !target.closest) {
                return;
            }
            if (target.closest("[data-destination-prediction]")) {
                return;
            }
            if (target.closest(".trip-destination-suggestions")) {
                return;
            }
            if (target === destinationInput) {
                return;
            }
            hideSuggestions();
        });

        setMapToggleState(false, "");
        if (String(destinationInput.value || "").trim()) {
            setStatus("Select the matching suggestion to pin an exact destination.", "muted");
        } else {
            setStatus("Start typing and choose a destination suggestion.", "muted");
        }
    }
    function initSectionIndex(form) {
        var layout = form.parentElement;
        var indexHost = layout ? layout.querySelector("[data-trip-section-index]") : null;
        if (!indexHost) {
            return;
        }

        var sections = Array.prototype.slice.call(form.querySelectorAll(".trip-form-section"));
        if (sections.length === 0) {
            return;
        }

        var indexList = document.createElement("ul");
        indexList.className = "trip-form-index-list";
        var sectionLinkPairs = [];

        sections.forEach(function eachSection(section, index) {
            var sectionId = String(section.id || "").trim();
            if (!sectionId) {
                sectionId = "trip-section-" + String(index + 1);
                while (document.getElementById(sectionId)) {
                    sectionId = sectionId + "-x";
                }
                section.id = sectionId;
            }

            var sectionLabel = String(section.getAttribute("data-index-label") || "").trim();
            if (!sectionLabel) {
                var heading = section.querySelector(".trip-form-section-header h2");
                sectionLabel = heading ? String(heading.textContent || "").trim() : "";
            }
            if (!sectionLabel) {
                sectionLabel = "Section " + String(index + 1);
            }

            var sectionLogo = "";
            var sectionLogoMarkup = "";
            var logoHost = section.querySelector(".trip-form-section-header .section-logo");
            if (logoHost) {
                sectionLogo = String(logoHost.textContent || "").trim();
                var logoSvg = logoHost.querySelector("svg");
                if (logoSvg && logoSvg.outerHTML) {
                    sectionLogoMarkup = String(logoSvg.outerHTML);
                }
            }

            var item = document.createElement("li");
            var link = document.createElement("a");
            link.className = "trip-form-index-link";
            link.href = "#" + sectionId;
            if (sectionLogoMarkup || sectionLogo) {
                var logo = document.createElement("span");
                logo.className = "trip-form-index-logo";
                logo.setAttribute("aria-hidden", "true");
                if (sectionLogoMarkup) {
                    logo.innerHTML = sectionLogoMarkup;
                } else {
                    logo.textContent = sectionLogo;
                }
                link.appendChild(logo);
            }
            var text = document.createElement("span");
            text.className = "trip-form-index-link-text";
            text.textContent = sectionLabel;
            link.appendChild(text);
            link.addEventListener("click", function onIndexClick(event) {
                event.preventDefault();
                if (typeof section.__tripSetCollapsed === "function") {
                    section.__tripSetCollapsed(false);
                }
                section.scrollIntoView({ behavior: "smooth", block: "start" });
                if (window.history && typeof window.history.replaceState === "function") {
                    window.history.replaceState(null, "", "#" + sectionId);
                }
                markActive(section);
            });

            item.appendChild(link);
            indexList.appendChild(item);
            sectionLinkPairs.push({ section: section, link: link });
        });

        indexHost.innerHTML = "";
        indexHost.appendChild(indexList);

        function markActive(activeSection) {
            sectionLinkPairs.forEach(function eachPair(pair) {
                pair.link.classList.toggle("is-active", pair.section === activeSection);
            });
        }

        function activeSectionFromViewport() {
            var anchorLine = window.innerHeight * 0.28;
            var active = sections[0];
            sections.forEach(function eachSectionPosition(section) {
                if (section.getBoundingClientRect().top <= anchorLine) {
                    active = section;
                }
            });
            return active;
        }

        var rafToken = null;
        function requestActiveUpdate() {
            if (rafToken !== null) {
                return;
            }
            rafToken = window.requestAnimationFrame(function runActiveUpdate() {
                rafToken = null;
                markActive(activeSectionFromViewport());
            });
        }

        window.addEventListener("scroll", requestActiveUpdate, { passive: true });
        window.addEventListener("resize", requestActiveUpdate);

        var initialHash = String(window.location.hash || "").replace(/^#/, "");
        var initialSection = initialHash ? document.getElementById(initialHash) : null;
        if (initialSection && sections.indexOf(initialSection) >= 0) {
            if (typeof initialSection.__tripSetCollapsed === "function") {
                initialSection.__tripSetCollapsed(false);
            }
            markActive(initialSection);
            return;
        }

        markActive(activeSectionFromViewport());
    }

    function initTripProgress(form) {
        var progressShell = document.querySelector("[data-trip-progress-shell]");
        if (!progressShell) {
            return;
        }

        var progressTrack = progressShell.querySelector("[data-trip-progress-track]");
        var progressFill = progressShell.querySelector("[data-trip-progress-fill]");
        var progressPercent = progressShell.querySelector("[data-trip-progress-percent]");
        var progressSections = progressShell.querySelector("[data-trip-progress-sections]");
        var sections = Array.prototype.slice.call(form.querySelectorAll(".trip-form-section"));
        if (!progressTrack || !progressFill || !progressPercent || !progressSections || sections.length === 0) {
            return;
        }

        function isTrackableControl(control) {
            if (!control || control.disabled) {
                return false;
            }
            if (control.hasAttribute && control.hasAttribute("data-progress-ignore")) {
                return false;
            }
            var type = String(control.type || "").toLowerCase();
            return !(
                type === "hidden" ||
                type === "button" ||
                type === "submit" ||
                type === "reset" ||
                type === "image"
            );
        }

        function controlHasValue(control) {
            var tag = String(control.tagName || "").toLowerCase();
            var type = String(control.type || "").toLowerCase();
            if (type === "checkbox" || type === "radio") {
                return !!control.checked;
            }
            if (type === "file") {
                return !!(control.files && control.files.length > 0);
            }
            if (tag === "select") {
                if (control.multiple && control.options) {
                    return Array.prototype.slice.call(control.options).some(function hasSelected(option) {
                        return option.selected && String(option.value || "").trim() !== "";
                    });
                }
                return String(control.value || "").trim() !== "";
            }
            return String(control.value || "").trim() !== "";
        }

        function sectionIsComplete(section) {
            var controls = Array.prototype.slice.call(section.querySelectorAll("input, select, textarea"))
                .filter(isTrackableControl);
            if (controls.length === 0) {
                return section.querySelectorAll("[data-pill-item]").length > 0;
            }
            var requiredControls = controls.filter(function onlyRequired(control) {
                return !!control.required;
            });
            if (requiredControls.length > 0) {
                return requiredControls.every(controlHasValue);
            }
            if (section.querySelectorAll("[data-pill-item]").length > 0) {
                return true;
            }
            return controls.some(controlHasValue);
        }

        function syncProgressTopOffset() {
            var header = document.querySelector(".site-header");
            var headerHeight = header ? Math.ceil(header.getBoundingClientRect().height) : 0;
            var topOffset = Math.max(8, headerHeight + 8);
            var progressHeight = Math.ceil(progressShell.getBoundingClientRect().height) || 0;
            document.documentElement.style.setProperty("--trip-progress-top", String(topOffset) + "px");
            document.documentElement.style.setProperty("--trip-progress-height", String(progressHeight) + "px");
        }

        function updateProgress() {
            var completedCount = sections.filter(sectionIsComplete).length;
            var totalCount = sections.length;
            var percent = Math.round((completedCount / totalCount) * 100);
            progressFill.style.width = String(percent) + "%";
            progressTrack.setAttribute("aria-valuenow", String(percent));
            progressPercent.textContent = String(percent) + "%";
            progressSections.textContent = String(completedCount) + " / " + String(totalCount) + " sections";
            syncProgressTopOffset();
        }

        var rafToken = null;
        function requestProgressUpdate() {
            if (rafToken !== null) {
                return;
            }
            rafToken = window.requestAnimationFrame(function runProgressUpdate() {
                rafToken = null;
                updateProgress();
            });
        }

        form.addEventListener("input", requestProgressUpdate);
        form.addEventListener("change", requestProgressUpdate);
        form.addEventListener("trip-progress-refresh", requestProgressUpdate);
        window.addEventListener("resize", function onResize() {
            syncProgressTopOffset();
            requestProgressUpdate();
        });

        syncProgressTopOffset();
        updateProgress();
    }

    function initCollapsibleSections(form) {
        Array.prototype.slice.call(form.querySelectorAll(".trip-form-section")).forEach(function eachSection(section) {
            var header = section.querySelector(".trip-form-section-header");
            if (!header) {
                return;
            }

            header.classList.add("is-collapsible");
            header.setAttribute("role", "button");
            header.setAttribute("tabindex", "0");

            var notation = document.createElement("span");
            notation.className = "trip-section-notation";
            notation.setAttribute("aria-hidden", "true");
            header.appendChild(notation);

            var sectionHasErrors = !!section.querySelector(".text-danger");
            var isRequiredSection = String(section.getAttribute("data-section-required") || "").toLowerCase() === "true";
            var isCollapsed = !isRequiredSection && !sectionHasErrors;

            function renderSectionState() {
                section.classList.toggle("is-collapsed", isCollapsed);
                header.setAttribute("aria-expanded", String(!isCollapsed));
                header.setAttribute("title", isCollapsed ? "Expand section" : "Collapse section");
                notation.textContent = isCollapsed ? "▸" : "▾";
                section.dispatchEvent(new CustomEvent("trip-section-visibility-changed", {
                    bubbles: true,
                    detail: { collapsed: isCollapsed }
                }));
            }

            section.__tripSetCollapsed = function setCollapsed(nextCollapsed) {
                isCollapsed = !!nextCollapsed;
                renderSectionState();
            };

            function toggleSection() {
                isCollapsed = !isCollapsed;
                renderSectionState();
            }

            header.addEventListener("click", function onHeaderClick() {
                toggleSection();
            });
            header.addEventListener("keydown", function onHeaderKeydown(event) {
                if (event.key !== "Enter" && event.key !== " ") {
                    return;
                }
                event.preventDefault();
                toggleSection();
            });

            renderSectionState();
        });
    }

    function initMediaDropzones(form) {
        function imageFilesFromList(files) {
            return Array.prototype.slice.call(files || []).filter(function isImage(file) {
                return String((file && file.type) || "").toLowerCase().indexOf("image/") === 0;
            });
        }

        function assignFilesToInput(input, files) {
            if (!input || typeof DataTransfer === "undefined") {
                return;
            }
            var transfer = new DataTransfer();
            files.forEach(function eachFile(file) {
                transfer.items.add(file);
            });
            input.files = transfer.files;
            input.dispatchEvent(new Event("change", { bubbles: true }));
        }

        var heroDropzone = form.querySelector("[data-media-hero-dropzone]");
        if (heroDropzone) {
            var heroInputId = heroDropzone.getAttribute("data-input-id");
            var heroInput = heroInputId ? document.getElementById(heroInputId) : null;
            var heroPreview = heroDropzone.querySelector("[data-media-hero-preview]");
            var heroPlaceholder = heroDropzone.querySelector("[data-media-hero-placeholder]");
            var heroPreviewUrl = "";
            var heroInitialSrc = heroPreview && !heroPreview.hidden ? String(heroPreview.getAttribute("src") || "") : "";

            function clearHeroPreviewUrl() {
                if (!heroPreviewUrl) {
                    return;
                }
                URL.revokeObjectURL(heroPreviewUrl);
                heroPreviewUrl = "";
            }

            function renderHeroPreview(src) {
                if (!heroPreview || !heroPlaceholder) {
                    return;
                }
                var hasSrc = String(src || "").trim().length > 0;
                if (hasSrc) {
                    heroPreview.src = String(src);
                    heroPreview.hidden = false;
                    heroPlaceholder.hidden = true;
                } else {
                    heroPreview.removeAttribute("src");
                    heroPreview.hidden = true;
                    heroPlaceholder.hidden = false;
                }
            }

            function setHeroDragState(isActive) {
                heroDropzone.classList.toggle("is-dragover", !!isActive);
            }

            if (heroInput && heroPreview && heroPlaceholder) {
                renderHeroPreview(heroInitialSrc);

                heroDropzone.addEventListener("click", function onHeroClick() {
                    heroInput.click();
                });
                heroDropzone.addEventListener("keydown", function onHeroKeydown(event) {
                    if (event.key !== "Enter" && event.key !== " ") {
                        return;
                    }
                    event.preventDefault();
                    heroInput.click();
                });
                heroDropzone.addEventListener("dragover", function onHeroDragOver(event) {
                    event.preventDefault();
                    setHeroDragState(true);
                });
                heroDropzone.addEventListener("dragleave", function onHeroDragLeave(event) {
                    if (event.currentTarget === event.target) {
                        setHeroDragState(false);
                    }
                });
                heroDropzone.addEventListener("drop", function onHeroDrop(event) {
                    event.preventDefault();
                    setHeroDragState(false);
                    var dropped = imageFilesFromList((event.dataTransfer || {}).files || []);
                    if (dropped.length === 0) {
                        return;
                    }
                    assignFilesToInput(heroInput, [dropped[0]]);
                });
                heroInput.addEventListener("change", function onHeroInputChange() {
                    clearHeroPreviewUrl();
                    var selected = imageFilesFromList(heroInput.files);
                    if (selected.length > 0) {
                        heroPreviewUrl = URL.createObjectURL(selected[0]);
                        renderHeroPreview(heroPreviewUrl);
                        return;
                    }
                    renderHeroPreview(heroInitialSrc);
                });
            }
        }

        var galleryDropzone = form.querySelector("[data-media-gallery-dropzone]");
        if (galleryDropzone) {
            var galleryInputId = galleryDropzone.getAttribute("data-input-id");
            var galleryInput = galleryInputId ? document.getElementById(galleryInputId) : null;
            var gallerySlots = Array.prototype.slice.call(galleryDropzone.querySelectorAll("[data-media-gallery-slot]"));
            var galleryPreviewUrls = [];

            function clearGalleryPreviewUrls() {
                galleryPreviewUrls.forEach(function eachUrl(url) {
                    URL.revokeObjectURL(url);
                });
                galleryPreviewUrls = [];
            }

            function renderGalleryPreview(files) {
                clearGalleryPreviewUrls();
                gallerySlots.forEach(function eachSlot(slot, index) {
                    var preview = slot.querySelector("[data-media-gallery-preview]");
                    var placeholder = slot.querySelector("[data-media-gallery-placeholder]");
                    var file = files[index];
                    if (!preview || !placeholder) {
                        return;
                    }
                    if (file) {
                        var fileUrl = URL.createObjectURL(file);
                        galleryPreviewUrls.push(fileUrl);
                        preview.src = fileUrl;
                        preview.hidden = false;
                        placeholder.hidden = true;
                    } else {
                        preview.removeAttribute("src");
                        preview.hidden = true;
                        placeholder.hidden = false;
                    }
                });
            }

            function mergeGalleryFilesAtSlot(existingFiles, incomingFiles, slotIndex) {
                var merged = existingFiles.slice(0, 4);
                var writeIndex = slotIndex;
                incomingFiles.forEach(function eachIncoming(file) {
                    if (writeIndex >= 4) {
                        return;
                    }
                    merged[writeIndex] = file;
                    writeIndex += 1;
                });
                return merged.filter(function hasFile(file) {
                    return !!file;
                });
            }

            function setSlotDragState(slot, isActive) {
                slot.classList.toggle("is-dragover", !!isActive);
            }

            if (galleryInput && gallerySlots.length > 0) {
                renderGalleryPreview(imageFilesFromList(galleryInput.files).slice(0, 4));
                galleryInput.addEventListener("change", function onGalleryInputChange() {
                    renderGalleryPreview(imageFilesFromList(galleryInput.files).slice(0, 4));
                });

                gallerySlots.forEach(function bindGallerySlot(slot, index) {
                    slot.addEventListener("click", function onGalleryClick() {
                        galleryInput.click();
                    });
                    slot.addEventListener("dragover", function onGalleryDragOver(event) {
                        event.preventDefault();
                        setSlotDragState(slot, true);
                    });
                    slot.addEventListener("dragleave", function onGalleryDragLeave(event) {
                        if (event.currentTarget === event.target) {
                            setSlotDragState(slot, false);
                        }
                    });
                    slot.addEventListener("drop", function onGalleryDrop(event) {
                        event.preventDefault();
                        setSlotDragState(slot, false);
                        var droppedFiles = imageFilesFromList((event.dataTransfer || {}).files || []);
                        if (droppedFiles.length === 0) {
                            return;
                        }
                        var existingFiles = imageFilesFromList(galleryInput.files);
                        var mergedFiles = mergeGalleryFilesAtSlot(existingFiles, droppedFiles, index);
                        assignFilesToInput(galleryInput, mergedFiles.slice(0, 4));
                    });
                });
            }
        }
    }

    var form = document.querySelector(".trip-creation-form");
    if (!form) {
        return;
    }

    initCollapsibleSections(form);
    initMediaDropzones(form);
    initDestinationPicker(form);
    initChoiceLimitGroups(form);
    initAgePreferenceSliders(form);
    initSectionIndex(form);
    initTripProgress(form);
    Array.prototype.slice.call(form.querySelectorAll("[data-list-builder]")).forEach(initListBuilder);
    Array.prototype.slice.call(form.querySelectorAll("[data-pill-builder]")).forEach(initPillBuilder);
    Array.prototype.slice.call(form.querySelectorAll("[data-day-builder]")).forEach(initDayBuilder);
    Array.prototype.slice.call(form.querySelectorAll("[data-faq-builder]")).forEach(initFaqBuilder);

    form.addEventListener("submit", function onSubmit() {
        Array.prototype.slice.call(form.querySelectorAll("[data-list-builder]")).forEach(syncListBuilder);
        Array.prototype.slice.call(form.querySelectorAll("[data-pill-builder]")).forEach(syncPillBuilder);
        Array.prototype.slice.call(form.querySelectorAll("[data-day-builder]")).forEach(syncDayBuilder);
        Array.prototype.slice.call(form.querySelectorAll("[data-faq-builder]")).forEach(syncFaqBuilder);
    });
})();
