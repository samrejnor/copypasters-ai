const form = document.querySelector("#form");
    const textInput = document.querySelector("#text");
    const status = document.querySelector("#status");
    const results = document.querySelector("#results");
    const count = document.querySelector("#count");
    const submitButton = document.querySelector("#submit");
    const testButton = document.querySelector("#test-cases");
    const testCollectionButton = document.querySelector("#test-collection");

    const themeSelect = document.querySelector("#theme");

    const categories = ["техника", "сеть", "помещение", "другое"];
    const priorities = ["высокий", "обычный"];
    let processedCount = 0;

    function applyTheme(theme) {
      if (theme === "violet") {
        document.documentElement.removeAttribute("data-theme");
      } else {
        document.documentElement.dataset.theme = theme;
      }
      themeSelect.value = theme;
      localStorage.setItem("dispatcher-theme", theme);
    }

    applyTheme(localStorage.getItem("dispatcher-theme") || "violet");
    themeSelect.addEventListener("change", () => applyTheme(themeSelect.value));

    function createSelect(values, originalValue, onChange) {
      const select = document.createElement("select");

      for (const value of values) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.append(option);
      }

      select.value = originalValue;
      select.addEventListener("change", onChange);
      return select;
    }

    function addResult(text, data, requestId = data.id, expected = {}) {
      document.querySelector("#empty-row")?.remove();

      const original = {
        category: data.category,
        priority: data.priority
      };

      const row = document.createElement("tr");

      const textCell = row.insertCell();
      textCell.textContent = text;

      const categoryCell = row.insertCell();
      const categorySelect = createSelect(categories, original.category, updateLabels);
      const categoryOriginal = document.createElement("small");
      categoryOriginal.className = "original";
      categoryCell.append(categorySelect, categoryOriginal);

      const priorityCell = row.insertCell();
      const prioritySelect = createSelect(priorities, original.priority, updateLabels);
      const priorityOriginal = document.createElement("small");
      priorityOriginal.className = "original";
      priorityCell.append(prioritySelect, priorityOriginal);

      const questionCell = row.insertCell();
      questionCell.textContent = data.question || "—";

      function updateLabels() {
        categoryOriginal.textContent = expected.category
          ? `Ответ модели: ${original.category} · Эталон: ${expected.category}`
          : categorySelect.value === original.category
            ? `Ответ модели: ${original.category}`
            : `${original.category} → ${categorySelect.value} (исправлено вручную)`;

        priorityOriginal.textContent = expected.priority
          ? `Ответ модели: ${original.priority} · Эталон: ${expected.priority}`
          : prioritySelect.value === original.priority
            ? `Ответ модели: ${original.priority}`
            : `${original.priority} → ${prioritySelect.value} (исправлено вручную)`;
      }

      async function persistReview() {
        try {
          await saveReview(requestId, categorySelect.value, prioritySelect.value);
          status.className = "";
          status.textContent = "Ручная проверка сохранена.";
        } catch (error) {
          status.className = "error";
          status.textContent = error.message;
        }
      }

      categorySelect.addEventListener("change", persistReview);
      prioritySelect.addEventListener("change", persistReview);

      updateLabels();
      results.prepend(row);

      processedCount += 1;
      count.textContent = `Обработано: ${processedCount}`;
    }


    async function classifyText(text, requestId = null) {
      const body = { text };
      if (requestId !== null) body.request_id = requestId;

      const response = await fetch("/api/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.error || `Ошибка API (${response.status})`);
      }

      if (
        !categories.includes(data.category) ||
        !priorities.includes(data.priority) ||
        typeof data.question !== "string"
      ) {
        throw new Error("API вернул ответ в неправильном формате.");
      }

      return data;
    }

    const collectionSelect = document.querySelector("#collection-select");
    const uploadInput = document.querySelector("#upload-json");

    async function loadCollections(selectedId = null) {
      const response = await fetch("/api/collections");
      const collections = await response.json();

      if (!response.ok) {
        throw new Error(collections.error || "Не удалось загрузить наборы.");
      }

      collectionSelect.replaceChildren();

      for (const collection of collections) {
        const option = document.createElement("option");
        option.value = collection.id;
        option.textContent = `${collection.name} (${collection.request_count})`;
        collectionSelect.append(option);
      }

      if (selectedId !== null) {
        collectionSelect.value = String(selectedId);
      }
    }

    async function saveReview(id, category, priority) {
      const response = await fetch(`/api/requests/${id}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, priority })
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || "Не удалось сохранить проверку.");
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = textInput.value.trim();
      if (!text) return;

      submitButton.disabled = true;
      status.className = "";
      status.textContent = "Обрабатываем…";

      try {
        const data = await classifyText(text);
        addResult(text, data, data.id);
        status.textContent = "Готово. Исходный ответ модели сохранён в строке.";
        form.reset();
      } catch (error) {
        status.className = "error";
        status.textContent = error.message;
      } finally {
        submitButton.disabled = false;
      }
    });

    loadCollections().catch((error) => {
    status.className = "error";
    status.textContent = error.message;
  });

  uploadInput.addEventListener("change", async () => {
    const file = uploadInput.files[0];
    if (!file) return;

    try {
      const items = JSON.parse(await file.text());

      if (!Array.isArray(items)) {
        throw new Error("JSON-файл должен содержать массив обращений.");
      }

      const name = file.name.replace(/\.json$/i, "");

      const response = await fetch("/api/collections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, requests: items })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Не удалось импортировать набор.");
      }

      await loadCollections(data.id);
      status.className = "";
      status.textContent = `Набор «${data.name}» добавлен.`;
    } catch (error) {
      status.className = "error";
      status.textContent = error.message;
    } finally {
      uploadInput.value = "";
    }
  });


    testCollectionButton.addEventListener("click", async () => {
    const collectionId = collectionSelect.value;

    if (!collectionId) {
      status.className = "error";
      status.textContent = "Сначала выберите набор обращений.";
      return;
    }

    testCollectionButton.disabled = true;
    testButton.disabled = true;
    submitButton.disabled = true;
    status.className = "";
    status.textContent = "Загружаем набор…";

    try {
      const response = await fetch(
        `/api/collections/${encodeURIComponent(collectionId)}/requests`
      );
      const items = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(items.error || "Не удалось загрузить обращения.");
      }

      if (!Array.isArray(items)) {
        throw new Error("Сервер вернул набор в неправильном формате.");
      }

      for (let index = 0; index < items.length; index += 1) {
        const item = items[index];

        if (!item || typeof item.text !== "string") {
          throw new Error(`Некорректное обращение в наборе (номер ${index + 1}).`);
        }

        status.textContent = `Обрабатываем: ${index + 1} из ${items.length}…`;

        const result = await classifyText(item.text, item.id);
        addResult(item.text, result, item.id, {
          category: item.review_category,
          priority: item.review_priority
        });
      }

      status.textContent = `Готово: обработано ${items.length} обращений.`;
    } catch (error) {
      status.className = "error";
      status.textContent = error.message;
    } finally {
      testCollectionButton.disabled = false;
      testButton.disabled = false;
      submitButton.disabled = false;
    }
  });

