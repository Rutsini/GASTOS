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

const subcategoryCategories = readJsonData("subcategory-categories-data", {});
        const subEditor = document.getElementById("subcategory-category-editor");
        const subEditorTitle = document.getElementById("subcategory-category-title");
        const subEditorId = document.getElementById("subcategory-category-id");
        const subEditorName = document.getElementById("subcategory-category-name");
        const subEditorActive = document.getElementById("subcategory-category-active");
        const subEditorChecks = subEditor ? Array.from(subEditor.querySelectorAll('input[name="categoria_ids"]')) : [];
        document.querySelectorAll(".edit-subcategory-categories").forEach((button) => {
            button.addEventListener("click", () => {
                const row = button.closest(".subcategory-edit-row");
                const subcategoryId = button.dataset.subcategoryId;
                const selected = new Set((subcategoryCategories[subcategoryId] || []).map(String));
                subEditorId.value = subcategoryId;
                subEditorName.value = row.querySelector('input[name="nombre"]').value;
                subEditorActive.value = row.querySelector('select[name="activa"]').value;
                subEditorTitle.textContent = "Editar categorías de " + button.dataset.subcategoryName;
                subEditorChecks.forEach((check) => {
                    check.checked = selected.has(check.value);
                });
                subEditor.hidden = false;
                subEditor.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        });
