document.getElementById("chk_all")?.addEventListener("change", function(e) {
            document.querySelectorAll(".chk_row").forEach(cb => cb.checked = e.target.checked);
        });

        document.querySelectorAll(".movement-edit-actions").forEach(actions => {
            const row = actions.closest("tr");
            const movId = actions.dataset.movId;
            const subCell = row?.querySelector(".movement-subcategory-cell");
            const subLabel = subCell?.querySelector(".movement-subcategory-label");
            const subSelect = subCell?.querySelector(".movement-subcategory-select");
            const status = subCell?.querySelector(".category-save-status");
            const editBtn = actions.querySelector(".movement-edit-btn");
            const saveBtn = actions.querySelector(".movement-save-btn");
            const cancelBtn = actions.querySelector(".movement-cancel-btn");
            const originalValue = subSelect?.value || "";

            function setEditing(editing) {
                subLabel.hidden = editing;
                subSelect.hidden = !editing;
                editBtn.hidden = editing;
                saveBtn.hidden = !editing;
                cancelBtn.hidden = !editing;
                if (status && !editing) status.textContent = "";
            }

            editBtn?.addEventListener("click", () => setEditing(true));
            cancelBtn?.addEventListener("click", () => {
                if (subSelect) subSelect.value = originalValue;
                setEditing(false);
            });
            saveBtn?.addEventListener("click", async () => {
                status.textContent = "Guardando...";
                status.className = "category-save-status muted";
                saveBtn.disabled = true;
                row?.classList.remove("category-save-ok", "category-save-error");
                try {
                    const response = await fetch(`/movimientos/${movId}/subcategoria`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ subcategoria_id: subSelect?.value || "" })
                    });
                    const data = await response.json();
                    if (!response.ok || !data.ok) {
                        throw new Error(data.mensaje || "No se pudo actualizar");
                    }
                    const categoryCell = row.querySelector(".movement-category-cell");
                    categoryCell.textContent = "";
                    if (data.pendiente) {
                        const pending = document.createElement("span");
                        pending.className = "badge pending";
                        pending.textContent = "Pendiente";
                        const category = document.createElement("span");
                        category.className = "badge neutral";
                        category.textContent = data.categoria;
                        categoryCell.append(pending, " ", category);
                    } else {
                        const category = document.createElement("span");
                        category.className = "badge classified";
                        category.textContent = data.categoria;
                        categoryCell.append(category);
                    }
                    if (data.tipo_categoria === "cambio_efectivo") {
                        const cash = document.createElement("span");
                        cash.className = "badge cash-move";
                        cash.textContent = "Cambio de efectivo";
                        categoryCell.append(" ", cash);
                    }
                    subLabel.textContent = data.subcategoria;
                    const originCell = row.querySelector(".movement-origin-cell");
                    originCell.textContent = "";
                    const origin = document.createElement("span");
                    origin.className = "badge origin-manual";
                    origin.textContent = "🔒 Manual";
                    originCell.append(origin);
                    status.textContent = "Guardado";
                    status.className = "category-save-status category-save-success";
                    row?.classList.add("category-save-ok");
                    setEditing(false);
                } catch (error) {
                    status.textContent = error.message || "Error";
                    status.className = "category-save-status category-save-fail";
                    row?.classList.add("category-save-error");
                } finally {
                    saveBtn.disabled = false;
                }
            });
        });
