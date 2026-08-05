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

    document.querySelectorAll("[data-confirm]").forEach(function (element) {
        element.addEventListener("click", function (event) {
            if (!window.confirm(element.getAttribute("data-confirm"))) {
                event.preventDefault();
                return;
            }
            const form = element.closest("form");
            if (form) {
                window.setTimeout(function () {
                    form.querySelectorAll("button").forEach(function (button) {
                        button.disabled = true;
                    });
                }, 0);
            }
        });
    });

    document.querySelectorAll(".js-card-amount, .js-card-installments, .js-card-installment-value").forEach(function (input) {
        input.addEventListener("input", updateFinancePreview);
    });
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
