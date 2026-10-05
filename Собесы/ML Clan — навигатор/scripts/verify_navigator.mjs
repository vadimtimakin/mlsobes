import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";


const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const navRoot = path.dirname(scriptRoot);
const vaultRoot = path.dirname(navRoot);
const dataPath = path.join(navRoot, "data", "navigator-data.json");
const viewPath = path.join(navRoot, "view", "view.js");
const notePath = path.join(navRoot, "ML Clan — навигатор.md");
const dataviewSettingsPath = path.join(vaultRoot, ".obsidian", "plugins", "dataview", "data.json");


class FakeNode {
    constructor(tagName = "#text", text = "") {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.parentNode = null;
        this._text = text;
        this.className = "";
        this.attributes = {};
        this.listeners = new Map();
        this._classes = new Set();
        this.classList = {
            toggle: (name, force) => {
                const enabled = force === undefined ? !this._classes.has(name) : Boolean(force);
                enabled ? this._classes.add(name) : this._classes.delete(name);
                this.className = [...this._classes].join(" ");
                return enabled;
            }
        };
    }

    get textContent() {
        if (this.tagName === "#TEXT") return this._text;
        return this._text + this.children.map((child) => child.textContent).join("");
    }

    set textContent(value) {
        this._text = String(value ?? "");
        this.children = [];
    }

    get options() {
        return this.children.filter((child) => child.tagName === "OPTION");
    }

    append(...children) {
        for (const child of children) {
            const node = child instanceof FakeNode ? child : new FakeNode("#text", String(child));
            node.parentNode = this;
            this.children.push(node);
        }
    }

    appendChild(child) {
        this.append(child);
        return child;
    }

    replaceChildren(...children) {
        this.children = [];
        this._text = "";
        this.append(...children);
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    addEventListener(type, listener) {
        if (!this.listeners.has(type)) this.listeners.set(type, []);
        this.listeners.get(type).push(listener);
    }

    async dispatch(type) {
        for (const listener of this.listeners.get(type) || []) await listener({ target: this });
    }

    createDiv(options = {}) {
        const child = new FakeNode("div");
        child.className = options.cls || "";
        child._classes = new Set(child.className.split(/\s+/).filter(Boolean));
        this.append(child);
        return child;
    }

    findAll(tagName) {
        const wanted = tagName.toUpperCase();
        const own = this.tagName === wanted ? [this] : [];
        return own.concat(...this.children.map((child) => child.findAll(wanted)));
    }
}


const fakeDocument = {
    createElement(tagName) {
        return new FakeNode(tagName);
    },
    createTextNode(text) {
        return new FakeNode("#text", String(text));
    }
};

const fakeStorage = {
    values: new Map(),
    getItem(key) {
        return this.values.has(key) ? this.values.get(key) : null;
    },
    setItem(key, value) {
        this.values.set(key, String(value));
    }
};


const dataset = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const questionsById = new Map(dataset.questions.map((question) => [question.id, question]));
const interviewsById = new Map(dataset.interviews.map((interview) => [Number(interview.id), interview]));

assert.equal(questionsById.size, dataset.questions.length, "question ID должны быть уникальны");
assert.equal(dataset.summary.questions, dataset.questions.length);
assert.equal(dataset.summary.interviews, dataset.interviews.length);
assert.ok(dataset.questions.length > 2_000, "ожидалось больше 2 000 вопросов");
assert.ok(dataset.interviews.length > 150, "ожидалось больше 150 интервью");
for (const question of dataset.questions) {
    for (const evidence of question.evidence) {
        assert.ok(interviewsById.has(Number(evidence.interview_id)), `нет interview ${evidence.interview_id}`);
    }
}

const note = fs.readFileSync(notePath, "utf8");
assert.ok(note.includes("dv.current().file.folder"));
const dataviewSettings = JSON.parse(fs.readFileSync(dataviewSettingsPath, "utf8"));
assert.equal(dataviewSettings.enableDataviewJs, true, "DataviewJS должен быть включён");

for (const folder of ["ML Clan — навигатор", "Собесы/ML Clan — навигатор", "Other/Renamed folder/Navigator"]) {
const container = new FakeNode("div");
const errors = [];
const dv = {
    container,
    current: () => ({ file: { folder } }),
    io: {
        async load(requestedPath) {
            assert.equal(requestedPath, `${folder}/data/navigator-data.json`);
            return fs.readFileSync(dataPath, "utf8");
        }
    },
    paragraph(message) {
        errors.push(String(message));
    }
};

const noteCode = note.match(/```dataviewjs\r?\n([\s\S]*?)```/)[1];
await new (Object.getPrototypeOf(async function () {}).constructor)("dv", noteCode)({
    current: dv.current,
    async view(requestedPath) { assert.equal(requestedPath, `${folder}/view`); }
});
fakeStorage.values.clear();
const source = fs.readFileSync(viewPath, "utf8");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const runView = new AsyncFunction("dv", "document", "Node", "localStorage", source);
await runView(dv, fakeDocument, FakeNode, fakeStorage);

assert.deepEqual(errors, [], "view не должен выводить ошибки");
assert.equal(container.findAll("button").length, 6, "ожидалось шесть пресетов");
assert.equal(container.findAll("article").length, 100, "по умолчанию выводятся первые 100 вопросов");

const summaryNode = container.findAll("div").find((node) => node.className.includes("mlcn-summary"));
assert.ok(summaryNode?.textContent.includes("вопрос"), "summary должен содержать число вопросов");

const livecodingButton = container.findAll("button").find((node) => node.textContent === "Лайвкодинг");
assert.ok(livecodingButton, "не найден пресет лайвкодинга");
await livecodingButton.dispatch("click");
assert.match(summaryNode.textContent, /^63 вопрос/);

const bankButton = container.findAll("button").find((node) => node.textContent === "Все банки");
assert.ok(bankButton, "не найден банковский пресет");
await bankButton.dispatch("click");
assert.match(summaryNode.textContent, /^848 вопросов/);

const bankClassicButton = container.findAll("button").find((node) => node.textContent.startsWith("Банки без"));
await bankClassicButton.dispatch("click");
assert.match(summaryNode.textContent, /^612 вопросов/);

const sberButton = container.findAll("button").find((node) => node.textContent === "Только Сбер");
await sberButton.dispatch("click");
assert.match(summaryNode.textContent, /^355 вопросов/);

console.log(JSON.stringify({
    status: "OK",
    folder,
    questions: dataset.questions.length,
    interviews: dataset.interviews.length,
    rendered_rows: container.findAll("article").length,
    presets_checked: ["Лайвкодинг", "Все банки", "Банки без специализированных доменов", "Только Сбер"]
}, null, 2));

}
