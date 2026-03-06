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

    function hasHtmlMarkup(value) {
        return /<\/?[a-z][\s\S]*>/i.test(String(value || ""));
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function htmlFromPlainText(value) {
        var text = String(value || "").trim();
        if (!text) {
            return "";
        }
        return text
            .split(/\n{2,}/)
            .map(function eachParagraph(paragraph) {
                var escaped = escapeHtml(paragraph).replace(/\n/g, "<br>");
                return "<p>" + escaped + "</p>";
            })
            .join("");
    }

    function normalizeEditorHtml(value) {
        var html = String(value || "").trim();
        if (!html) {
            return "";
        }
        var temp = document.createElement("div");
        temp.innerHTML = html;
        var plain = String(temp.textContent || "").trim();
        if (!plain) {
            return "";
        }
        return String(temp.innerHTML || "").trim();
    }

    function ensureRichTextEditor(textarea, onChange) {
        if (!textarea || textarea.getAttribute("data-rich-text-ready") === "1") {
            return;
        }
        textarea.setAttribute("data-rich-text-ready", "1");

        var shell = document.createElement("div");
        shell.className = "rich-text-shell";
        shell.setAttribute("data-progress-ignore", "1");

        var toolbar = document.createElement("div");
        toolbar.className = "rich-text-toolbar";

        var editor = document.createElement("div");
        editor.className = "rich-text-editor";
        editor.setAttribute("contenteditable", "true");
        editor.setAttribute("role", "textbox");
        editor.setAttribute("aria-multiline", "true");
        editor.setAttribute("data-placeholder", String(textarea.getAttribute("placeholder") || ""));

        function syncTextareaValue() {
            var normalized = normalizeEditorHtml(editor.innerHTML);
            textarea.value = normalized;
            if (typeof onChange === "function") {
                onChange();
            }
        }

        function runCommand(command, value) {
            editor.focus();
            document.execCommand("styleWithCSS", false, true);
            document.execCommand(command, false, value === undefined ? null : value);
            window.setTimeout(function syncAfterCommand() {
                syncTextareaValue();
                updateToolStates();
            }, 0);
        }

        function applyColorCommand(command, colorValue) {
            var normalizedColor = String(colorValue || "").trim();
            if (!/^#[0-9a-fA-F]{6}$/.test(normalizedColor)) {
                return;
            }
            editor.focus();
            document.execCommand("styleWithCSS", false, true);
            if (command === "hiliteColor") {
                var applied = document.execCommand("hiliteColor", false, normalizedColor);
                if (!applied) {
                    document.execCommand("backColor", false, normalizedColor);
                }
            } else {
                document.execCommand("foreColor", false, normalizedColor);
            }
            window.setTimeout(function syncAfterColorChange() {
                syncTextareaValue();
                updateToolStates();
            }, 0);
        }

        function queryCommandStateSafe(command) {
            try {
                return !!document.queryCommandState(command);
            } catch (_error) {
                return false;
            }
        }

        function queryCommandValueSafe(command) {
            try {
                return String(document.queryCommandValue(command) || "").toLowerCase();
            } catch (_error) {
                return "";
            }
        }

        function createToolbarGroup() {
            var group = document.createElement("div");
            group.className = "rich-text-toolbar-group";
            toolbar.appendChild(group);
            return group;
        }

        var stateBinders = [];
        function createToolButton(group, config) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "rich-text-tool";
            button.setAttribute("aria-label", config.title);
            button.title = config.title;

            var glyph = document.createElement("span");
            glyph.className = "rich-text-tool-glyph";
            glyph.textContent = config.glyph;
            button.appendChild(glyph);

            button.addEventListener("click", function onToolClick() {
                if (typeof config.execute === "function") {
                    config.execute();
                    return;
                }
                runCommand(config.command, config.value);
            });

            if (typeof config.isActive === "function") {
                stateBinders.push(function bindState() {
                    button.classList.toggle("is-active", !!config.isActive());
                });
            }

            group.appendChild(button);
            return button;
        }

        function updateToolStates() {
            stateBinders.forEach(function eachBinder(binder) {
                binder();
            });
        }

        function isFormatBlockActive(expectedTag) {
            var current = queryCommandValueSafe("formatBlock").replace(/[<>]/g, "");
            return current === String(expectedTag || "").toLowerCase();
        }

        function createLinkFromSelection() {
            editor.focus();
            var provided = window.prompt("Enter URL", "https://");
            var href = String(provided || "").trim();
            if (!href) {
                return;
            }
            if (!/^https?:\/\//i.test(href) && !/^mailto:/i.test(href)) {
                href = "https://" + href;
            }
            runCommand("createLink", href);
        }

        var blockGroup = createToolbarGroup();
        createToolButton(blockGroup, {
            glyph: "P",
            title: "Paragraph",
            execute: function toParagraph() {
                runCommand("formatBlock", "<p>");
            },
            isActive: function paragraphActive() {
                var current = queryCommandValueSafe("formatBlock").replace(/[<>]/g, "");
                return !current || current === "p" || current === "div";
            }
        });
        createToolButton(blockGroup, {
            glyph: "H2",
            title: "Heading",
            execute: function toHeading() {
                runCommand("formatBlock", "<h2>");
            },
            isActive: function headingActive() {
                return isFormatBlockActive("h2");
            }
        });
        createToolButton(blockGroup, {
            glyph: "Q",
            title: "Quote",
            execute: function toQuote() {
                runCommand("formatBlock", "<blockquote>");
            },
            isActive: function quoteActive() {
                return isFormatBlockActive("blockquote");
            }
        });

        var emphasisGroup = createToolbarGroup();
        createToolButton(emphasisGroup, {
            glyph: "B",
            title: "Bold (Ctrl+B)",
            command: "bold",
            isActive: function boldActive() {
                return queryCommandStateSafe("bold");
            }
        });
        createToolButton(emphasisGroup, {
            glyph: "I",
            title: "Italic (Ctrl+I)",
            command: "italic",
            isActive: function italicActive() {
                return queryCommandStateSafe("italic");
            }
        });
        createToolButton(emphasisGroup, {
            glyph: "U",
            title: "Underline (Ctrl+U)",
            command: "underline",
            isActive: function underlineActive() {
                return queryCommandStateSafe("underline");
            }
        });

        var listGroup = createToolbarGroup();
        createToolButton(listGroup, {
            glyph: "UL",
            title: "Bullet list",
            command: "insertUnorderedList",
            isActive: function unorderedListActive() {
                return queryCommandStateSafe("insertUnorderedList");
            }
        });
        createToolButton(listGroup, {
            glyph: "OL",
            title: "Numbered list",
            command: "insertOrderedList",
            isActive: function orderedListActive() {
                return queryCommandStateSafe("insertOrderedList");
            }
        });

        var alignGroup = createToolbarGroup();
        createToolButton(alignGroup, {
            glyph: "L",
            title: "Align left",
            command: "justifyLeft",
            isActive: function leftActive() {
                return queryCommandStateSafe("justifyLeft");
            }
        });
        createToolButton(alignGroup, {
            glyph: "C",
            title: "Align center",
            command: "justifyCenter",
            isActive: function centerActive() {
                return queryCommandStateSafe("justifyCenter");
            }
        });
        createToolButton(alignGroup, {
            glyph: "R",
            title: "Align right",
            command: "justifyRight",
            isActive: function rightActive() {
                return queryCommandStateSafe("justifyRight");
            }
        });

        var linkGroup = createToolbarGroup();
        createToolButton(linkGroup, {
            glyph: "Link",
            title: "Insert link",
            execute: createLinkFromSelection
        });
        createToolButton(linkGroup, {
            glyph: "Unlink",
            title: "Remove link",
            command: "unlink"
        });
        createToolButton(linkGroup, {
            glyph: "Clear",
            title: "Clear formatting",
            execute: function clearFormatting() {
                editor.focus();
                document.execCommand("removeFormat", false, null);
                document.execCommand("unlink", false, null);
                window.setTimeout(function syncAfterClear() {
                    syncTextareaValue();
                    updateToolStates();
                }, 0);
            }
        });

        var historyGroup = createToolbarGroup();
        createToolButton(historyGroup, {
            glyph: "Undo",
            title: "Undo",
            command: "undo"
        });
        createToolButton(historyGroup, {
            glyph: "Redo",
            title: "Redo",
            command: "redo"
        });

        var colorGroup = createToolbarGroup();
        function createColorTool(label, command, defaultColor) {
            var wrapper = document.createElement("label");
            wrapper.className = "rich-text-color-tool";
            wrapper.title = label;

            var hint = document.createElement("span");
            hint.className = "rich-text-color-label";
            hint.textContent = label;

            var input = document.createElement("input");
            input.className = "rich-text-color-input";
            input.type = "color";
            input.value = defaultColor;
            input.setAttribute("aria-label", label);
            input.addEventListener("input", function onColorChange() {
                applyColorCommand(command, input.value);
            });

            wrapper.appendChild(hint);
            wrapper.appendChild(input);
            colorGroup.appendChild(wrapper);
        }

        createColorTool("Text", "foreColor", "#0f172a");
        createColorTool("Highlight", "hiliteColor", "#fde68a");

        var initialValue = String(textarea.value || "");
        if (initialValue.trim()) {
            editor.innerHTML = hasHtmlMarkup(initialValue) ? initialValue : htmlFromPlainText(initialValue);
            syncTextareaValue();
        } else {
            editor.innerHTML = "";
        }

        editor.addEventListener("input", function onEditorInput() {
            syncTextareaValue();
            updateToolStates();
        });
        editor.addEventListener("blur", syncTextareaValue);
        editor.addEventListener("keyup", updateToolStates);
        editor.addEventListener("mouseup", updateToolStates);
        editor.addEventListener("focus", updateToolStates);
        editor.addEventListener("paste", function onPaste(event) {
            event.preventDefault();
            var clipboard = (event.clipboardData || window.clipboardData);
            var pastedText = clipboard ? String(clipboard.getData("text/plain") || "") : "";
            document.execCommand("insertText", false, pastedText);
        });

        document.addEventListener("selectionchange", function onSelectionChange() {
            if (document.activeElement === editor || editor.contains(document.activeElement)) {
                updateToolStates();
            }
        });

        textarea.classList.add("rich-text-source");
        textarea.parentNode.insertBefore(shell, textarea);
        shell.appendChild(toolbar);
        shell.appendChild(editor);
        shell.appendChild(textarea);
        updateToolStates();
    }

    function createDragHandle(label) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "dynamic-row-handle";
        button.setAttribute("data-row-drag-handle", "1");
        button.setAttribute("draggable", "true");
        button.setAttribute("aria-label", label);
        button.title = label;
        button.textContent = "⋮⋮";
        return button;
    }

    function createRowRemoveButton(label, onClick) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "dynamic-row-remove";
        button.setAttribute("aria-label", label);
        button.title = label;
        button.textContent = "×";
        button.addEventListener("click", function onRemoveClick(event) {
            event.preventDefault();
            onClick();
        });
        return button;
    }

    function bindReorderableRows(itemsHost, rowSelector, onReorder) {
        if (!itemsHost || itemsHost.getAttribute("data-reorder-ready") === "1") {
            return;
        }
        itemsHost.setAttribute("data-reorder-ready", "1");
        var activeRow = null;
        var hoverRow = null;
        var dragImageNode = null;

        function clearHoverRow() {
            if (!hoverRow) {
                return;
            }
            hoverRow.classList.remove("is-drop-target");
            hoverRow = null;
        }

        function removeDragImageNode() {
            if (!dragImageNode) {
                return;
            }
            dragImageNode.remove();
            dragImageNode = null;
        }

        function resetActiveRow() {
            if (activeRow) {
                activeRow.classList.remove("is-dragging");
            }
            clearHoverRow();
            removeDragImageNode();
            itemsHost.classList.remove("is-reordering");
            activeRow = null;
        }

        itemsHost.addEventListener("dragstart", function onDragStart(event) {
            var target = event.target;
            var handle = target && target.closest ? target.closest("[data-row-drag-handle]") : null;
            if (!handle) {
                event.preventDefault();
                return;
            }
            var sourceRow = handle.closest(rowSelector);
            if (!sourceRow) {
                event.preventDefault();
                return;
            }
            var sourceBounds = sourceRow.getBoundingClientRect();
            activeRow = sourceRow;
            activeRow.classList.add("is-dragging");
            itemsHost.classList.add("is-reordering");
            if (event.dataTransfer) {
                event.dataTransfer.effectAllowed = "move";
                try {
                    event.dataTransfer.setData("text/plain", "drag-row");
                } catch (_error) {
                    // Ignore setData errors for browsers that restrict drag payloads.
                }

                // Use a custom drag image so the full row appears to float with the cursor.
                dragImageNode = sourceRow.cloneNode(true);
                dragImageNode.classList.add("dynamic-row-drag-image");
                dragImageNode.style.width = String(Math.max(220, Math.ceil(sourceBounds.width))) + "px";
                dragImageNode.style.height = String(Math.max(44, Math.ceil(sourceBounds.height))) + "px";
                dragImageNode.style.left = "-9999px";
                dragImageNode.style.top = "-9999px";
                document.body.appendChild(dragImageNode);
                try {
                    var pointerOffsetX = Math.max(18, Math.min(Math.ceil(sourceBounds.width * 0.18), 76));
                    var pointerOffsetY = Math.max(16, Math.min(Math.ceil(sourceBounds.height * 0.45), 44));
                    event.dataTransfer.setDragImage(dragImageNode, pointerOffsetX, pointerOffsetY);
                } catch (_error) {
                    // Keep default browser drag image as fallback.
                }
            }
        });

        itemsHost.addEventListener("dragover", function onDragOver(event) {
            if (!activeRow) {
                return;
            }
            var target = event.target;
            var targetRow = target && target.closest ? target.closest(rowSelector) : null;
            if (!targetRow || targetRow === activeRow) {
                return;
            }
            event.preventDefault();
            var bounds = targetRow.getBoundingClientRect();
            var insertBefore = (event.clientY - bounds.top) < bounds.height / 2;
            if (hoverRow !== targetRow) {
                clearHoverRow();
                targetRow.classList.add("is-drop-target");
                hoverRow = targetRow;
            }
            itemsHost.insertBefore(activeRow, insertBefore ? targetRow : targetRow.nextSibling);
        });

        itemsHost.addEventListener("drop", function onDrop(event) {
            if (!activeRow) {
                return;
            }
            event.preventDefault();
            resetActiveRow();
            if (typeof onReorder === "function") {
                onReorder();
            }
        });

        itemsHost.addEventListener("dragleave", function onDragLeave(event) {
            if (!itemsHost.contains(event.relatedTarget)) {
                clearHoverRow();
            }
        });

        itemsHost.addEventListener("dragend", function onDragEnd() {
            if (!activeRow) {
                return;
            }
            resetActiveRow();
            if (typeof onReorder === "function") {
                onReorder();
            }
        });
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
        row.className = "dynamic-list-row dynamic-row-inline";
        row.setAttribute("data-list-row", "1");

        var handle = createDragHandle("Drag to reorder item");
        var remove = createRowRemoveButton("Remove item", function onRemove() {
            row.remove();
            syncListBuilder(root);
        });

        var input = document.createElement("input");
        input.type = "text";
        input.className = "form-input dynamic-row-inline-input";
        input.setAttribute("data-list-value", "1");
        input.placeholder = root.getAttribute("data-item-example") || root.getAttribute("data-item-label") || "Item";
        input.value = String(value || "");
        input.addEventListener("input", function onInput() {
            syncListBuilder(root);
        });

        row.appendChild(handle);
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

        bindReorderableRows(itemsHost, "[data-list-row]", function onListReorder() {
            syncListBuilder(root);
        });
        syncListBuilder(root);
    }

    function parseDateTimeLocal(value) {
        var text = String(value || "").trim();
        if (!text) {
            return null;
        }
        var parts = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
        if (!parts) {
            return null;
        }
        var year = Number(parts[1]);
        var month = Number(parts[2]) - 1;
        var day = Number(parts[3]);
        var hour = Number(parts[4] || 0);
        var minute = Number(parts[5] || 0);
        var candidate = new Date(year, month, day, hour, minute, 0, 0);
        if (!isFinite(candidate.getTime())) {
            return null;
        }
        return candidate;
    }

    function formatDayDate(dateValue) {
        if (!(dateValue instanceof Date) || !isFinite(dateValue.getTime())) {
            return "Date TBD";
        }
        return dateValue.toLocaleDateString(undefined, {
            weekday: "short",
            year: "numeric",
            month: "short",
            day: "numeric"
        });
    }

    function refreshDayRowMeta(root) {
        var startInputId = String(root.getAttribute("data-start-input-id") || "").trim();
        var startInput = startInputId ? document.getElementById(startInputId) : null;
        var startDate = parseDateTimeLocal(startInput ? startInput.value : "");

        Array.prototype.slice.call(root.querySelectorAll("[data-day-row]")).forEach(function eachRow(row, index) {
            var serialNode = row.querySelector("[data-day-serial]");
            var dateNode = row.querySelector("[data-day-date]");
            if (serialNode) {
                serialNode.textContent = "Day " + String(index);
            }
            if (!dateNode) {
                return;
            }
            if (!startDate) {
                dateNode.textContent = "Date TBD";
                return;
            }
            var currentDate = new Date(startDate.getTime());
            currentDate.setDate(startDate.getDate() + index);
            dateNode.textContent = formatDayDate(currentDate);
        });
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
        refreshDayRowMeta(root);
        requestProgressRefresh(root);
    }

    function createDayRow(root, value) {
        var dayValue = value && typeof value === "object" ? value : {};
        var row = document.createElement("div");
        row.className = "dynamic-day-row";
        row.setAttribute("data-day-row", "1");

        var tools = document.createElement("div");
        tools.className = "dynamic-day-meta";

        var toolsLeft = document.createElement("div");
        toolsLeft.className = "dynamic-day-meta-left";

        var handle = createDragHandle("Drag to reorder day");
        var serial = document.createElement("span");
        serial.className = "dynamic-day-seq";
        serial.setAttribute("data-day-serial", "1");
        serial.textContent = "Day 0";
        toolsLeft.appendChild(handle);
        toolsLeft.appendChild(serial);

        var dateLabel = document.createElement("span");
        dateLabel.className = "dynamic-day-date";
        dateLabel.setAttribute("data-day-date", "1");
        dateLabel.textContent = "Date TBD";

        var remove = createRowRemoveButton("Remove day", function onRemove() {
            row.remove();
            syncDayBuilder(root);
        });

        tools.appendChild(toolsLeft);
        tools.appendChild(dateLabel);
        tools.appendChild(remove);
        row.appendChild(tools);

        row.insertAdjacentHTML("beforeend", "" +
            "<div class=\"trip-form-grid trip-form-grid-2\">" +
            "  <label class=\"inline-checkbox-label\"><input type=\"checkbox\" data-day-flexible> flexible?</label>" +
            "</div>" +
            "<div class=\"form-field\"><label>Day Title</label><input class=\"form-input\" type=\"text\" maxlength=\"180\" data-day-title placeholder=\"e.g. Arrival + old town walk\"></div>" +
            "<div class=\"form-field\"><label>What happens on this day ...</label><textarea class=\"form-input\" rows=\"4\" maxlength=\"2000\" data-day-description data-rich-text=\"1\" placeholder=\"e.g. Check-in, local lunch, sunset viewpoint, and welcome dinner.\"></textarea></div>" +
            "<div class=\"trip-form-grid trip-form-grid-2\">" +
            "  <div class=\"form-field\"><label>Stay</label><input class=\"form-input\" type=\"text\" maxlength=\"180\" data-day-stay placeholder=\"e.g. Lakeside resort\"></div>" +
            "  <div class=\"form-field\"><label>Meals</label><input class=\"form-input\" type=\"text\" maxlength=\"180\" data-day-meals placeholder=\"e.g. Breakfast, Dinner\"></div>" +
            "</div>");

        var flexible = row.querySelector("[data-day-flexible]");
        if (flexible) {
            flexible.checked = !!dayValue.is_flexible;
            flexible.addEventListener("change", function onChange() {
                syncDayBuilder(root);
            });
        }

        [
            ["[data-day-title]", "title"],
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

        var dayDescription = row.querySelector("[data-day-description]");
        if (dayDescription) {
            dayDescription.value = String(dayValue.description || "");
            ensureRichTextEditor(dayDescription, function onDayDescriptionChange() {
                syncDayBuilder(root);
            });
        }

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

        bindReorderableRows(itemsHost, "[data-day-row]", function onDayReorder() {
            syncDayBuilder(root);
        });

        var startInputId = String(root.getAttribute("data-start-input-id") || "").trim();
        var startInput = startInputId ? document.getElementById(startInputId) : null;
        if (startInput && startInput.getAttribute("data-day-meta-bound") !== "1") {
            startInput.setAttribute("data-day-meta-bound", "1");
            ["input", "change"].forEach(function eachEventName(eventName) {
                startInput.addEventListener(eventName, function onStartDateChange() {
                    syncDayBuilder(root);
                });
            });
        }

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

        var rowInline = document.createElement("div");
        rowInline.className = "dynamic-row-inline dynamic-row-inline-faq";
        rowInline.appendChild(createDragHandle("Drag to reorder FAQ"));

        var question = document.createElement("input");
        question.className = "form-input dynamic-row-inline-input";
        question.type = "text";
        question.maxLength = 280;
        question.setAttribute("data-faq-question", "1");
        question.setAttribute("aria-label", "FAQ question");
        question.placeholder = "e.g. Is airport pickup included?";
        question.value = String(faqValue.question || "");
        question.addEventListener("input", function onInput() {
            syncFaqBuilder(root);
        });
        rowInline.appendChild(question);

        rowInline.appendChild(createRowRemoveButton("Remove FAQ", function onRemove() {
            row.remove();
            syncFaqBuilder(root);
        }));
        row.appendChild(rowInline);

        var answerField = document.createElement("div");
        answerField.className = "form-field";
        var answerLabel = document.createElement("label");
        answerLabel.textContent = "Answer";
        var answer = document.createElement("textarea");
        answer.className = "form-input";
        answer.rows = 3;
        answer.maxLength = 2000;
        answer.setAttribute("data-faq-answer", "1");
        answer.setAttribute("data-rich-text", "1");
        answer.placeholder = "e.g. Pickup is optional and can be arranged at extra cost.";
        answer.value = String(faqValue.answer || "");
        answerField.appendChild(answerLabel);
        answerField.appendChild(answer);
        row.appendChild(answerField);

        if (answer) {
            ensureRichTextEditor(answer, function onFaqAnswerChange() {
                syncFaqBuilder(root);
            });
        }

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

        bindReorderableRows(itemsHost, "[data-faq-row]", function onFaqReorder() {
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
            var parentField = group.closest(".form-field");
            var statusNode = parentField ? parentField.querySelector("[data-choice-limit-status]") : null;
            var baseLabel = String(group.getAttribute("data-choice-limit-label") || ("Choose up to " + String(limit))).trim();

            function checkedCount() {
                return checkboxes.filter(function isChecked(input) {
                    return !!input.checked;
                }).length;
            }

            function syncDisabledState() {
                var totalChecked = checkedCount();
                var atLimit = totalChecked >= limit;
                checkboxes.forEach(function eachCheckbox(input) {
                    if (!input.checked) {
                        input.disabled = atLimit;
                    } else {
                        input.disabled = false;
                    }
                });
                group.classList.toggle("is-at-limit", atLimit);
                if (statusNode) {
                    statusNode.textContent = baseLabel + " (" + String(totalChecked) + " selected)";
                }
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

    function initRichTextEditors(form) {
        Array.prototype.slice.call(form.querySelectorAll("textarea[data-rich-text]")).forEach(function eachTextarea(textarea) {
            ensureRichTextEditor(textarea, function onRichTextChange() {
                requestProgressRefresh(textarea);
            });
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
            link.setAttribute("data-index-target", sectionId);

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

            var check = document.createElement("span");
            check.className = "trip-form-index-check";
            check.setAttribute("aria-hidden", "true");
            check.innerHTML = (
                "<svg viewBox=\"0 0 24 24\">" +
                "<circle cx=\"12\" cy=\"12\" r=\"9\"></circle>" +
                "<path d=\"m8.6 12.2 2.4 2.4 4.8-4.9\"></path>" +
                "</svg>"
            );
            link.appendChild(check);

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
        var layout = form.parentElement;
        var progressShell = layout ? layout.querySelector("[data-trip-progress-shell]") : document.querySelector("[data-trip-progress-shell]");
        if (!progressShell) {
            return;
        }

        var progressRing = progressShell.querySelector("[data-trip-progress-ring]");
        var progressPercentNodes = Array.prototype.slice.call(document.querySelectorAll("[data-trip-progress-percent]"));
        var progressSectionNodes = Array.prototype.slice.call(document.querySelectorAll("[data-trip-progress-sections]"));
        var sections = Array.prototype.slice.call(form.querySelectorAll(".trip-form-section"));
        if (!progressRing || progressPercentNodes.length === 0 || progressSectionNodes.length === 0 || sections.length === 0) {
            return;
        }
        var formMode = String(form.getAttribute("data-form-mode") || "create").trim().toLowerCase();
        var requiresUserDelta = formMode === "create";

        var ringRadius = Number(progressRing.getAttribute("r") || 0);
        var ringCircumference = ringRadius > 0 ? (2 * Math.PI * ringRadius) : 0;
        if (ringCircumference > 0) {
            progressRing.style.strokeDasharray = String(ringCircumference) + " " + String(ringCircumference);
            progressRing.style.strokeDashoffset = String(ringCircumference);
        }
        var baselineControlSignatures = new WeakMap();
        var baselinePillCounts = new WeakMap();
        var touchedControls = new WeakSet();

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

        function normalizePlainValue(value) {
            return String(value || "")
                .replace(/\u00a0/g, " ")
                .replace(/[\u200B-\u200D\uFEFF]/g, "")
                .trim();
        }

        function isRichTextControl(control) {
            if (!control) {
                return false;
            }
            return control.getAttribute("data-rich-text") === "1" || control.classList.contains("rich-text-source");
        }

        function normalizedControlValue(control) {
            if (!control) {
                return "";
            }
            if (isRichTextControl(control)) {
                return normalizeEditorHtml(control.value);
            }
            return normalizePlainValue(control.value);
        }

        function resolveBuilderTargetInput(builderRoot) {
            if (!builderRoot) {
                return null;
            }
            var inputId = String(builderRoot.getAttribute("data-target-input-id") || "").trim();
            if (!inputId) {
                return null;
            }
            return document.getElementById(inputId);
        }

        function parseBuilderPayloadArray(builderRoot) {
            var hiddenInput = resolveBuilderTargetInput(builderRoot);
            if (!hiddenInput) {
                return [];
            }
            var parsed = parseJson(hiddenInput.value, []);
            return Array.isArray(parsed) ? parsed : [];
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
                        return option.selected && normalizePlainValue(option.value) !== "";
                    });
                }
                return normalizePlainValue(control.value) !== "";
            }
            return normalizedControlValue(control) !== "";
        }

        function isBooleanControl(control) {
            var type = String(control.type || "").toLowerCase();
            return type === "checkbox" || type === "radio";
        }

        function controlSignature(control) {
            var tag = String(control.tagName || "").toLowerCase();
            var type = String(control.type || "").toLowerCase();
            if (type === "checkbox" || type === "radio") {
                return control.checked ? "1" : "0";
            }
            if (type === "file") {
                return String(control.files && control.files.length ? control.files.length : 0);
            }
            if (tag === "select") {
                if (control.multiple && control.options) {
                    return Array.prototype.slice.call(control.options)
                        .filter(function onlySelected(option) {
                            return option.selected && normalizePlainValue(option.value) !== "";
                        })
                        .map(function mapOption(option) {
                            return normalizePlainValue(option.value);
                        })
                        .sort()
                        .join("|");
                }
                return normalizePlainValue(control.value);
            }
            return normalizedControlValue(control);
        }

        function controlDiffersFromBaseline(control) {
            var currentSignature = controlSignature(control);
            if (baselineControlSignatures.has(control)) {
                return baselineControlSignatures.get(control) !== currentSignature;
            }
            if (requiresUserDelta && !touchedControls.has(control)) {
                return false;
            }
            return controlHasValue(control);
        }

        function sectionHasUserDelta(section) {
            if (!requiresUserDelta) {
                return true;
            }
            var controls = Array.prototype.slice.call(section.querySelectorAll("input, select, textarea"))
                .filter(isTrackableControl);
            if (controls.some(controlDiffersFromBaseline)) {
                return true;
            }
            var baselinePills = Number(baselinePillCounts.get(section) || 0);
            var currentPills = section.querySelectorAll("[data-pill-item]").length;
            return currentPills !== baselinePills;
        }

        function sectionIsComplete(section) {
            function payloadTextValue(value) {
                return normalizePlainValue(value);
            }

            function payloadRichTextValue(value) {
                return normalizeEditorHtml(value);
            }

            var listBuilder = section.querySelector("[data-list-builder]");
            if (listBuilder) {
                var listItems = parseBuilderPayloadArray(listBuilder);
                var hasCompleteListRow = listItems.some(function anyCompleteListRow(item) {
                    return payloadTextValue(item) !== "";
                });
                return sectionHasUserDelta(section) && hasCompleteListRow;
            }

            var dayBuilder = section.querySelector("[data-day-builder]");
            if (dayBuilder) {
                var dayItems = parseBuilderPayloadArray(dayBuilder);
                var hasCompleteDayRow = dayItems.some(function anyCompleteDayRow(day) {
                    var dayRecord = day && typeof day === "object" ? day : {};
                    return (
                        payloadTextValue(dayRecord.title) !== "" &&
                        payloadRichTextValue(dayRecord.description) !== "" &&
                        payloadTextValue(dayRecord.stay) !== "" &&
                        payloadTextValue(dayRecord.meals) !== ""
                    );
                });
                return sectionHasUserDelta(section) && hasCompleteDayRow;
            }

            var faqBuilder = section.querySelector("[data-faq-builder]");
            if (faqBuilder) {
                var faqItems = parseBuilderPayloadArray(faqBuilder);
                var hasCompleteFaqRow = faqItems.some(function anyCompleteFaqRow(faq) {
                    var faqRecord = faq && typeof faq === "object" ? faq : {};
                    return (
                        payloadTextValue(faqRecord.question) !== "" &&
                        payloadRichTextValue(faqRecord.answer) !== ""
                    );
                });
                return sectionHasUserDelta(section) && hasCompleteFaqRow;
            }

            var pillBuilder = section.querySelector("[data-pill-builder]");
            if (pillBuilder) {
                var pillItems = parseBuilderPayloadArray(pillBuilder);
                var hasPillItem = pillItems.some(function anyPillValue(value) {
                    return payloadTextValue(value) !== "";
                });
                return sectionHasUserDelta(section) && hasPillItem;
            }

            var controls = Array.prototype.slice.call(section.querySelectorAll("input, select, textarea"))
                .filter(isTrackableControl);
            if (controls.length === 0) {
                return sectionHasUserDelta(section) && section.querySelectorAll("[data-pill-item]").length > 0;
            }
            var requiredControls = controls.filter(function onlyRequired(control) {
                return !!control.required;
            });
            if (requiredControls.length > 0) {
                return sectionHasUserDelta(section) && requiredControls.every(controlHasValue);
            }
            var fillableControls = controls.filter(function onlyFillable(control) {
                return !isBooleanControl(control);
            });
            if (fillableControls.length > 0) {
                return sectionHasUserDelta(section) && fillableControls.every(controlHasValue);
            }
            if (section.querySelectorAll("[data-pill-item]").length > 0) {
                return sectionHasUserDelta(section);
            }
            return sectionHasUserDelta(section) && controls.some(controlHasValue);
        }

        function syncProgressTopOffset() {
            var header = document.querySelector(".site-header");
            var headerHeight = header ? Math.ceil(header.getBoundingClientRect().height) : 0;
            var topOffset = Math.max(8, headerHeight + 8);
            document.documentElement.style.setProperty("--trip-progress-top", String(topOffset) + "px");
        }

        function syncIndexCompletion(completionMap) {
            var indexLinks = Array.prototype.slice.call(
                document.querySelectorAll(".trip-form-index-link[data-index-target]")
            );
            indexLinks.forEach(function eachLink(link) {
                var targetId = String(link.getAttribute("data-index-target") || "").trim();
                var isComplete = !!completionMap[targetId];
                link.classList.toggle("is-complete", isComplete);
            });
        }

        function updateProgress() {
            var completionMap = {};
            var completedCount = 0;
            sections.forEach(function eachSection(section) {
                var isComplete = sectionIsComplete(section);
                completionMap[String(section.id || "")] = isComplete;
                if (isComplete) {
                    completedCount += 1;
                }
            });
            var totalCount = sections.length;
            var percent = Math.round((completedCount / totalCount) * 100);
            var ratio = Math.max(0, Math.min(1, percent / 100));

            if (ringCircumference > 0) {
                progressRing.style.strokeDashoffset = String(ringCircumference * (1 - ratio));
            }
            progressShell.setAttribute("aria-valuenow", String(percent));
            progressPercentNodes.forEach(function eachPercentNode(node) {
                node.textContent = String(percent) + "%";
            });
            progressSectionNodes.forEach(function eachSectionNode(node) {
                node.textContent = String(completedCount) + " / " + String(totalCount) + " sections";
            });
            syncIndexCompletion(completionMap);
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

        Array.prototype.slice.call(form.querySelectorAll("input, select, textarea"))
            .filter(isTrackableControl)
            .forEach(function captureControlBaseline(control) {
                baselineControlSignatures.set(control, controlSignature(control));
            });
        sections.forEach(function captureSectionBaseline(section) {
            baselinePillCounts.set(section, section.querySelectorAll("[data-pill-item]").length);
        });

        function markControlTouched(event) {
            var target = event.target;
            if (!target || typeof target.tagName !== "string") {
                return;
            }
            var tag = String(target.tagName || "").toLowerCase();
            if (tag !== "input" && tag !== "select" && tag !== "textarea") {
                return;
            }
            if (!isTrackableControl(target)) {
                return;
            }
            touchedControls.add(target);
        }

        form.addEventListener("input", markControlTouched, true);
        form.addEventListener("change", markControlTouched, true);
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
    initRichTextEditors(form);
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
