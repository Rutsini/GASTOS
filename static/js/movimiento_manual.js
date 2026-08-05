const categoriaSelect = document.getElementById("categoria");
        const subcategoriaSelect = document.getElementById("subcategoria_id");
        function actualizarCategoriaReadonly() {
            const option = subcategoriaSelect?.selectedOptions?.[0];
            const categoria = option?.dataset?.categoria || "Sin categoría";
            if (categoriaSelect) categoriaSelect.value = categoria;
        }
        subcategoriaSelect?.addEventListener("change", actualizarCategoriaReadonly);
        actualizarCategoriaReadonly();
