import { test, expect, type Page } from "@playwright/test";

async function saveSources(page: Page, content: string) {
  await page.getByRole("button", { name: "MELD", exact: true }).click();
  const source = page.getByRole("textbox", {
    name: "deontic_rules.meld",
    exact: true,
  });
  await source.fill(content);
  await page
    .getByRole("button", { name: "Check and save draft", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "MELD draft saved" }),
  ).toBeVisible();
}

const source = `(aegis-schema-version 1)
(case WorkshopRules)
(permittedToDo-WRT WorkshopCode operator (inspectArtifact))
(forbiddenToDo-WRT WorkshopCode operator (deleteArtifact))
`;
const scenarios = [
  {
    id: "allow",
    name: "Inspection",
    expected: "PERMITTED",
    action: {
      agent: "operator",
      actionType: "inspectArtifact",
      parameters: {},
    },
  },
  {
    id: "deny",
    name: "Deletion",
    expected: "FORBIDDEN",
    action: { agent: "operator", actionType: "deleteArtifact", parameters: {} },
  },
];
async function reviewPublish(page: Page, version: string) {
  await page.getByRole("button", { name: "Guard test", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Scenarios (JSON)", exact: true })
    .fill(JSON.stringify(scenarios));
  await page.getByRole("button", { name: "Save and run scenarios" }).click();
  await expect(page.locator("pre[role=status]")).toContainText(
    '"passed": true',
  );
  await page.getByRole("button", { name: "Governance", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Review / change description", exact: true })
    .fill(`Browser review ${version}`);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Confirm review" }).click();
  await expect(
    page.getByText("Review for this revision: current"),
  ).toBeVisible();
  await page.getByLabel("New version").fill(version);
  await page.getByRole("button", { name: "Publish snapshot" }).click();
  await expect(
    page.locator("article").filter({ hasText: version }),
  ).toBeVisible();
}

test("new project, structure, MELD, reload, tests, release, activation and rollback", async ({
  page,
  request,
}) => {
  const workspace = await (await request.get("/_fixture/workspace")).json();
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/");
  await page
    .getByRole("button", { name: /Open Project/ })
    .first()
    .click();
  await page.getByLabel("Create a new project directory").check();
  await page.locator("#project-path").fill(workspace.path);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Open Project/ })
    .click();
  await page.getByRole("button", { name: "New domain" }).click();
  await page.locator("#domain-name").fill("Workshop");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Create|Erstellen/, exact: true })
    .click();
  await page
    .getByRole("button")
    .filter({
      has: page.getByRole("heading", { name: "Workshop", exact: true }),
    })
    .click();
  for (const [group, name] of [
    ["Roles", "operator"],
    ["Codes of Conduct", "WorkshopCode"],
    ["Action types", "inspectArtifact"],
    ["Action types", "deleteArtifact"],
  ]) {
    await page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: group, exact: true }) })
      .last()
      .getByRole("button", { name: "Add" })
      .click();
    await page.getByRole("dialog").locator("input").first().fill(name);
    await page.getByRole("button", { name: "Save in MELD" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  await saveSources(page, source);
  const first = await (
    await request.get("/api/domains/workshop", {
      headers: { "X-Aegis-Project": encodeURIComponent(workspace.path) },
    })
  ).json();
  await request.post("/_fixture/reload");
  await page.reload();
  await reviewPublish(page, "1.0.0");
  await page
    .locator("article")
    .filter({ hasText: "1.0.0" })
    .getByRole("button", { name: "Activate / rollback" })
    .click();
  await expect(
    page
      .locator("article")
      .filter({ hasText: "1.0.0" })
      .getByRole("button", { name: "Active", exact: true }),
  ).toBeVisible();
  await saveSources(page, source + "\n;; second immutable revision\n");
  await reviewPublish(page, "1.1.0");
  await page
    .locator("article")
    .filter({ hasText: "1.1.0" })
    .getByRole("button", { name: "Activate / rollback" })
    .click();
  await expect(
    page
      .locator("article")
      .filter({ hasText: "1.1.0" })
      .getByRole("button", { name: "Active", exact: true }),
  ).toBeVisible();
  await page
    .locator("article")
    .filter({ hasText: "1.0.0" })
    .getByRole("button", { name: "Activate / rollback" })
    .click();
  await expect(
    page
      .locator("article")
      .filter({ hasText: "1.0.0" })
      .getByRole("button", { name: "Active", exact: true }),
  ).toBeVisible();
  const verdict = await request.post("/api/domains/workshop/runtime/check", {
    headers: {
      "X-Aegis-Editor": "1",
      "X-Aegis-Project": encodeURIComponent(workspace.path),
    },
    data: scenarios[0].action,
  });
  expect(verdict.ok()).toBeTruthy();
  expect((await verdict.json()).revision).toBe(first.revision);
});

