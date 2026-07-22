(function () {
    window.getJsonData = function getJsonData(elementId, fallback) {
        const element = document.getElementById(elementId);
        if (!element) {
            return fallback;
        }
        try {
            return JSON.parse(element.textContent || "");
        } catch (error) {
            console.warn("No se pudo leer JSON embebido", elementId, error);
            return fallback;
        }
    };

    const storageKey = "hideAmounts";
    const hiddenValue = "******";
    const moneyPattern = /-?\$[\d.]+,\d{2}/g;
    const originalText = new WeakMap();
    const skipTags = new Set(["SCRIPT", "STYLE", "INPUT", "TEXTAREA", "SELECT", "OPTION"]);
    const toggle = document.getElementById("toggle-amounts");

    function shouldHideAmounts() {
        return localStorage.getItem(storageKey) === "true";
    }

    window.formatAmount = function formatAmount(value) {
        if (shouldHideAmounts()) {
            return hiddenValue;
        }
        if (typeof value === "number" && Number.isFinite(value)) {
            const sign = value < 0 ? "-" : "";
            const abs = Math.abs(value);
            return sign + "$" + abs.toLocaleString("es-AR", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
        }
        return String(value);
    };

    function updateToggle(hidden) {
        if (!toggle) {
            return;
        }
        toggle.setAttribute("aria-pressed", hidden ? "true" : "false");
        toggle.querySelector(".amount-visibility-icon").textContent = "$";
        toggle.querySelector(".amount-visibility-label").textContent = hidden ? "Mostrar montos" : "Ocultar montos";
        document.body.classList.toggle("amounts-hidden", hidden);
    }

    function visitTextNodes(root, callback) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode(node) {
                const parent = node.parentElement;
                if (!parent || skipTags.has(parent.tagName)) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            },
        });
        let node = walker.nextNode();
        while (node) {
            callback(node);
            node = walker.nextNode();
        }
    }

    function updateCharts() {
        if (!window.Chart || !Chart.instances) {
            return;
        }
        Object.values(Chart.instances).forEach(function (chart) {
            chart.options.plugins = chart.options.plugins || {};
            chart.options.plugins.tooltip = chart.options.plugins.tooltip || {};
            chart.options.plugins.tooltip.callbacks = chart.options.plugins.tooltip.callbacks || {};
            chart.options.plugins.tooltip.callbacks.label = function (context) {
                const label = context.dataset.label || context.label || "";
                const value = window.formatAmount(Number(context.raw || 0));
                return label ? label + ": " + value : value;
            };
            Object.values(chart.options.scales || {}).forEach(function (scale) {
                scale.ticks = scale.ticks || {};
                scale.ticks.callback = function (value) {
                    return window.formatAmount(Number(value || 0));
                };
            });
            chart.update();
        });
    }

    function applyAmountVisibility() {
        const hidden = shouldHideAmounts();
        visitTextNodes(document.body, function (node) {
            const saved = originalText.get(node) || node.nodeValue;
            if (!moneyPattern.test(saved)) {
                moneyPattern.lastIndex = 0;
                return;
            }
            originalText.set(node, saved);
            moneyPattern.lastIndex = 0;
            node.nodeValue = hidden ? saved.replace(moneyPattern, hiddenValue) : saved;
        });
        updateCharts();
        updateToggle(hidden);
    }

    if (toggle) {
        toggle.addEventListener("click", function () {
            localStorage.setItem(storageKey, shouldHideAmounts() ? "false" : "true");
            applyAmountVisibility();
        });
    }

    applyAmountVisibility();
})();
