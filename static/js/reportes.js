function readJsonData(elementId, fallback) {
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
}

const chartData = readJsonData("report-chart-data", {});

function hasNumericData(values) {
    return Array.isArray(values) && values.some((value) => Number.isFinite(Number(value)) && Number(value) !== 0);
}

function formatReportAmount(value) {
    const number = Number(value || 0);
    const sign = number < 0 ? "-" : "";
    return sign + "$" + Math.abs(number).toLocaleString("es-AR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
        return {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
        }[char];
    });
}

function toggleChart(canvasId, emptyId, showChart) {
    const canvas = document.getElementById(canvasId);
    const empty = document.getElementById(emptyId);
    if (!canvas || !empty) {
        return;
    }
    canvas.classList.toggle("chart-hidden", !showChart);
    empty.classList.toggle("chart-hidden", showChart);
    canvas.hidden = !showChart;
    empty.hidden = showChart;
    canvas.style.display = showChart ? "" : "none";
    empty.style.display = showChart ? "none" : "flex";
}

function showFallback(canvasId, emptyId, hasData, html) {
    toggleChart(canvasId, emptyId, false);
    const empty = document.getElementById(emptyId);
    if (!empty) {
        return;
    }
    empty.classList.toggle("chart-empty", !hasData);
    empty.classList.toggle("chart-fallback", hasData);
    empty.innerHTML = hasData ? html : "No hay datos para mostrar";
    empty.hidden = false;
    empty.style.display = hasData ? "block" : "flex";
}

function fallbackMonthlyBars(labels, ingresos, gastos, ahorro) {
    const rows = labels.map(function (label, index) {
        const ingreso = Number(ingresos[index] || 0);
        const gasto = Number(gastos[index] || 0);
        const ahorroMes = Number(ahorro[index] || 0);
        const max = Math.max(Math.abs(ingreso), Math.abs(gasto), Math.abs(ahorroMes), 1);
        return (
            '<div class="chart-fallback-row">' +
                '<div class="chart-fallback-label">' + escapeHtml(label) + '</div>' +
                '<div class="chart-fallback-bars">' +
                    '<span class="chart-bar income" style="width:' + Math.max(4, Math.abs(ingreso) / max * 100) + '%">' + formatReportAmount(ingreso) + '</span>' +
                    '<span class="chart-bar expense" style="width:' + Math.max(4, Math.abs(gasto) / max * 100) + '%">' + formatReportAmount(gasto) + '</span>' +
                    '<span class="chart-bar savings" style="width:' + Math.max(4, Math.abs(ahorroMes) / max * 100) + '%">' + formatReportAmount(ahorroMes) + '</span>' +
                '</div>' +
            '</div>'
        );
    }).join("");
    return '<div class="chart-fallback-legend"><span>Ingresos</span><span>Gastos</span><span>Ahorro</span></div>' + rows;
}

function fallbackList(labels, values) {
    const total = values.reduce(function (acc, value) {
        return acc + Math.abs(Number(value || 0));
    }, 0) || 1;
    return labels.map(function (label, index) {
        const value = Number(values[index] || 0);
        return (
            '<div class="chart-fallback-row compact">' +
                '<div class="chart-fallback-label">' + escapeHtml(label) + '</div>' +
                '<strong>' + formatReportAmount(value) + '</strong>' +
                '<div class="chart-fallback-meter"><span style="width:' + Math.max(4, Math.abs(value) / total * 100) + '%"></span></div>' +
            '</div>'
        );
    }).join("");
}

function renderReportCharts() {
    const monthlyChartOption = {
        labels: Array.isArray(chartData.meses) ? chartData.meses : [],
        ingresos: Array.isArray(chartData.ingresos) ? chartData.ingresos : [],
        gastos: Array.isArray(chartData.gastos) ? chartData.gastos : [],
        ahorro: Array.isArray(chartData.ahorro) ? chartData.ahorro : [],
    };
    const hasMonthlyData = hasNumericData(monthlyChartOption.ingresos)
        || hasNumericData(monthlyChartOption.gastos)
        || hasNumericData(monthlyChartOption.ahorro);

    const donutRawLabels = Array.isArray(chartData.categorias_gasto) ? chartData.categorias_gasto : [];
    const donutRawData = Array.isArray(chartData.gastos_categoria) ? chartData.gastos_categoria : [];
    const donutItems = donutRawData
        .map((value, index) => ({ label: donutRawLabels[index], value: Number(value) }))
        .filter((item) => item.label && Number.isFinite(item.value) && item.value > 0);
    const donutLabels = donutItems.map((item) => item.label);
    const donutDataset = donutItems.map((item) => item.value);
    const hasDonut = donutLabels.length > 0 && donutDataset.length > 0;

    const balanceLabels = Array.isArray(chartData.meses) ? chartData.meses : [];
    const balanceData = Array.isArray(chartData.disponible) ? chartData.disponible : [];
    const hasBalance = balanceLabels.length > 0 && balanceData.some((value) => Number.isFinite(Number(value)));

    if (!window.Chart) {
        showFallback(
            "barMes",
            "barMesEmpty",
            hasMonthlyData,
            fallbackMonthlyBars(monthlyChartOption.labels, monthlyChartOption.ingresos, monthlyChartOption.gastos, monthlyChartOption.ahorro)
        );
        showFallback("donutCategorias", "donutCategoriasEmpty", hasDonut, fallbackList(donutLabels, donutDataset));
        showFallback("lineBalance", "lineBalanceEmpty", hasBalance, fallbackList(balanceLabels, balanceData));
        return;
    }

    toggleChart("barMes", "barMesEmpty", hasMonthlyData);
    if (hasMonthlyData) {
        new Chart(document.getElementById("barMes"), {
            type: "bar",
            data: {
                labels: monthlyChartOption.labels,
                datasets: [
                    { label: "Ingresos", data: monthlyChartOption.ingresos, backgroundColor: "#16a34a" },
                    { label: "Gastos", data: monthlyChartOption.gastos, backgroundColor: "#dc2626" },
                    {
                        label: "Ahorro",
                        data: monthlyChartOption.ahorro,
                        type: "line",
                        borderColor: "#6366f1",
                        backgroundColor: "#6366f1",
                        tension: 0.2,
                    },
                ],
            },
            options: { responsive: true, scales: { y: { beginAtZero: true } } },
        });
    }

    toggleChart("donutCategorias", "donutCategoriasEmpty", hasDonut);
    if (hasDonut) {
        new Chart(document.getElementById("donutCategorias"), {
            type: "doughnut",
            data: {
                labels: donutLabels,
                datasets: [{
                    data: donutDataset,
                    backgroundColor: ["#dc2626", "#f97316", "#eab308", "#0ea5e9", "#7c3aed", "#64748b"],
                }],
            },
            options: { responsive: true },
        });
    }

    toggleChart("lineBalance", "lineBalanceEmpty", hasBalance);
    if (hasBalance) {
        new Chart(document.getElementById("lineBalance"), {
            type: "line",
            data: {
                labels: balanceLabels,
                datasets: [{
                    label: "Disponible",
                    data: balanceData,
                    borderColor: "#004481",
                    backgroundColor: "#004481",
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    tension: 0.2,
                }],
            },
            options: { responsive: true, scales: { y: { beginAtZero: false } } },
        });
    }
}

renderReportCharts();