test("custom provider settings, reload and explicit proposal verification/adoption using HTTP fixture", async ({
  page,
  request,
}) => {
  const workspace = await (await request.get("/_fixture/workspace")).json();
  await request.post("/api/project/open", {
    headers: { "X-Aegis-Editor": "1" },
    data: { path: workspace.sample },
  });
  await page.goto("/settings/providers");
  await page.getByRole("button", { name: "Add provider", exact: true }).click();
  const profile = page.locator("fieldset").last();
  await profile
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Browser Fixture");
  await profile
    .getByRole("textbox", { name: "Base URL", exact: true })
    .fill("http://127.0.0.1:18101/_fixture/v1");
  await profile
    .getByRole("combobox", { name: "Model ID", exact: true })
    .fill("fixture-model");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Saved." }),
  ).toBeVisible();
  await request.post("/_fixture/reload");
  await page.reload();
  await expect(
    page
      .locator("fieldset")
      .last()
      .getByRole("combobox", { name: "Model ID", exact: true }),
  ).toHaveValue("fixture-model");
  await page
    .locator("fieldset")
    .last()
    .getByRole("button", { name: "Check connection and models" })
    .click();
  await expect(
    page.locator("fieldset").last().getByRole("status"),
  ).toContainText("Reachable");
  await page.goto("/domain/pharma/authoring");
  await page.getByRole("button").filter({ hasText: "Browser Fixture" }).click();
  await page
    .getByRole("textbox", {
      name: "Model ID (manual entry supported)",
      exact: true,
    })
    .fill("fixture-model");
  await page
    .getByRole("button", { name: "Test tool calling", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Tool call verified");
  await page
    .getByRole("button", { name: /Start Authoring|Authoring starten/ })
    .click();
  await page
    .locator("textarea")
    .fill("Allow pharmacists to report adverse events.");
  await page
    .getByRole("button", {
      name: /Generate Rules/,
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Fixture permission for adverse event reporting", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Accept", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Verify", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Accept", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Accept", exact: true }).click();
  await expect(
    page.getByText("Fixture permission for adverse event reporting", {
      exact: true,
    }),
  ).toHaveCount(0);
  const saved = await (
    await request.get("/api/domains/pharma/sources", {
      headers: { "X-Aegis-Project": encodeURIComponent(workspace.sample) },
    })
  ).json();
  expect(saved.sources["EditorProposals.meld"]).toContain(
    "(reportAdverseEvent majorInteraction)",
  );
});

test("document import runs real DIP with a deterministic HTTP model fixture and remains Draft", async ({
  page,
  request,
}) => {
  const workspace = await (await request.get("/_fixture/workspace")).json();
  await request.post("/api/project/open", {
    headers: { "X-Aegis-Editor": "1" },
    data: { path: workspace.sample },
  });
  let settings = await (await request.get("/api/llm/settings")).json();
  delete settings.credentialStatus;
  settings.profiles.push({
    id: "dip-fixture",
    name: "DIP Fixture",
    protocol: "openai",
    type: "local",
    baseUrl: "http://127.0.0.1:18101/_fixture/v1",
    allowPrivate: true,
    model: "fixture-model",
  });
  await request.put("/api/llm/settings", {
    headers: { "X-Aegis-Editor": "1" },
    data: settings,
  });
  await page.goto("/documents/import");
  await page.getByRole("button").filter({ hasText: "DIP Fixture" }).click();
  await page
    .getByRole("textbox", {
      name: "Model ID (manual entry supported)",
      exact: true,
    })
    .fill("fixture-model");
  await page
    .getByRole("button", { name: "Test tool calling", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Tool call verified");
  await page
    .getByLabel("Domain identifier", { exact: true })
    .fill("document-fixture");
  await page
    .getByLabel("Document title", { exact: true })
    .fill("Browser fixture policy");
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("en");
  await page
    .getByRole("textbox", { name: "Document content", exact: true })
    .fill("Employees may report incidents. Employees must not delete records.");
  await page
    .getByRole("button", { name: "Review document and extract rules" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review result" }),
  ).toBeVisible();
  await expect(page.getByText(/review\.json$/)).toBeVisible();
  await page
    .getByRole("button", { name: "Adopt reviewed result as a new domain" })
    .click();
  await expect(
    page.getByRole("button", { name: "Adopted as draft" }),
  ).toBeVisible();
  const domain = await (
    await request.get("/api/domains/generated-document-fixture", {
      headers: { "X-Aegis-Project": encodeURIComponent(workspace.sample) },
    })
  ).json();
  expect(domain.status).toBe("Draft");
  expect(domain.rules.length).toBeGreaterThan(0);
});

test("English UI and unsaved MELD survive navigation and reload", async ({
  page,
  request,
}) => {
  const workspace = await (await request.get("/_fixture/workspace")).json();
  await request.post("/api/project/open", {
    headers: { "X-Aegis-Editor": "1" },
    data: { path: workspace.sample },
  });
  await page.addInitScript(() => localStorage.setItem("aegis-editor-language", "de"));
  await page.goto("/domain/pharma");
  await expect(
    page.getByRole("button", { name: "Guard test", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Guard test", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "MELD", exact: true }).click();
  const source = page.locator("textarea").last();
  await source.fill(
    (await source.inputValue()) + "\n;; unsaved browser recovery\n",
  );
  let confirmed = false;
  page.on("dialog", async (dialog) => {
    if (dialog.type() === "confirm") {
      confirmed = true;
      await dialog.dismiss();
    } else await dialog.accept();
  });
  await page.getByRole("button", { name: /Dashboard/ }).click();
  await expect.poll(() => confirmed).toBe(true);
  await expect(page).toHaveURL(/domain\/pharma/);
  await page.reload();
  await page.getByRole("button", { name: "MELD", exact: true }).click();
  await expect(page.locator("textarea").last()).toHaveValue(
    /unsaved browser recovery/,
  );
});

test("larger domain remains searchable and supports keyboard structure editing", async ({
  page,
  request,
}) => {
  const workspace = await (await request.get("/_fixture/workspace")).json();
  await request.post("/api/project/open", {
    headers: { "X-Aegis-Editor": "1" },
    data: { path: workspace.sample },
  });
  const headers = {
    "X-Aegis-Editor": "1",
    "X-Aegis-Project": encodeURIComponent(workspace.sample),
  };
  const created = await request.post("/api/domains", {
    headers,
    data: { name: "Scale" },
  });
  expect(created.ok()).toBeTruthy();
  const domain = await created.json();
  const roles = Array.from({ length: 400 }, (_, index) => `operator${index}`);
  const updated = await request.put("/api/domains/scale/sources", {
    headers,
    data: {
      revision: domain.revision,
      sources: {
        "ontology.meld":
          "(aegis-schema-version 1)\n(case ScaleOntology)\n(isa ScaleCode CodeOfConduct)\n" +
          roles.map((role) => `(isa ${role} IntelligentAgent)`).join("\n"),
        "action_vocab.meld":
          "(aegis-schema-version 1)\n(case ScaleActions)\n(isa inspectArtifact ActionType)\n(isa deleteArtifact ActionType)\n",
        "deontic_rules.meld":
          "(aegis-schema-version 1)\n(case ScaleRules)\n" +
          roles
            .map(
              (role) =>
                `(permittedToDo-WRT ScaleCode ${role} (inspectArtifact))\n(forbiddenToDo-WRT ScaleCode ${role} (deleteArtifact))`,
            )
            .join("\n"),
      },
    },
  });
  expect(updated.ok()).toBeTruthy();
  expect((await updated.json()).rules).toHaveLength(800);
  await page.goto("/domain/scale");
  await page.getByRole("button", { name: "Structure", exact: true }).click();
  await page.getByLabel("Search", { exact: true }).fill("operator399");
  const role = page.getByRole("button", { name: "operator399", exact: true });
  await role.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("dialog").getByLabel("MELD symbol", { exact: true }),
  ).toHaveValue("operator399");
});
