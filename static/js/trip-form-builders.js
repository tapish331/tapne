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
                    meals: String(((row.querySelector("[data-day-meals]") || {}).value || "")).trim(),
                    activities: String(((row.querySelector("[data-day-activities]") || {}).value || "")).trim()
                };
            })
            .filter(function nonEmpty(day) {
                return day.title || day.description || day.stay || day.meals || day.activities;
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
            "<div class=\"trip-form-grid trip-form-grid-3\">" +
            "  <div class=\"form-field\"><label>Stay</label><input class=\"form-input\" type=\"text\" maxlength=\"180\" data-day-stay placeholder=\"e.g. Lakeside resort\"></div>" +
            "  <div class=\"form-field\"><label>Meals</label><input class=\"form-input\" type=\"text\" maxlength=\"180\" data-day-meals placeholder=\"e.g. Breakfast, Dinner\"></div>" +
            "  <div class=\"form-field\"><label>Activities</label><input class=\"form-input\" type=\"text\" maxlength=\"280\" data-day-activities placeholder=\"e.g. Village walk, bonfire night\"></div>" +
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
            ["[data-day-meals]", "meals"],
            ["[data-day-activities]", "activities"]
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
            var logoHost = section.querySelector(".trip-form-section-header .section-logo");
            if (logoHost) {
                sectionLogo = String(logoHost.textContent || "").trim();
            }

            var item = document.createElement("li");
            var link = document.createElement("a");
            link.className = "trip-form-index-link";
            link.href = "#" + sectionId;
            if (sectionLogo) {
                var logo = document.createElement("span");
                logo.className = "trip-form-index-logo";
                logo.setAttribute("aria-hidden", "true");
                logo.textContent = sectionLogo;
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
                return false;
            }
            var requiredControls = controls.filter(function onlyRequired(control) {
                return !!control.required;
            });
            if (requiredControls.length > 0) {
                return requiredControls.every(controlHasValue);
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

    var form = document.querySelector(".trip-creation-form");
    if (!form) {
        return;
    }

    initCollapsibleSections(form);
    initSectionIndex(form);
    initTripProgress(form);
    Array.prototype.slice.call(form.querySelectorAll("[data-list-builder]")).forEach(initListBuilder);
    Array.prototype.slice.call(form.querySelectorAll("[data-day-builder]")).forEach(initDayBuilder);
    Array.prototype.slice.call(form.querySelectorAll("[data-faq-builder]")).forEach(initFaqBuilder);

    form.addEventListener("submit", function onSubmit() {
        Array.prototype.slice.call(form.querySelectorAll("[data-list-builder]")).forEach(syncListBuilder);
        Array.prototype.slice.call(form.querySelectorAll("[data-day-builder]")).forEach(syncDayBuilder);
        Array.prototype.slice.call(form.querySelectorAll("[data-faq-builder]")).forEach(syncFaqBuilder);
    });
})();
