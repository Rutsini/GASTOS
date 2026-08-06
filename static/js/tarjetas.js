(function () {
    function parseMoney(value) {
        const text = String(value || "").replace(/\$/g, "").replace(/\s/g, "");
        if (!text) {
            return null;
        }
        const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
        const number = Number(normalized);
        return Number.isFinite(number) ? Math.round(number * 100) : null;
    }

    function formatMoney(centavos) {
        if (!Number.isFinite(centavos)) {
            return "-";
        }
        const sign = centavos < 0 ? "-" : "";
        return sign + "$" + (Math.abs(centavos) / 100).toLocaleString("es-AR", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function updateFinancePreview() {
        const amountInput = document.querySelector(".js-card-amount");
        const installmentsInput = document.querySelector(".js-card-installments");
        const installmentValueInput = document.querySelector(".js-card-installment-value");
        if (!amountInput || !installmentsInput) {
            return;
        }
        const amount = parseMoney(amountInput.value);
        const installments = Number(installmentsInput.value || 0);
        const manualInstallment = parseMoney(installmentValueInput && installmentValueInput.value);
        const cuotaNode = document.querySelector('[data-card-preview="cuota"]');
        const totalNode = document.querySelector('[data-card-preview="total"]');
        const diffNode = document.querySelector('[data-card-preview="diferencia"]');
        if (!amount || installments <= 0) {
            [cuotaNode, totalNode, diffNode].forEach(function (node) {
                if (node) node.textContent = "-";
            });
            return;
        }
        const cuota = manualInstallment || Math.floor(amount / installments);
        const total = manualInstallment ? manualInstallment * installments : amount;
        if (cuotaNode) cuotaNode.textContent = formatMoney(cuota);
        if (totalNode) totalNode.textContent = formatMoney(total);
        if (diffNode) diffNode.textContent = formatMoney(total - amount);
    }

    function updateSubscriptionMode() {
        const toggle = document.querySelector(".js-card-subscription-toggle");
        if (!toggle) {
            return;
        }
        const enabled = toggle.checked;
        document.querySelectorAll(".js-installment-only").forEach(function (group) {
            group.hidden = enabled;
            group.querySelectorAll("input, select, textarea").forEach(function (field) {
                field.disabled = enabled;
            });
        });
        const amountLabel = document.querySelector('[data-card-label="monto"]');
        if (amountLabel) {
            amountLabel.textContent = enabled ? "Monto mensual" : "Monto original";
        }
        const submit = document.querySelector("[data-card-submit-label]");
        if (submit) {
            submit.textContent = enabled ? "Crear suscripcion" : "Crear compra y cuotas";
        }
    }

    document.querySelectorAll("[data-confirm]").forEach(function (element) {
        element.addEventListener("click", function (event) {
            if (!window.confirm(element.getAttribute("data-confirm"))) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll("[data-dialog-target]").forEach(function (button) {
        button.addEventListener("click", function () {
            const dialog = document.getElementById(button.getAttribute("data-dialog-target"));
            if (!dialog) {
                return;
            }
            if (typeof dialog.showModal === "function") {
                dialog.showModal();
            } else {
                dialog.setAttribute("open", "");
            }
        });
    });

    document.querySelectorAll(".subscription-dialog, .entity-dialog").forEach(function (dialog) {
        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) {
                if (typeof dialog.close === "function") {
                    dialog.close();
                } else {
                    dialog.removeAttribute("open");
                }
            }
        });
        dialog.querySelectorAll("[data-dialog-close]").forEach(function (button) {
            button.addEventListener("click", function () {
                if (typeof dialog.close === "function") {
                    dialog.close();
                } else {
                    dialog.removeAttribute("open");
                }
            });
        });
    });

    function setupStatusFilter(filter) {
        const name = filter.getAttribute("data-status-filter");
        const list = document.querySelector('[data-status-filter-list="' + name + '"]');
        if (!list) {
            return;
        }
        const items = Array.from(list.querySelectorAll("[data-status-filter-item]"));
        const buttons = Array.from(filter.querySelectorAll("[data-status-filter-option]"));
        const categorySelect = filter.querySelector('[data-category-filter="' + name + '"]');
        const empty = document.querySelector('[data-status-filter-empty="' + name + '"]');
        const statusStorageKey = "status-filter-" + name;
        const categoryStorageKey = "category-filter-" + name;
        const validStatuses = new Set(buttons.map(function (button) {
            return button.getAttribute("data-status-filter-option");
        }));
        const fallback = filter.getAttribute("data-default-status") || "all";
        let selectedStatus = sessionStorage.getItem(statusStorageKey) || fallback;
        let selectedCategory = sessionStorage.getItem(categoryStorageKey) || "all";
        if (!validStatuses.has(selectedStatus)) {
            selectedStatus = fallback;
        }
        if (items.length === 0) {
            selectedStatus = "all";
            selectedCategory = "all";
        }
        if (categorySelect) {
            const hasUncategorized = items.some(function (item) {
                return !(item.getAttribute("data-category") || "").trim();
            });
            const uncategorizedOption = categorySelect.querySelector("[data-uncategorized-option]");
            if (uncategorizedOption) {
                uncategorizedOption.hidden = !hasUncategorized;
            }
            const validCategories = new Set(Array.from(categorySelect.options).filter(function (option) {
                return !option.hidden;
            }).map(function (option) {
                return option.value;
            }));
            if (!validCategories.has(selectedCategory)) {
                selectedCategory = "all";
            }
            categorySelect.value = selectedCategory;
        }

        function updateCounts() {
            const counts = { all: items.length };
            items.forEach(function (item) {
                const status = item.getAttribute("data-status") || "";
                counts[status] = (counts[status] || 0) + 1;
            });
            filter.querySelectorAll("[data-status-count]").forEach(function (counter) {
                const status = counter.getAttribute("data-status-count");
                counter.textContent = counts[status] || 0;
            });
        }

        function categoryLabel() {
            if (!categorySelect || selectedCategory === "all") {
                return "";
            }
            const option = categorySelect.selectedOptions[0];
            return option ? option.textContent.trim() : "";
        }

        function selectedButton() {
            return buttons.find(function (button) {
                return button.getAttribute("data-status-filter-option") === selectedStatus;
            });
        }

        function buildEmptyMessage() {
            const category = categoryLabel();
            const button = selectedButton();
            if (category) {
                const entity = filter.getAttribute("data-entity-label") || "resultados";
                const statusText = selectedStatus === "all" ? "" : (button ? button.firstChild.nodeValue.trim().toLowerCase() : "");
                return "No hay " + entity + (statusText ? " " + statusText : "") + " en la categoria " + category + ".";
            }
            return (button && button.getAttribute("data-empty-message")) || "No hay resultados para este filtro.";
        }

        function apply() {
            sessionStorage.setItem(statusStorageKey, selectedStatus);
            sessionStorage.setItem(categoryStorageKey, selectedCategory);
            let visible = 0;
            items.forEach(function (item) {
                const statusMatches = selectedStatus === "all" || item.getAttribute("data-status") === selectedStatus;
                const itemCategory = (item.getAttribute("data-category") || "").trim();
                const categoryMatches = selectedCategory === "all" ||
                    (selectedCategory === "__uncategorized" ? !itemCategory : itemCategory === selectedCategory);
                const visibleItem = statusMatches && categoryMatches;
                item.hidden = !visibleItem;
                if (visibleItem) {
                    visible += 1;
                }
            });
            buttons.forEach(function (button) {
                button.setAttribute("aria-pressed", button.getAttribute("data-status-filter-option") === selectedStatus ? "true" : "false");
            });
            if (empty) {
                empty.hidden = visible !== 0;
                empty.textContent = buildEmptyMessage();
            }
        }

        buttons.forEach(function (button) {
            button.addEventListener("click", function () {
                selectedStatus = button.getAttribute("data-status-filter-option");
                apply();
            });
        });
        if (categorySelect) {
            categorySelect.addEventListener("change", function () {
                selectedCategory = categorySelect.value || "all";
                apply();
            });
        }
        updateCounts();
        apply();
    }

    document.querySelectorAll("[data-status-filter]").forEach(setupStatusFilter);

    document.querySelectorAll("form").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (form.dataset.submitting === "1") {
                event.preventDefault();
                return;
            }
            form.dataset.submitting = "1";
            const submitter = event.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
            form.querySelectorAll("button").forEach(function (button) {
                button.disabled = true;
            });
            if (submitter && submitter.tagName === "BUTTON") {
                submitter.textContent = submitter.getAttribute("data-loading-text") || "Procesando...";
            }
        });
    });

    document.querySelectorAll(".js-card-amount, .js-card-installments, .js-card-installment-value").forEach(function (input) {
        input.addEventListener("input", updateFinancePreview);
    });
    document.querySelectorAll(".js-card-subscription-toggle").forEach(function (input) {
        input.addEventListener("change", updateSubscriptionMode);
    });
    updateSubscriptionMode();
    updateFinancePreview();

    const category = document.querySelector(".js-card-category");
    const subcategory = document.querySelector(".js-card-subcategory");
    if (category && subcategory) {
        category.addEventListener("change", function () {
            const selected = category.value;
            Array.from(subcategory.options).forEach(function (option) {
                const optionCategory = option.getAttribute("data-categoria") || "";
                option.hidden = Boolean(option.value) && Boolean(selected) && optionCategory !== selected;
            });
            if (subcategory.selectedOptions[0] && subcategory.selectedOptions[0].hidden) {
                subcategory.value = "";
            }
        });
        category.dispatchEvent(new Event("change"));
    }
})();
