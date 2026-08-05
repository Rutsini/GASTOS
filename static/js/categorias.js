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

const categorySubcategories = readJsonData("category-subcategories-data", {});
        const editor = document.getElementById("category-subcategory-editor");
        const editorTitle = document.getElementById("category-subcategory-title");
        const editorInput = document.getElementById("category-subcategory-id");
        const editorChecks = editor ? Array.from(editor.querySelectorAll('input[name="subcategoria_ids"]')) : [];
        document.querySelectorAll(".edit-category-subcategories").forEach((button) => {
            button.addEventListener("click", () => {
                const categoryId = button.dataset.categoryId;
                const selected = new Set((categorySubcategories[categoryId] || []).map(String));
                editorInput.value = categoryId;
                editorTitle.textContent = "Editar subcategorías de " + button.dataset.categoryName;
                editorChecks.forEach((check) => {
                    check.checked = selected.has(check.value);
                });
                editor.hidden = false;
                editor.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        });
