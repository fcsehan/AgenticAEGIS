import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import enCommon from "./en/common.json";
import enRules from "./en/rules.json";
import enGovernance from "./en/governance.json";
import enValidation from "./en/validation.json";
import enDomains from "./en/domains.json";
import enAuthoring from "./en/authoring.json";

import enEditor from "./en/editor.json";

const resources = {
  en: {
    editor: enEditor,
    common: enCommon,
    rules: enRules,
    governance: enGovernance,
    validation: enValidation,
    domains: enDomains,
    authoring: enAuthoring,
  },
};

i18n.use(initReactI18next).init({
  resources,
  lng: "en",
  supportedLngs: ["en"],
  fallbackLng: "en",
  ns: [
    "editor",
    "common",
    "rules",
    "governance",
    "validation",
    "domains",
    "authoring",
  ],
  defaultNS: "common",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
