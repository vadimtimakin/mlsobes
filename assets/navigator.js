// Навигатор вопросов ML Clan — standalone (данные через fetch, монтаж в
// #navigator-root). По умолчанию показывает ВСЁ: без пресетов, все направления
// выбраны. Фильтры: сектор, компания, отдел, тема, направления, поиск,
// сортировка, минимум интервью, этап, показывать.
(async function () {
  "use strict";

  const DATA_PATH = "assets/navigator-data.json";
  const STORAGE_KEY = "ml-clan-navigator-state-v2";
  const ALL_DIRECTIONS = ["llm", "nlp", "cv", "recsys", "ranking", "search", "deep_learning"];

  const mount = document.getElementById("navigator-root");
  if (!mount) return;

  function fail(msg) {
    const p = document.createElement("p");
    p.className = "mlcn-empty";
    p.textContent = msg;
    mount.appendChild(p);
  }

  let data;
  try {
    const resp = await fetch(DATA_PATH);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    data = await resp.json();
  } catch (error) {
    fail("Не удалось загрузить данные навигатора: " + error.message);
    return;
  }

  const root = document.createElement("div");
  root.className = "ml-clan-nav";
  mount.appendChild(root);

  const interviewById = new Map(data.interviews.map((item) => [Number(item.id), item]));
  const domainLabel = new Map(data.catalog.domains.map((item) => [item.id, item.label]));
  const poolLabel = new Map(data.catalog.pools.map((item) => [item.id, item.label]));

  const defaultState = {
    sector: "", company: "", department: "", stage: "", pool: "",
    query: "", directions: ALL_DIRECTIONS.slice(), minInterviews: 1,
    sort: "coverage", limit: 100
  };

  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch (_) { stored = {}; }
  const state = { ...defaultState, ...stored };
  // directions — множество ВЫБРАННЫХ (показываемых) направлений; по умолчанию все
  state.directions = new Set(Array.isArray(state.directions) ? state.directions : ALL_DIRECTIONS);

  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...state, directions: [...state.directions] }));
  }

  function element(tag, options = {}, children = []) {
    const node = document.createElement(tag);
    if (options.cls) node.className = options.cls;
    if (options.text !== undefined) node.textContent = options.text;
    if (options.type) node.type = options.type;
    if (options.value !== undefined) node.value = String(options.value);
    if (options.placeholder) node.placeholder = options.placeholder;
    if (options.min !== undefined) node.min = String(options.min);
    if (options.max !== undefined) node.max = String(options.max);
    if (options.checked !== undefined) node.checked = Boolean(options.checked);
    const list = Array.isArray(children) ? children : [children];
    for (const child of list) {
      if (child === null || child === undefined) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function option(value, label) { return element("option", { value, text: label }); }

  function replaceOptions(select, items, current, emptyLabel) {
    select.replaceChildren(option("", emptyLabel));
    for (const item of items) select.append(option(item.value, item.label));
    const valid = [...select.options].some((item) => item.value === current);
    select.value = valid ? current : "";
    return select.value;
  }

  function labeledControl(labelText, control) {
    const label = element("label", { cls: "mlcn-field" });
    label.append(element("span", { cls: "mlcn-label", text: labelText }), control);
    return label;
  }

  function createSelect() { return element("select", { cls: "dropdown mlcn-select" }); }

  const controls = element("div", { cls: "mlcn-controls" });
  const directions = element("div", { cls: "mlcn-directions" });
  const summary = element("div", { cls: "mlcn-summary" });
  const results = element("div", { cls: "mlcn-results" });
  root.append(controls, directions, summary, results);

  const sectorSelect = createSelect();
  const companySelect = createSelect();
  const departmentSelect = createSelect();
  const stageSelect = createSelect();
  const poolSelect = createSelect();
  const sortSelect = createSelect();
  const limitSelect = createSelect();
  const minInterviewsInput = element("input", { cls: "mlcn-number", type: "number", min: 1, max: 999, value: state.minInterviews });
  const queryInput = element("input", { cls: "mlcn-query", type: "search", value: state.query, placeholder: "Например: ROC-AUC или leakage" });

  controls.append(
    labeledControl("Сектор", sectorSelect),
    labeledControl("Компания", companySelect),
    labeledControl("Отдел / команда", departmentSelect),
    labeledControl("Тема", poolSelect),
    labeledControl("Поиск по вопросу", queryInput),
    labeledControl("Сортировка", sortSelect),
    labeledControl("Минимум интервью", minInterviewsInput),
    labeledControl("Этап", stageSelect),
    labeledControl("Показывать", limitSelect)
  );

  replaceOptions(sectorSelect, data.catalog.sectors.map((i) => ({ value: i.id, label: i.label })), state.sector, "Все секторы");
  replaceOptions(poolSelect, data.catalog.pools.map((i) => ({ value: i.id, label: i.label })), state.pool, "Все темы");
  replaceOptions(sortSelect, [
    { value: "coverage", label: "Компании → интервью → свежесть" },
    { value: "interviews", label: "Интервью → свежесть" },
    { value: "recent", label: "Сначала свежие" },
    { value: "alphabetical", label: "По алфавиту" }
  ], state.sort, "Сортировка");
  replaceOptions(limitSelect, [
    { value: "50", label: "50 вопросов" },
    { value: "100", label: "100 вопросов" },
    { value: "250", label: "250 вопросов" },
    { value: "0", label: "Все вопросы" }
  ], String(state.limit), "100 вопросов");

  // Направления — что показывать (по умолчанию все выбраны)
  directions.append(element("span", { cls: "mlcn-label", text: "Направления (показывать):" }));
  const directionChecks = new Map();
  for (const domain of ALL_DIRECTIONS) {
    const id = `mlcn-dir-${domain}`;
    const checkbox = element("input", { type: "checkbox", checked: state.directions.has(domain) });
    checkbox.id = id;
    const label = element("label", { cls: "mlcn-check" }, [checkbox, domainLabel.get(domain) || domain]);
    label.htmlFor = id;
    directions.append(label);
    directionChecks.set(domain, checkbox);
    checkbox.addEventListener("change", () => {
      checkbox.checked ? state.directions.add(domain) : state.directions.delete(domain);
      saveState(); renderResults();
    });
  }
  const dirToggle = element("button", { cls: "mlcn-dir-toggle", type: "button", text: "Сбросить" });
  directions.append(dirToggle);
  dirToggle.addEventListener("click", () => {
    const allOn = state.directions.size === ALL_DIRECTIONS.length;
    state.directions = new Set(allOn ? [] : ALL_DIRECTIONS);
    for (const [d, cb] of directionChecks) cb.checked = state.directions.has(d);
    dirToggle.textContent = allOn ? "Выбрать все" : "Сбросить";
    saveState(); renderResults();
  });

  function interviewsForMetadata() {
    return data.interviews.filter((interview) => {
      if (interview.source_kind !== "interview") return false;
      if (state.sector && interview.sector !== state.sector) return false;
      if (state.company && interview.company_id !== state.company) return false;
      return true;
    });
  }

  function refreshDependentOptions() {
    const companies = data.catalog.companies
      .filter((company) => company.id !== "unknown")
      .filter((company) => !state.sector || company.sector === state.sector)
      .sort((a, b) => a.name.localeCompare(b.name, "ru"))
      .map((company) => ({ value: company.id, label: company.name }));
    state.company = replaceOptions(companySelect, companies, state.company, "Все компании");

    const metadataInterviews = interviewsForMetadata();
    const departments = [...new Set(metadataInterviews.map((i) => i.department).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "ru")).map((value) => ({ value, label: value }));
    const stages = [...new Set(metadataInterviews.map((i) => i.stage).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "ru")).map((value) => ({ value, label: value }));
    state.department = replaceOptions(departmentSelect, departments, state.department, "Любой / не указан");
    state.stage = replaceOptions(stageSelect, stages, state.stage, "Любой / не указан");
  }

  function filteredInterviews() {
    return data.interviews.filter((interview) => {
      if (interview.source_kind !== "interview") return false;
      if (state.sector && interview.sector !== state.sector) return false;
      if (state.company && interview.company_id !== state.company) return false;
      if (state.department && interview.department !== state.department) return false;
      if (state.stage && interview.stage !== state.stage) return false;
      return true;
    });
  }

  function compareResults(left, right) {
    if (state.sort === "coverage") {
      return right.companyCount - left.companyCount
        || right.interviewCount - left.interviewCount
        || right.latest.localeCompare(left.latest)
        || left.question.text.localeCompare(right.question.text, "ru");
    }
    if (state.sort === "interviews") {
      return right.interviewCount - left.interviewCount
        || right.companyCount - left.companyCount
        || right.latest.localeCompare(left.latest)
        || left.question.text.localeCompare(right.question.text, "ru");
    }
    if (state.sort === "recent") {
      return right.latest.localeCompare(left.latest)
        || right.interviewCount - left.interviewCount
        || left.question.text.localeCompare(right.question.text, "ru");
    }
    return left.question.text.localeCompare(right.question.text, "ru");
  }

  function rankQuestions() {
    const allowedInterviews = filteredInterviews();
    const allowedIds = new Set(allowedInterviews.map((item) => Number(item.id)));
    const query = state.query.trim().toLocaleLowerCase("ru");
    const allDirsOn = state.directions.size === ALL_DIRECTIONS.length;
    const ranked = [];

    for (const question of data.questions) {
      if (state.pool && !question.pool_ids.includes(state.pool)) continue;
      // направления: показываем вопрос без тематики всегда, тематический —
      // если хотя бы одно его направление выбрано
      if (!allDirsOn && question.domains.length
          && !question.domains.some((d) => state.directions.has(d))) continue;
      if (query && !question.text.toLocaleLowerCase("ru").includes(query)) continue;

      const evidenceByInterview = new Map();
      for (const evidence of question.evidence) {
        const interviewId = Number(evidence.interview_id);
        if (!allowedIds.has(interviewId)) continue;
        if (!evidenceByInterview.has(interviewId)) evidenceByInterview.set(interviewId, []);
        evidenceByInterview.get(interviewId).push(Number(evidence.source_id));
      }
      if (evidenceByInterview.size < Number(state.minInterviews || 1)) continue;

      const matchedInterviews = [...evidenceByInterview.keys()]
        .map((id) => interviewById.get(id)).filter(Boolean);
      const companies = new Set(matchedInterviews.map((item) => item.company_id));
      const latest = matchedInterviews.map((item) => item.date || "").sort().at(-1) || "";
      ranked.push({
        question, evidenceByInterview, matchedInterviews,
        companyCount: companies.size, interviewCount: matchedInterviews.length, latest
      });
    }
    ranked.sort(compareResults);
    return { ranked, allowedInterviews };
  }

  function renderSourceDetails(item) {
    const details = element("details", { cls: "mlcn-details" });
    details.append(element("summary", { text: "Где спрашивали" }));
    const list = element("ul", { cls: "mlcn-sources" });
    const sorted = [...item.matchedInterviews].sort((a, b) =>
      (b.date || "").localeCompare(a.date || "") || a.company.localeCompare(b.company, "ru"));
    for (const interview of sorted) {
      const parts = [interview.company];
      if (interview.date) parts.push(interview.date);
      if (interview.department) parts.push(interview.department);
      if (interview.stage) parts.push(interview.stage);
      list.append(element("li", { text: parts.join(" · ") }));
    }
    details.append(list);
    return details;
  }

  function renderResults() {
    const { ranked, allowedInterviews } = rankQuestions();
    const allowedCompanies = new Set(allowedInterviews.map((item) => item.company_id));
    const limit = Number(state.limit || 0);
    const visible = limit > 0 ? ranked.slice(0, limit) : ranked;

    summary.replaceChildren();
    summary.append(
      element("strong", { text: `${ranked.length.toLocaleString("ru-RU")} вопросов` }),
      document.createTextNode(` · ${allowedInterviews.length} интервью · ${allowedCompanies.size} компаний`)
    );
    if (visible.length < ranked.length) {
      summary.append(document.createTextNode(` · показаны первые ${visible.length}`));
    }

    results.replaceChildren();
    if (!visible.length) {
      results.append(element("p", { cls: "mlcn-empty", text: "В этом срезе ничего не найдено. Ослабь фильтры или верни направления." }));
      return;
    }

    visible.forEach((item, index) => {
      const row = element("article", { cls: "mlcn-result" });
      const rank = element("div", { cls: "mlcn-rank", text: String(index + 1) });
      const body = element("div", { cls: "mlcn-result-body" });
      const question = element("div", { cls: "mlcn-question", text: item.question.text });
      const meta = element("div", { cls: "mlcn-meta" });
      meta.append(
        element("span", { cls: "mlcn-count", text: `${item.companyCount} комп.` }),
        element("span", { cls: "mlcn-count", text: `${item.interviewCount} собес.` })
      );
      if (item.latest) meta.append(element("span", { text: `последний: ${item.latest}` }));
      const topics = item.question.pool_ids.map((id) => poolLabel.get(id) || id).join(" · ");
      if (topics) meta.append(element("span", { text: topics }));
      body.append(question, meta, renderSourceDetails(item));
      row.append(rank, body);
      results.append(row);
    });
  }

  sectorSelect.addEventListener("change", () => {
    state.sector = sectorSelect.value; state.company = ""; state.department = ""; state.stage = "";
    refreshDependentOptions(); saveState(); renderResults();
  });
  companySelect.addEventListener("change", () => {
    state.company = companySelect.value; state.department = ""; state.stage = "";
    refreshDependentOptions(); saveState(); renderResults();
  });
  departmentSelect.addEventListener("change", () => { state.department = departmentSelect.value; saveState(); renderResults(); });
  stageSelect.addEventListener("change", () => { state.stage = stageSelect.value; saveState(); renderResults(); });
  poolSelect.addEventListener("change", () => { state.pool = poolSelect.value; saveState(); renderResults(); });
  sortSelect.addEventListener("change", () => { state.sort = sortSelect.value; saveState(); renderResults(); });
  limitSelect.addEventListener("change", () => { state.limit = Number(limitSelect.value); saveState(); renderResults(); });
  minInterviewsInput.addEventListener("change", () => {
    state.minInterviews = Math.max(1, Number(minInterviewsInput.value) || 1);
    minInterviewsInput.value = String(state.minInterviews); saveState(); renderResults();
  });
  let queryTimer;
  queryInput.addEventListener("input", () => {
    clearTimeout(queryTimer);
    queryTimer = setTimeout(() => { state.query = queryInput.value; saveState(); renderResults(); }, 180);
  });

  refreshDependentOptions();
  sectorSelect.value = state.sector;
  companySelect.value = state.company;
  departmentSelect.value = state.department;
  stageSelect.value = state.stage;
  poolSelect.value = state.pool;
  sortSelect.value = state.sort;
  limitSelect.value = String(state.limit);
  dirToggle.textContent = state.directions.size === ALL_DIRECTIONS.length ? "Сбросить" : "Выбрать все";
  renderResults();
})();
